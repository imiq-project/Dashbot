"""Utility nodes (cache + proactive) for the LangGraph pipeline.

The proactive bridge node (graph/nodes/proactive_node.py) runs in-process and
is coords-native: when the user's location is known it queries the FIWARE
client directly for nearby weather/parking/traffic and injects a compact
`proactive_context` line for the agent. It does NOT route through the
context-bridge MCP tool — that tool (get_nearby_context) backs on-demand
"what's nearby?" lookups the agent makes itself.
"""

from graph.nodes.cache_node import create_cache_nodes
from graph.nodes._models import CacheCheckResult

__all__ = [
    "create_cache_nodes",
    "CacheCheckResult",
]
