"""
Package exports for business logic services. Exposes coordinate resolution
functions, the SemanticCache, and canonical thresholds.
"""

from .coordinate_resolver import CoordinateResolver, initialize_resolver, get_coordinates
from .semantic_cache import SemanticCache
from ._embedder import get_shared_encoder, ensure_shared_encoder, set_shared_encoder
from . import thresholds

__all__ = [
    'CoordinateResolver',
    'initialize_resolver',
    'get_coordinates',
    'SemanticCache',
    'get_shared_encoder',
    'ensure_shared_encoder',
    'set_shared_encoder',
    'thresholds',
]
