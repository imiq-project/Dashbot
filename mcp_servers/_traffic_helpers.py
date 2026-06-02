"""Shared traffic helpers for the FIWARE + routing MCP servers.

Kept in sync with graph/agents/_direct_tools.py so the MCP path and the
in-process path classify and name congestion identically.
"""

import math
import re


def summarize_traffic_entity(entity: dict) -> dict:
    """Compact congestion summary from a FIWARE Traffic entity (keyValues shape).

    With a live `avgSpeed`: congestion = clear / moderate / heavy by ratio to
    `speedLimit`. With no live speed: congestion='clear',
    basis='no_slowdowns_reported' (a confident "no delays reported", never a
    fabricated measurement — live_speed_kmh stays None).
    """
    avg = entity.get("avgSpeed")
    limit = entity.get("speedLimit")
    ratio = (avg / limit) if (isinstance(avg, (int, float))
                              and isinstance(limit, (int, float)) and limit) else None
    if ratio is None:
        congestion, basis = "clear", "no_slowdowns_reported"
    elif ratio < 0.5:
        congestion, basis = "heavy", "live_speed"
    elif ratio < 0.75:
        congestion, basis = "moderate", "live_speed"
    else:
        congestion, basis = "clear", "live_speed"
    return {
        "segment": entity.get("id"),
        "speed_limit_kmh": limit,
        "live_speed_kmh": round(avg, 1) if isinstance(avg, (int, float)) else None,
        "speed_ratio": round(ratio, 2) if ratio is not None else None,
        "congestion": congestion,
        "basis": basis,
    }


def normalize_street_name(name: str) -> str:
    """'Gustav-Adolf-Straße' and 'GustavAdolfStrasse' both -> 'gustavadolfstrasse'."""
    if not name:
        return ""
    s = name.lower()
    s = s.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return re.sub(r"[^a-z0-9]", "", s)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
