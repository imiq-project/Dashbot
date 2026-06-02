"""
Composed Neo4jTransitGraph class.

Only the place-resolution path is live (place name -> coordinates, used by
mcp_servers/routing_server.py): `_find_stop_or_building` (Neo4jBase) and
`find_any_location` (SearchMixin). The former Transit / Spatial / Sensor mixins
were unused dead code and were removed 2026-06-01.
"""

from neo4j_tools._base import Neo4jBase
from neo4j_tools._search import SearchMixin


class Neo4jTransitGraph(Neo4jBase, SearchMixin):
    """Neo4j graph interface: campus place resolution (name -> coordinates)."""
    pass
