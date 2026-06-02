"""
Package exports for external API clients. Exposes FIWAREClient and ORSClient
for external service integration.

Each client exposes BOTH sync and async method variants on the same class:
- ORSClient: geocode / ageocode, get_route / aget_route,
  get_multi_modal_routes / aget_multi_modal_routes,
  get_route_with_directions / aget_route_with_directions.
- FIWAREClient: see fiware_client module for sync + async variants.

Sync methods remain fully callable (they bridge to async internally via a
shared httpx.AsyncClient pool). Callers ALWAYS pass `lat, lon` in that order;
coordinate-swap to GeoJSON `[lon, lat]` happens inside each client only.
"""

from .fiware_client import FIWAREClient
from .ors_client import ORSClient

__all__ = [
    'FIWAREClient',
    'ORSClient',
]
