"""
Shared domain types used across the codebase.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Coordinates:
    """Immutable geographic point with explicit lat/lon fields.

    Eliminates coordinate-swap bugs by replacing raw (lon, lat) / (lat, lon)
    tuples with named fields.  Every client accesses .lat and .lon directly
    and applies its own API convention internally.
    """
    lat: float
    lon: float

    @classmethod
    def from_dict(cls, d: dict) -> "Coordinates":
        """Create from a dict with latitude/longitude or lat/lon keys."""
        lat = d.get("latitude") or d.get("lat")
        lon = d.get("longitude") or d.get("lon")
        if lat is None or lon is None:
            raise ValueError(f"Cannot extract coordinates from {d}")
        return cls(lat=float(lat), lon=float(lon))
