"""
Proactive context bridge node (single-agent, location-triggered).

When the user shares a location, proactively pull nearby live conditions
(weather, parking, traffic) by coordinates and inject a compact, freshness-
tagged context line so the gpt-5.4 agent can surface them without being asked.

Adapted from the recovered multi-agent `proactive_node`:
- TomTom branch dropped (client removed; traffic now from FIWARE).
- Gating simplified: fire when `user_location` is present (the "on location"
  trigger) instead of the old multi-agent `agents_to_call` signal.
- Coords-native: fetches the nearest sensor of each type via the FIWARE client
  directly, so it works from raw GPS without a name lookup.

Every branch is best-effort with a hard per-branch timeout: a slow or missing
sensor must never block or fail the agent turn.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

_BRANCH_TIMEOUT_SECONDS = 3.0
_RADIUS_M = 800


def _to_float(value):
    """FIWARE attributes sometimes arrive as strings — coerce to float or None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coords(user_location):
    if not isinstance(user_location, dict):
        return None, None
    lat = user_location.get("lat", user_location.get("latitude"))
    lon = user_location.get("lon", user_location.get("longitude"))
    return _to_float(lat), _to_float(lon)


def create_proactive_node(fiware_client):
    """Create the proactive context-bridge node bound to the FIWARE client."""

    async def _nearest(lat, lon, sensor_type):
        try:
            return await asyncio.wait_for(
                fiware_client.aquery_sensor_by_coordinates(
                    latitude=lat, longitude=lon, sensor_type=sensor_type, radius=_RADIUS_M,
                ),
                timeout=_BRANCH_TIMEOUT_SECONDS,
            )
        except Exception:
            # Out-of-bounds coords, timeout, or transport error — proactive
            # failures are silent by design.
            return None

    async def proactive_node(state: dict) -> dict:
        if fiware_client is None:
            return {}
        lat, lon = _coords(state.get("user_location"))
        if lat is None or lon is None:
            return {}

        weather, parking, traffic = await asyncio.gather(
            _nearest(lat, lon, "Weather"),
            _nearest(lat, lon, "Parking"),
            _nearest(lat, lon, "Traffic"),
        )

        bits: list[str] = []

        if isinstance(weather, dict) and weather.get("success"):
            e = weather.get("entity", {})
            temp = _to_float(e.get("temperature"))
            if temp is not None:
                rain = _to_float(e.get("precipitation"))
                suffix = " (rain)" if (rain is not None and rain > 0) else ""
                bits.append(f"weather ~{temp:.0f}°C{suffix}")

        if isinstance(parking, dict) and parking.get("success"):
            e = parking.get("entity", {})
            free = e.get("freeSpots")
            if free is None:
                free = e.get("freeParkingSpaces")
            if free is not None:
                name = (e.get("name") or e.get("id") or "nearest lot")
                bits.append(f"parking '{name}': {free} free")

        if isinstance(traffic, dict) and traffic.get("success"):
            e = traffic.get("entity", {})
            avg = _to_float(e.get("avgSpeed"))
            lim = _to_float(e.get("speedLimit"))
            if avg is not None and lim:
                ratio = avg / lim
                band = "heavy" if ratio < 0.5 else ("moderate" if ratio < 0.75 else "clear")
                if band != "clear":
                    road = str(e.get("id", "nearby")).replace("Traffic:", "")
                    bits.append(f"traffic {band} on {road}")

        if not bits:
            return {}

        ctx = (
            f"PROACTIVE NEARBY CONTEXT (live, fetched {_iso_now()}; the user is "
            f"at lat={lat:.5f}, lon={lon:.5f}). Mention only what's relevant to "
            f"their question, naturally: " + "; ".join(bits) + "."
        )
        print(f"[PROACTIVE] {ctx}")
        return {"proactive_context": ctx}

    return proactive_node
