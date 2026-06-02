"""
Routing MCP Server for the Magdeburg Campus Mobility Assistant.
Exposes route calculation (walking, cycling, driving), geocoding,
and place-to-coordinate resolution.
Wraps OpenRouteService (walking/cycling/driving). Traffic data now comes from
the FIWARE sensor network (see the FIWARE tools), not this server.
"""

import json
import sys
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from models import Coordinates
from clients.ors_client import ORSClient
from clients.fiware_client import FIWAREClient
from config import (
    ORS_API_KEY, ORS_BASE_URL, HTTP_TIMEOUT,
    MAGDEBURG_LAT, MAGDEBURG_LON,
    FIWARE_BASE_URL, FIWARE_API_KEY,
    NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE,
)
from mcp_servers._traffic_helpers import normalize_street_name, summarize_traffic_entity, haversine_m
from mcp_servers._place_resolver import resolve_place
from neo4j_tools import Neo4jTransitGraph
from neo4j import Query

# Optional import of shared thresholds (authored in parallel — tolerate absence).
try:
    from services.thresholds import BUILDING_EXACT as _BUILDING_EXACT  # type: ignore
except Exception:  # pragma: no cover
    _BUILDING_EXACT = 0.75

mcp = FastMCP("routing", instructions=(
    "Route calculation for Magdeburg. "
    "Supports walking, cycling, and driving routes between coordinates. "
    "Use resolve_place_to_coordinates() or geocode() to convert place names to coordinates first, "
    "then use the route tools with those coordinates. "
    "All coordinates must lie within Magdeburg (lat 52.05-52.20, lon 11.55-11.75)."
))

# ---------------------------------------------------------------------------
# Clients (module-level singletons)
# ---------------------------------------------------------------------------
_ors = ORSClient(ORS_API_KEY, ORS_BASE_URL, HTTP_TIMEOUT)
_fiware = FIWAREClient(FIWARE_BASE_URL, FIWARE_API_KEY)

# ---------------------------------------------------------------------------
# Neo4j-first place resolution. The campus knowledge graph is the PRIMARY
# resolver (via the shared canonical resolver in _place_resolver.py, full-text
# based — no embedding model); the ORS geocoder is only a LAST resort for
# genuine off-graph street addresses. `_neo4j` is kept solely for its driver:
# _run_read() issues the resolver's read-only Cypher through it.
# ---------------------------------------------------------------------------
_neo4j = Neo4jTransitGraph(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)

def _run_read(cypher: str, params: dict | None = None, timeout: float = 8.0) -> list[dict]:
    """Read-only Cypher via the routing server's own Neo4j driver — the read
    function the shared canonical place resolver runs through."""
    with _neo4j.driver.session(database=_neo4j.database) as session:
        result = session.run(Query(cypher, timeout=timeout), parameters=params or {})
        return [dict(record) for record in result]


def _resolve_via_neo4j(place_name: str) -> dict | None:
    """Resolve a place name to coordinates via the shared canonical resolver
    (Neo4j FIRST; curated campus nodes ranked before OSM imports). Returns
    ``{name, lat, lon, type}`` on a graph hit, or ``None`` when nothing matches
    — the caller then falls back to the ORS geocoder (the last resort).

    This is the SAME resolver find_transit_route uses, so a place like "mensa"
    maps to ONE node across every tool instead of three disagreeing matches.
    """
    try:
        hit = resolve_place(_run_read, place_name)
    except Exception:
        # Resolution must never crash routing — fall back to ORS.
        return None
    if not hit or hit.get("lat") is None or hit.get("lon") is None:
        return None
    return {"name": hit.get("name"), "lat": hit["lat"], "lon": hit["lon"], "type": hit.get("type")}


def _nearest_online_parking(lat: float, lon: float, radius_m: int = 800) -> dict:
    """Nearest live FIWARE parking garage to a destination.

    ALWAYS returns the closest garage with status=='Online' (an Offline
    sensor's `freeSpots` is meaningless), with its distance, so the agent can
    name it and how far it is ("~110 free at the Universitätsplatz garage,
    350 m away"). `within_radius` flags whether it's within ``radius_m`` (a
    short walk) so a more distant garage can be phrased honestly ("nearest live
    parking is ~1.2 km away"). Only returns ``{found: False}`` when NO garage
    reports live availability at all. Best-effort: any failure returns
    ``{found: False}`` rather than breaking routing.
    """
    try:
        res = _fiware.query_entities(entity_type="Parking", limit=50)
    except Exception:
        return {"found": False}
    if not isinstance(res, dict) or not res.get("success"):
        return {"found": False}
    best = None
    for e in res.get("entities", []):
        if not isinstance(e, dict) or str(e.get("status")) != "Online":
            continue
        loc = e.get("location")
        plat = plon = None
        if isinstance(loc, str) and "," in loc:
            try:
                parts = loc.split(",")
                plat, plon = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                continue
        elif isinstance(loc, dict):
            coords = loc.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 2:
                plat, plon = coords[1], coords[0]
        if plat is None:
            continue
        d = haversine_m(lat, lon, plat, plon)
        if best is None or d < best["distance_m"]:
            best = {
                "name": e.get("name") or str(e.get("id", "")).split(":", 1)[-1],
                "free_spots": e.get("freeSpots"),
                "total_spots": e.get("totalSpots"),
                "distance_m": round(d),
            }
    if best:
        return {"found": True, "within_radius": best["distance_m"] <= radius_m, **best}
    return {"found": False}


# Outdoor air-quality pollutants we surface (µg/m³). CO2-only indoor sensors are skipped.
_AQ_POLLUTANTS = ("no2", "pm25", "pm10", "o3")


def _nearest_air_quality(lat: float, lon: float, radius_m: int = 3000) -> dict:
    """Nearest live FIWARE air-quality station to a point (e.g. a route midpoint).

    Considers only stations reporting at least one outdoor pollutant
    (NO2/PM2.5/PM10/O3). Returns
    ``{found: True, station, distance_m, pollutants:{...}}`` for the closest in
    range, else ``{found: False}``. Best-effort: failure returns
    ``{found: False}`` rather than breaking routing.
    """
    try:
        res = _fiware.query_entities(entity_type="AirQuality", limit=50)
    except Exception:
        return {"found": False, "radius_m": radius_m}
    if not isinstance(res, dict) or not res.get("success"):
        return {"found": False, "radius_m": radius_m}
    best = None
    for e in res.get("entities", []):
        if not isinstance(e, dict):
            continue
        loc = e.get("location")
        plat = plon = None
        if isinstance(loc, str) and "," in loc:
            try:
                parts = loc.split(",")
                plat, plon = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                continue
        elif isinstance(loc, dict):
            coords = loc.get("coordinates")
            if isinstance(coords, list) and len(coords) >= 2:
                plat, plon = coords[1], coords[0]
        if plat is None:
            continue
        d = haversine_m(lat, lon, plat, plon)
        if d > radius_m:
            continue
        pollutants = {k: e.get(k) for k in _AQ_POLLUTANTS if e.get(k) not in (None, "", [], {})}
        if not pollutants:
            continue
        if best is None or d < best["distance_m"]:
            best = {
                "station": e.get("name") or str(e.get("id", "")).split(":", 1)[-1],
                "distance_m": round(d),
                "pollutants": pollutants,
            }
    if best:
        return {"found": True, **best}
    return {"found": False, "radius_m": radius_m}


def _route_traffic_summary(streets_on_route):
    """Per-segment FIWARE congestion for the streets a route actually uses.

    Name-joins each ORS route street to a live Traffic segment (umlaut/ß/
    separator-normalized) and aggregates to an overall congestion verdict plus
    a `slowdowns` list. Best-effort: any failure returns None so routing never
    breaks. Mirrors graph/agents/_direct_tools._route_traffic_summary.
    """
    if not streets_on_route:
        return None
    try:
        res = _fiware.query_entities(entity_type="Traffic", q="avgSpeed>0", limit=200)
    except Exception:
        return None
    if not isinstance(res, dict) or not res.get("success"):
        return None

    live_by_name = {}
    for ent in res.get("entities", []):
        if not isinstance(ent, dict):
            continue
        key = normalize_street_name(str(ent.get("id", "")).split(":", 1)[-1])
        if key:
            live_by_name[key] = ent

    matched = {}
    for label in streets_on_route:
        for part in str(label).split(","):
            key = normalize_street_name(part)
            if key and key in live_by_name:
                ent = live_by_name[key]
                eid = ent.get("id")
                if eid not in matched:
                    matched[eid] = (part.strip(), summarize_traffic_entity(ent))
                break

    worst = "clear"
    slowdowns = []
    for _eid, (street, summ) in matched.items():
        cong = summ.get("congestion")
        if cong == "heavy":
            worst = "heavy"
        elif cong == "moderate" and worst != "heavy":
            worst = "moderate"
        if cong in ("heavy", "moderate"):
            slowdowns.append({
                "street": street,
                "congestion": cong,
                "live_speed_kmh": summ.get("live_speed_kmh"),
                "speed_limit_kmh": summ.get("speed_limit_kmh"),
                "speed_ratio": summ.get("speed_ratio"),
            })
    slowdowns.sort(key=lambda s: s["speed_ratio"] if s.get("speed_ratio") is not None else 9)

    return {
        "congestion": worst,
        "basis": "live_speed" if matched else "no_slowdowns_reported",
        "method": "per_segment_name_join",
        "streets_checked": len(streets_on_route),
        "live_segments_on_route": len(matched),
        "slowdowns": slowdowns,
    }

# ---------------------------------------------------------------------------
# Grounded bounds: Magdeburg bounding box.  Coordinates outside this box
# are rejected up-front — stops a swapped-lat/lon bug from computing a
# 110 km route through Saxony-Anhalt farmland.
# ---------------------------------------------------------------------------
_MGB_LAT_MIN, _MGB_LAT_MAX = 52.05, 52.20
_MGB_LON_MIN, _MGB_LON_MAX = 11.55, 11.75

# Per-mode route timeout (seconds) for get_all_routes parallel fan-out.
_ROUTE_MODE_TIMEOUT_S = 10


def _validate_magdeburg_coords(lat: float, lon: float) -> dict | None:
    """Reject coordinates outside the Magdeburg bounding box.

    Returns an error dict if out of range, None if OK.  Also catches the
    common swapped-lat/lon mistake (lon passed as lat): any non-numeric or
    NaN values also fail validation.
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return {
            "error": "invalid_coords",
            "reason": "lat/lon must be numeric",
            "received": {"lat": lat, "lon": lon},
        }
    if lat_f != lat_f or lon_f != lon_f:  # NaN check
        return {"error": "invalid_coords", "reason": "NaN"}
    if not (_MGB_LAT_MIN <= lat_f <= _MGB_LAT_MAX and _MGB_LON_MIN <= lon_f <= _MGB_LON_MAX):
        return {
            "error": "coords_outside_magdeburg",
            "bounds": {
                "lat_min": _MGB_LAT_MIN, "lat_max": _MGB_LAT_MAX,
                "lon_min": _MGB_LON_MIN, "lon_max": _MGB_LON_MAX,
            },
            "received": {"lat": lat_f, "lon": lon_f},
            "hint": "Coordinates may be swapped (lon/lat) or outside Magdeburg.",
        }
    return None


def _validate_route_endpoints(start_lat: float, start_lon: float,
                              end_lat: float, end_lon: float) -> dict | None:
    """Validate both start and end coordinates; returns error dict or None."""
    err = _validate_magdeburg_coords(start_lat, start_lon)
    if err:
        err["which"] = "start"
        return err
    err = _validate_magdeburg_coords(end_lat, end_lon)
    if err:
        err["which"] = "end"
        return err
    return None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def geocode(place_name: str) -> str:
    """Convert a place name to geographic coordinates using OpenRouteService geocoding.
    Searches with a Magdeburg focus.

    Args:
        place_name: Place name to geocode, e.g. 'Hauptbahnhof', 'Alter Markt',
                    'Ernst-Reuter-Allee 22'

    Returns:
        JSON with latitude and longitude, or error if not found.
    """
    coords = _ors.geocode(place_name, focus_lat=MAGDEBURG_LAT, focus_lon=MAGDEBURG_LON)
    if coords:
        return json.dumps({
            "success": True,
            "place": place_name,
            "latitude": coords.lat,
            "longitude": coords.lon
        })
    return json.dumps({"success": False, "error": f"Could not geocode '{place_name}'"})


@mcp.tool()
def resolve_place_to_coordinates(place_name: str) -> str:
    """Resolve a campus/city place name to coordinates — Neo4j FIRST.

    Looks the name up in the Neo4j knowledge graph (stops, buildings incl.
    "Building NN" numbers + aliases, POIs by name/cuisine/properties,
    landmarks). Only if the graph has no confident match does it fall back to
    the ORS geocoder — the LAST resort, for genuine off-graph street addresses.
    The `used_method` field tells the caller which path produced the result.

    Args:
        place_name: Place name, e.g. 'mensa', 'Building 03', 'ENERCON',
                    'Hauptbahnhof', 'Izgaram'

    Returns:
        JSON on success:
            {"success": true, "place", "coordinates": [lat, lon],
             "latitude", "longitude", "used_method": "neo4j" | "geocoding",
             "matched_name"?, "type"?}
        On failure:
            {"success": false, "error": "...", "tried": ["neo4j", "geocoding"]}
    """
    # 1. Neo4j knowledge graph FIRST.
    hit = _resolve_via_neo4j(place_name)
    if hit:
        return json.dumps({
            "success": True,
            "place": place_name,
            "coordinates": [hit["lat"], hit["lon"]],
            "latitude": hit["lat"],
            "longitude": hit["lon"],
            "used_method": "neo4j",
            "matched_name": hit.get("name"),
            "type": hit.get("type"),
        })

    # 2. ORS geocoder — LAST resort.
    coords = _ors.geocode(place_name, focus_lat=MAGDEBURG_LAT, focus_lon=MAGDEBURG_LON)
    if coords:
        return json.dumps({
            "success": True,
            "place": place_name,
            "coordinates": [coords.lat, coords.lon],
            "latitude": coords.lat,
            "longitude": coords.lon,
            "used_method": "geocoding",
            "note": "Not found in Neo4j; ORS geocoder fuzzy match (last resort).",
        })

    return json.dumps({
        "success": False,
        "error": f"Place '{place_name}' not found",
        "tried": ["neo4j", "geocoding"],
    })


@mcp.tool()
def get_walking_route(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float
) -> str:
    """Calculate a walking route between two coordinate points.

    Both endpoints must lie within the Magdeburg bounding box
    (lat 52.05-52.20, lon 11.55-11.75).

    Args:
        start_lat: Origin latitude
        start_lon: Origin longitude
        end_lat: Destination latitude
        end_lon: Destination longitude

    Returns:
        JSON with distance, duration, and route geometry.
    """
    err = _validate_route_endpoints(start_lat, start_lon, end_lat, end_lon)
    if err:
        return json.dumps(err)

    start = Coordinates(lat=start_lat, lon=start_lon)
    end = Coordinates(lat=end_lat, lon=end_lon)
    result = _ors.get_route(start, end, profile="walking")
    if result:
        if isinstance(result, dict) and result.get("success"):
            result["air_quality"] = _nearest_air_quality((start_lat + end_lat) / 2.0, (start_lon + end_lon) / 2.0)
        return json.dumps(result, indent=2, default=str)
    return json.dumps({"success": False, "error": "Walking route calculation failed"})


@mcp.tool()
def get_cycling_route(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float
) -> str:
    """Calculate a cycling route between two coordinate points.

    Both endpoints must lie within the Magdeburg bounding box
    (lat 52.05-52.20, lon 11.55-11.75).

    Args:
        start_lat: Origin latitude
        start_lon: Origin longitude
        end_lat: Destination latitude
        end_lon: Destination longitude

    Returns:
        JSON with distance, duration, and route geometry.
    """
    err = _validate_route_endpoints(start_lat, start_lon, end_lat, end_lon)
    if err:
        return json.dumps(err)

    start = Coordinates(lat=start_lat, lon=start_lon)
    end = Coordinates(lat=end_lat, lon=end_lon)
    result = _ors.get_route(start, end, profile="cycling")
    if result:
        if isinstance(result, dict) and result.get("success"):
            result["air_quality"] = _nearest_air_quality((start_lat + end_lat) / 2.0, (start_lon + end_lon) / 2.0)
        return json.dumps(result, indent=2, default=str)
    return json.dumps({"success": False, "error": "Cycling route calculation failed"})


@mcp.tool()
def get_driving_route(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float
) -> str:
    """Calculate a driving route with turn-by-turn directions (OpenRouteService).

    ETA is free-flow distance/duration — live road congestion is sourced
    separately from the FIWARE traffic sensors, not from this router.

    Both endpoints must lie within the Magdeburg bounding box
    (lat 52.05-52.20, lon 11.55-11.75).

    Args:
        start_lat: Origin latitude
        start_lon: Origin longitude
        end_lat: Destination latitude
        end_lon: Destination longitude

    Returns:
        JSON with distance, duration, street names, and turn-by-turn directions.
    """
    err = _validate_route_endpoints(start_lat, start_lon, end_lat, end_lon)
    if err:
        return json.dumps(err)

    start = Coordinates(lat=start_lat, lon=start_lon)
    end = Coordinates(lat=end_lat, lon=end_lon)

    result = _ors.get_route_with_directions(start, end, profile="driving")
    if result:
        if isinstance(result, dict) and result.get("success"):
            traffic = _route_traffic_summary(result.get("streets_on_route", []))
            if traffic is not None:
                result["traffic"] = traffic
            result["destination_parking"] = _nearest_online_parking(end_lat, end_lon)
        return json.dumps(result, indent=2, default=str)
    return json.dumps({"success": False, "error": "Driving route calculation failed"})


# ---------------------------------------------------------------------------
# Helpers for get_all_routes (parallel fan-out)
# ---------------------------------------------------------------------------

def _fetch_walking(start: Coordinates, end: Coordinates) -> dict:
    result = _ors.get_route(start, end, profile="walking")
    if result and result.get("success"):
        out = {
            "available": True,
            "distance": result.get("distance"),
            "duration": result.get("duration"),
            "distance_meters": result.get("distance_meters", 0),
            "duration_seconds": result.get("duration_seconds", 0),
            "geometry": result.get("geometry"),
        }
        out["air_quality"] = _nearest_air_quality((start.lat + end.lat) / 2.0, (start.lon + end.lon) / 2.0)
        return out
    return {"available": False, "error": (result or {}).get("error", "Failed") if result else "No result"}


def _fetch_cycling(start: Coordinates, end: Coordinates) -> dict:
    result = _ors.get_route(start, end, profile="cycling")
    if result and result.get("success"):
        out = {
            "available": True,
            "distance": result.get("distance"),
            "duration": result.get("duration"),
            "distance_meters": result.get("distance_meters", 0),
            "duration_seconds": result.get("duration_seconds", 0),
            "geometry": result.get("geometry"),
        }
        out["air_quality"] = _nearest_air_quality((start.lat + end.lat) / 2.0, (start.lon + end.lon) / 2.0)
        return out
    return {"available": False, "error": (result or {}).get("error", "Failed") if result else "No result"}


def _fetch_driving(start: Coordinates, end: Coordinates) -> dict:
    # Directions endpoint (not plain get_route) so we get streets_on_route for
    # the per-segment traffic join.
    result = _ors.get_route_with_directions(start, end, profile="driving")
    if result and result.get("success"):
        out = {
            "available": True,
            "source": "ors",
            "distance": result.get("distance"),
            "duration": result.get("duration"),
            "distance_meters": result.get("distance_meters", 0),
            "duration_seconds": result.get("duration_seconds", 0),
            "geometry": result.get("geometry"),
        }
        traffic = _route_traffic_summary(result.get("streets_on_route", []))
        if traffic is not None:
            out["traffic"] = traffic
        out["destination_parking"] = _nearest_online_parking(end.lat, end.lon)
        return out
    return {"available": False, "error": "driving route calculation failed"}


@mcp.tool()
def get_all_routes(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float
) -> str:
    """Calculate walking, cycling, and driving routes between two points in parallel.

    Both endpoints must lie within the Magdeburg bounding box
    (lat 52.05-52.20, lon 11.55-11.75).

    Runs the three route lookups concurrently with a 10s timeout per mode.
    If one mode times out or fails, it is reported as
    `{"available": false, "error": ...}` and the others still return.

    Args:
        start_lat: Origin latitude
        start_lon: Origin longitude
        end_lat: Destination latitude
        end_lon: Destination longitude

    Returns:
        JSON with routes for each transport mode.
    """
    err = _validate_route_endpoints(start_lat, start_lon, end_lat, end_lon)
    if err:
        return json.dumps(err)

    start = Coordinates(lat=start_lat, lon=start_lon)
    end = Coordinates(lat=end_lat, lon=end_lon)

    routes: dict = {}
    tasks = {
        "walking": _fetch_walking,
        "cycling": _fetch_cycling,
        "driving": _fetch_driving,
    }

    # ThreadPoolExecutor — the underlying clients are sync (requests-based).
    # Per-mode timeout caps total latency at _ROUTE_MODE_TIMEOUT_S.
    with ThreadPoolExecutor(max_workers=3) as pool:
        future_to_mode = {pool.submit(fn, start, end): mode for mode, fn in tasks.items()}
        for future, mode in list(future_to_mode.items()):
            try:
                routes[mode] = future.result(timeout=_ROUTE_MODE_TIMEOUT_S)
            except FuturesTimeoutError:
                routes[mode] = {
                    "available": False,
                    "error": f"timeout after {_ROUTE_MODE_TIMEOUT_S}s",
                }
            except Exception as e:
                routes[mode] = {"available": False, "error": f"exception: {e}"}

    return json.dumps({"success": True, "routes": routes}, indent=2, default=str)


# ---------------------------------------------------------------------------
# Plan B latency-surgery compound tool.
#
# `get_routes_for_places` collapses what was previously 5 sequential MCP
# calls (resolve origin -> resolve dest -> walking -> cycling -> driving)
# into a single call. Both place resolutions run in parallel via threads,
# then the three route lookups fan out in parallel via the same thread
# pool used by `get_all_routes`. The router agent's prompt should prefer
# this tool for any "how do I get from X to Y" query.
# ---------------------------------------------------------------------------

def _resolve_place_for_compound(place_name: str) -> dict | None:
    """Resolve a place name to ``{name, type, lat, lon, matched}`` or None.

    Mirrors the semantic-then-geocode strategy of
    `resolve_place_to_coordinates` but returns a structured dict instead
    of a JSON string so the compound tool can build a unified payload.
    """
    if not place_name or not place_name.strip():
        return None

    # 1. Neo4j knowledge graph FIRST (names, aliases, building numbers, POI
    #    cuisine/properties, full-text).
    hit = _resolve_via_neo4j(place_name)
    if hit:
        return {
            "name": hit.get("name") or place_name,
            "type": hit.get("type") or "neo4j",
            "lat": hit["lat"],
            "lon": hit["lon"],
            "matched": "neo4j",
        }

    # 2. ORS geocoder — LAST resort (genuine off-graph street addresses only).
    coords = _ors.geocode(place_name, focus_lat=MAGDEBURG_LAT, focus_lon=MAGDEBURG_LON)
    if coords:
        return {
            "name": place_name,
            "type": "geocoded",
            "lat": coords.lat,
            "lon": coords.lon,
            "matched": "geocoding",
        }
    return None


@mcp.tool()
def get_routes_for_places(origin_name: str, destination_name: str) -> str:
    """Single-call route planner: resolves both place names AND computes
    walking, cycling, driving in parallel. Use this for any 'how do I get
    from X to Y' query — it replaces the resolve-resolve-walk-cycle-drive
    sequence with one round-trip.

    Both places are resolved in parallel via the semantic/Neo4j resolver
    (with ORS geocoder fallback), validated against the Magdeburg bounding
    box, then walking/cycling/driving routes run concurrently with a 10s
    per-mode timeout. A failing mode is reported as
    ``{"available": false, "error": "..."}`` rather than dropped.

    Args:
        origin_name: Origin place name (e.g. 'Hauptbahnhof', 'Building 03')
        destination_name: Destination place name

    Returns:
        JSON with origin/destination resolved info plus all three modes.
    """
    # 1. Resolve both places in parallel.
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_origin = pool.submit(_resolve_place_for_compound, origin_name)
        f_dest = pool.submit(_resolve_place_for_compound, destination_name)
        try:
            origin_resolved = f_origin.result(timeout=_ROUTE_MODE_TIMEOUT_S)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": "resolver_error",
                "which": "origin",
                "place": origin_name,
                "detail": str(e),
            })
        try:
            dest_resolved = f_dest.result(timeout=_ROUTE_MODE_TIMEOUT_S)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": "resolver_error",
                "which": "destination",
                "place": destination_name,
                "detail": str(e),
            })

    # Origin failure takes precedence.
    if origin_resolved is None:
        return json.dumps({
            "success": False,
            "error": "place_not_found",
            "which": "origin",
            "place": origin_name,
        })
    if dest_resolved is None:
        return json.dumps({
            "success": False,
            "error": "place_not_found",
            "which": "destination",
            "place": destination_name,
        })

    # 2. Validate both endpoints lie inside Magdeburg.
    for which, resolved in (("origin", origin_resolved), ("destination", dest_resolved)):
        if _validate_magdeburg_coords(resolved["lat"], resolved["lon"]) is not None:
            return json.dumps({
                "success": False,
                "error": "coordinates_outside_magdeburg",
                "which": which,
            })

    start = Coordinates(lat=origin_resolved["lat"], lon=origin_resolved["lon"])
    end = Coordinates(lat=dest_resolved["lat"], lon=dest_resolved["lon"])

    # 3. Fan out the three modes in parallel — same pattern as get_all_routes.
    routes: dict = {}
    tasks = {
        "walking": _fetch_walking,
        "cycling": _fetch_cycling,
        "driving": _fetch_driving,
    }
    with ThreadPoolExecutor(max_workers=3) as pool:
        future_to_mode = {pool.submit(fn, start, end): mode for mode, fn in tasks.items()}
        for future, mode in list(future_to_mode.items()):
            try:
                routes[mode] = future.result(timeout=_ROUTE_MODE_TIMEOUT_S)
            except FuturesTimeoutError:
                routes[mode] = {
                    "available": False,
                    "error": f"timeout after {_ROUTE_MODE_TIMEOUT_S}s",
                }
            except Exception as e:
                routes[mode] = {"available": False, "error": f"exception: {e}"}

    def _endpoint_payload(input_str: str, resolved: dict) -> dict:
        return {
            "input": input_str,
            "name": resolved.get("name"),
            "lat": resolved.get("lat"),
            "lon": resolved.get("lon"),
            "type": resolved.get("type"),
            "matched": resolved.get("matched"),
        }

    return json.dumps({
        "success": True,
        "origin": _endpoint_payload(origin_name, origin_resolved),
        "destination": _endpoint_payload(destination_name, dest_resolved),
        "routes": routes,
    }, indent=2, default=str)


# Traffic tools were TomTom-only and have been removed. Real-time traffic now
# lives in the FIWARE sensor network — external MCP clients should query the
# `fiware` server's Traffic entities (avgSpeed / speedLimit) instead.


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
