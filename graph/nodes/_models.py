"""
Pydantic output models for graph nodes.

Each node dumps a validated model to guarantee field presence and types.
Downstream consumers (cache_store, graph-level conditional edges) rely on
these shapes.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Cache node
# ---------------------------------------------------------------------------


class CacheCheckResult(BaseModel):
    """Output contract of cache_check."""

    cache_hit: bool = False
    # When hit, the cached natural-language answer populates both `response`
    # (legacy field kept for compatibility) and `final_response` (the field
    # downstream nodes use to short-circuit the pipeline).
    response: Optional[str] = None
    final_response: Optional[str] = None
