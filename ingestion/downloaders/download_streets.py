"""
Download Magdeburg's full street network from OpenStreetMap via osmnx.

Saves raw output to ingestion/data/raw/ as:
- streets_nodes.geojson  : intersection points (graph nodes)
- streets_edges.geojson  : street segments (graph edges) with full OSM tags
- streets_meta.json      : download metadata (timestamp, place query, counts)

Idempotent: rerunning overwrites the files. The Neo4j load is a separate step.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import osmnx as ox

PLACE_QUERY = "Magdeburg, Germany"
NETWORK_TYPE = "all"  # all road/path classes incl. service, track, footway

THIS_DIR = Path(__file__).resolve().parent
RAW_DIR = THIS_DIR.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    print(f"Downloading streets from OSM: place={PLACE_QUERY!r}, network_type={NETWORK_TYPE!r}")
    started = datetime.now(timezone.utc)

    # graph_from_place: queries Overpass, builds a NetworkX MultiDiGraph
    G = ox.graph_from_place(PLACE_QUERY, network_type=NETWORK_TYPE)

    # Convert to GeoDataFrames (one for nodes/intersections, one for edges/segments)
    nodes_gdf, edges_gdf = ox.graph_to_gdfs(G)

    edges_path = RAW_DIR / "streets_edges.geojson"
    nodes_path = RAW_DIR / "streets_nodes.geojson"
    meta_path = RAW_DIR / "streets_meta.json"

    # GeoJSON keeps geometry + all OSM tags as properties
    edges_gdf.to_file(edges_path, driver="GeoJSON")
    nodes_gdf.to_file(nodes_path, driver="GeoJSON")

    finished = datetime.now(timezone.utc)
    meta = {
        "place_query": PLACE_QUERY,
        "network_type": NETWORK_TYPE,
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "node_count": int(len(nodes_gdf)),
        "edge_count": int(len(edges_gdf)),
        "edge_columns": sorted(edges_gdf.columns.tolist()),
        "osmnx_version": ox.__version__,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"  nodes (intersections): {meta['node_count']:,}")
    print(f"  edges (segments)     : {meta['edge_count']:,}")
    print(f"  duration             : {meta['duration_seconds']:.1f}s")
    print(f"  raw files            : {RAW_DIR}")


if __name__ == "__main__":
    main()
