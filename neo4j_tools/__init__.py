"""
Neo4j Transit Graph package for the Magdeburg Campus Assistant.
Provides methods for querying campus buildings, transit stops, routes, POIs, and sensors.
"""

from neo4j_tools._graph import Neo4jTransitGraph

# Module-level singleton driver (shared with mcp_servers/neo4j_server.py).
# Lazily resolved so importing this package doesn't force server import order.
_default_driver = None


def get_default_driver():
    """Return the shared module-level Neo4j driver.

    Prefers the driver created inside `mcp_servers.neo4j_server`. If that
    module cannot be imported (e.g. during eval scripts that only use
    `neo4j_tools`), falls back to creating one from `config.*` — still a
    single module-level instance in this package.
    """
    global _default_driver
    if _default_driver is not None:
        return _default_driver

    try:
        from mcp_servers import neo4j_server as _ns
        _default_driver = _ns._driver
        return _default_driver
    except Exception:
        pass

    from neo4j import GraphDatabase
    from config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD
    _default_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    return _default_driver


__all__ = ['Neo4jTransitGraph', 'get_default_driver']
