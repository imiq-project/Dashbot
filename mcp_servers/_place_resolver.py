"""
Canonical place resolver — the SINGLE source of truth for turning a free-text
place name ("mensa", "Building 03", "Hauptbahnhof", "ENERCON") into one graph
node plus its nearest transit stop.

Every tool that needs a location (get_building, find_transit_route,
get_routes_for_places, resolve_place_to_coordinates) resolves through this so a
question and its follow-up anchor to the SAME place. Previously each tool had
its own resolver and they disagreed — e.g. "where is mensa" found the curated
campus Mensa while "how do I get to mensa" matched an unrelated OSM building
literally named "Mensa" 2 km away.

Ranking rule (the fix): CURATED campus nodes (`source IS NULL`) outrank
OSM-imported nodes (`source = 'osm'`). Within a tier, full-text score decides.
This mirrors what get_building already did, generalised to every label.

Driver-agnostic: callers pass their own `run_read(cypher, params, timeout)`
(each MCP server process owns its own Neo4j driver).
"""

from __future__ import annotations

import re
from typing import Callable, Optional

RunRead = Callable[..., list]

_BUILDING_NUM_RE = re.compile(
    r"^\s*(?:building|geb\.?|geb[aä]ude)\s+0?(\d{1,2})\s*$", re.IGNORECASE
)

# Lucene specials we escape before building the full-text query string.
_LUCENE_SPECIALS = '+-&|!(){}[]^"~*?:\\/'


def _canonical_building_number(search: str) -> Optional[str]:
    """"building 3" / "Gebäude 27" -> canonical "Building 03" (zero-padded)."""
    m = _BUILDING_NUM_RE.match(search or "")
    return f"Building {int(m.group(1)):02d}" if m else None


def _lucene_escape(term: str) -> str:
    out = []
    for ch in term:
        if ch in _LUCENE_SPECIALS:
            out.append("\\")
        out.append(ch)
    return "".join(out)


# Numbered campus buildings ("Building 27") resolve by exact alias only — the
# curated campus building, never an OSM "Gebäude N" address building. The stop
# is the NEAREST bound stop (ACCESSIBLE_STOP/NEAREST_STOP) or, if none, the
# geographic nearest — picked by real distance so it is deterministic.
_BY_NUMBER_Q = """
    MATCH (b:Building)
    WHERE b.name = $canonical OR $canonical IN COALESCE(b.aliases, [])
    WITH b LIMIT 1
    CALL {
        WITH b
        OPTIONAL MATCH (b)-[:ACCESSIBLE_STOP|NEAREST_STOP]->(sd:Stop)
        WITH b, collect(DISTINCT sd) AS direct
        MATCH (s:Stop)
        WITH s, direct, point.distance(
            point({latitude: b.latitude, longitude: b.longitude}),
            point({latitude: s.latitude, longitude: s.longitude})
        ) AS dist
        WHERE size(direct) = 0 OR s IN direct
        RETURN s AS chosen_stop, dist AS walk_m
        ORDER BY dist LIMIT 1
    }
    RETURN b.name AS entity_name, 'Building' AS entity_type,
           b.latitude AS entity_lat, b.longitude AS entity_lon, b.source AS entity_source,
           chosen_stop.name AS stop_name, chosen_stop.latitude AS stop_lat,
           chosen_stop.longitude AS stop_lon, round(walk_m) AS walk_meters
"""

# Single-shot UNION across the 3 entry points (stop / building / POI). Each
# branch matches via its full-text index and projects a shared schema, then a
# nested CALL picks the bound transit stop (ACCESSIBLE_STOP / NEAREST_STOP) or
# the geographic nearest as fallback. `is_curated` (0 for curated, 1 for OSM)
# is the PRIMARY sort key so curated campus data wins ties against OSM decoys.
_UNION_Q = """
    CALL {
        // Branch 1: direct stop match
        CALL db.index.fulltext.queryNodes("stop_fts", $fts) YIELD node AS s, score
        RETURN s.name AS entity_name, 'Stop' AS entity_type,
               s.latitude AS entity_lat, s.longitude AS entity_lon,
               (CASE WHEN s.source IS NULL THEN 0 ELSE 1 END) AS is_curated,
               s.name AS stop_name, s.latitude AS stop_lat, s.longitude AS stop_lon,
               0 AS walk_meters, score * 2 AS score, 1 AS priority
        LIMIT 3

        UNION

        // Branch 2: building_fts -> nearest bound stop (ACCESSIBLE_STOP/
        // NEAREST_STOP) or geographic nearest, picked by real distance.
        CALL db.index.fulltext.queryNodes("building_fts", $fts) YIELD node AS b, score
        WITH b, score LIMIT 3
        CALL {
            WITH b
            OPTIONAL MATCH (b)-[:ACCESSIBLE_STOP|NEAREST_STOP]->(sd:Stop)
            WITH b, collect(DISTINCT sd) AS direct
            MATCH (s:Stop)
            WITH s, direct, point.distance(
                point({latitude: b.latitude, longitude: b.longitude}),
                point({latitude: s.latitude, longitude: s.longitude})
            ) AS dist
            WHERE size(direct) = 0 OR s IN direct
            RETURN s AS chosen_stop, dist AS walk_m
            ORDER BY dist LIMIT 1
        }
        RETURN b.name AS entity_name, 'Building' AS entity_type,
               b.latitude AS entity_lat, b.longitude AS entity_lon,
               (CASE WHEN b.source IS NULL THEN 0 ELSE 1 END) AS is_curated,
               chosen_stop.name AS stop_name, chosen_stop.latitude AS stop_lat,
               chosen_stop.longitude AS stop_lon,
               round(walk_m) AS walk_meters, score AS score, 2 AS priority

        UNION

        // Branch 3: poi_fts -> nearest bound stop (NEAREST_STOP/ACCESSIBLE_STOP)
        // or geographic nearest, picked by real distance.
        CALL db.index.fulltext.queryNodes("poi_fts", $fts) YIELD node AS p, score
        WITH p, score LIMIT 3
        CALL {
            WITH p
            OPTIONAL MATCH (p)-[:NEAREST_STOP|ACCESSIBLE_STOP]->(sd:Stop)
            WITH p, collect(DISTINCT sd) AS direct
            MATCH (s:Stop)
            WITH s, direct, point.distance(
                point({latitude: p.latitude, longitude: p.longitude}),
                point({latitude: s.latitude, longitude: s.longitude})
            ) AS dist
            WHERE size(direct) = 0 OR s IN direct
            RETURN s AS chosen_stop, dist AS walk_m
            ORDER BY dist LIMIT 1
        }
        RETURN p.name AS entity_name, 'POI' AS entity_type,
               p.latitude AS entity_lat, p.longitude AS entity_lon,
               (CASE WHEN p.source IS NULL THEN 0 ELSE 1 END) AS is_curated,
               chosen_stop.name AS stop_name, chosen_stop.latitude AS stop_lat,
               chosen_stop.longitude AS stop_lon,
               round(walk_m) AS walk_meters, score AS score, 3 AS priority
    }
    RETURN entity_name, entity_type, entity_lat, entity_lon, is_curated,
           stop_name, stop_lat, stop_lon, walk_meters, score, priority
    ORDER BY is_curated ASC, score DESC, priority ASC, walk_meters ASC
    LIMIT 1
"""

# Last resort if the full-text indexes are unavailable: plain CONTAINS on stops.
_FALLBACK_Q = """
    MATCH (s:Stop)
    WHERE toLower(s.name) CONTAINS $search
    RETURN s.name AS entity_name, 'Stop' AS entity_type,
           s.latitude AS entity_lat, s.longitude AS entity_lon,
           s.name AS stop_name, s.latitude AS stop_lat, s.longitude AS stop_lon,
           0 AS walk_meters
    ORDER BY size(s.name)
    LIMIT 1
"""


def _shape(row: dict) -> dict:
    """Normalise a result row into the canonical resolver shape."""
    return {
        "name": row.get("entity_name"),
        "type": row.get("entity_type"),
        "lat": row.get("entity_lat"),
        "lon": row.get("entity_lon"),
        "nearest_stop": {
            "name": row.get("stop_name"),
            "lat": row.get("stop_lat"),
            "lon": row.get("stop_lon"),
            "walk_m": row.get("walk_meters") or 0,
        },
    }


def resolve_place(run_read: RunRead, query: str) -> Optional[dict]:
    """Resolve a place name to a single canonical node + its nearest stop.

    Args:
        run_read: the calling server's read function
            ``run_read(cypher, params, timeout) -> list[dict]``.
        query: free-text place name.

    Returns:
        ``{name, type, lat, lon, nearest_stop: {name, lat, lon, walk_m}}`` or
        ``None`` when nothing matches (the caller may then fall back to a
        geocoder for genuine off-graph street addresses).
    """
    search = (query or "").strip()
    if not search:
        return None

    canonical = _canonical_building_number(search)
    if canonical:
        rows = run_read(_BY_NUMBER_Q, {"canonical": canonical}, 6.0)
        return _shape(rows[0]) if rows else None

    escaped = _lucene_escape(search)
    fts_q = f"{escaped}~1 {escaped}^2" if len(search) >= 4 else escaped
    rows = run_read(_UNION_Q, {"fts": fts_q}, 6.0)
    if rows:
        return _shape(rows[0])

    rows = run_read(_FALLBACK_Q, {"search": search.lower()}, 6.0)
    return _shape(rows[0]) if rows else None
