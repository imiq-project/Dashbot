"""
Load Magdeburg named streets into Neo4j from the OSM dump.

Reads:
  ingestion/data/raw/streets_edges.geojson
  ingestion/data/raw/streets_nodes.geojson

Writes (always):
  ingestion/data/processed/streets.json            (one record per named street)
  ingestion/data/processed/streets_intersects.json (one record per ordered pair)

Then (unless --dry-run) MERGEs into Neo4j:
  - Street {name}                          (preserves manual properties on MATCH)
  - (Street)-[:INTERSECTS]-(Street)        (idempotent; values come from data)

Flags:
  --dry-run                                  skip Neo4j write, only emit processed JSON
  --bbox MIN_LAT,MIN_LON,MAX_LAT,MAX_LON     only load streets whose centroid is in box
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import geopandas as gpd
import numpy as np
from dotenv import load_dotenv
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "ingestion" / "data" / "raw"
OUT_DIR = ROOT / "ingestion" / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _flatten(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, np.ndarray)):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _primary(values):
    flat = [v for v in values if v]
    if not flat:
        return None
    return Counter(flat).most_common(1)[0][0]


def _name_of(value):
    flat = _flatten(value)
    return flat[0] if flat else None


def aggregate_streets(edges_gdf):
    df = edges_gdf[edges_gdf["name"].notna()].copy()
    df["_name"] = df["name"].apply(_name_of)
    df = df[df["_name"].notna()]

    records = []
    for name, group in df.groupby("_name"):
        lines = [g for g in group["geometry"].tolist() if isinstance(g, LineString)]
        if not lines:
            continue
        try:
            merged = linemerge(MultiLineString(lines))
        except Exception:
            merged = MultiLineString(lines)
        if isinstance(merged, LineString):
            merged = MultiLineString([merged])

        centroid = merged.centroid
        osm_ids: list[int] = []
        highways: list[str] = []
        for _, row in group.iterrows():
            for x in _flatten(row.get("osmid")):
                try:
                    osm_ids.append(int(x))
                except ValueError:
                    pass
            highways.extend(_flatten(row.get("highway")))

        records.append({
            "name": name,
            "osm_ids": sorted(set(osm_ids)),
            "highway_type": _primary(highways),
            "surface": None,
            "geometry_wkt": merged.wkt,
            "centroid_lat": float(centroid.y),
            "centroid_lon": float(centroid.x),
            "length_m": float(group["length"].sum()),
            "point_count": sum(len(list(ln.coords)) for ln in lines),
            "segment_count": int(len(group)),
        })
    return records


def compute_intersects(edges_gdf, nodes_gdf):
    df = edges_gdf[edges_gdf["name"].notna()].copy()
    df["_name"] = df["name"].apply(_name_of)
    df = df[df["_name"].notna()]

    node_streets: dict[int, set[str]] = defaultdict(set)
    for _, row in df.iterrows():
        node_streets[int(row["u"])].add(row["_name"])
        node_streets[int(row["v"])].add(row["_name"])

    # GeoJSON round-trip drops the osmid index; osmid lives in a column instead.
    node_coords: dict[int, tuple[float, float]] = {
        int(osmid): (float(y), float(x))
        for osmid, y, x in zip(nodes_gdf["osmid"], nodes_gdf["y"], nodes_gdf["x"])
    }

    pair_data: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"junction_count": 0, "lat": None, "lon": None, "osm_node_ids": []}
    )
    for node_id, names in node_streets.items():
        if len(names) < 2:
            continue
        coord = node_coords.get(node_id)
        if coord is None:
            continue
        for a, b in combinations(sorted(names), 2):
            entry = pair_data[(a, b)]
            entry["junction_count"] += 1
            entry["osm_node_ids"].append(int(node_id))
            if entry["lat"] is None:
                entry["lat"], entry["lon"] = coord

    return [
        {"name_a": a, "name_b": b, **data}
        for (a, b), data in pair_data.items()
    ]


def filter_bbox(records, bbox):
    if not bbox:
        return records
    min_lat, min_lon, max_lat, max_lon = bbox
    return [
        r for r in records
        if min_lat <= r["centroid_lat"] <= max_lat
        and min_lon <= r["centroid_lon"] <= max_lon
    ]


def push_to_neo4j(streets, intersects, production: bool):
    from neo4j import GraphDatabase

    prefix = "NEO4J" if production else "NEO4J_STAGING"
    label = "PRODUCTION" if production else "STAGING"
    uri = os.getenv(f"{prefix}_URI", "")
    user = os.getenv(f"{prefix}_USERNAME", "neo4j")
    password = os.getenv(f"{prefix}_PASSWORD", "")
    database = os.getenv(f"{prefix}_DATABASE", "neo4j")

    if not uri or not password:
        raise SystemExit(
            f"{prefix}_URI / {prefix}_PASSWORD missing in .env "
            f"(needed to write to {label})."
        )

    print(f"  target: {label} ({uri})")
    if production:
        confirm = input("This writes to PRODUCTION Aura. Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            raise SystemExit("aborted")

    sync_ts = datetime.now(timezone.utc).isoformat()

    # ON MATCH only touches OSM-derived structural fields; manual fields stay.
    street_query = """
    UNWIND $batch AS row
    MERGE (s:Street {name: row.name})
    ON CREATE SET
      s.source = 'osm',
      s.osm_ids = row.osm_ids,
      s.highway_type = row.highway_type,
      s.geometry_wkt = row.geometry_wkt,
      s.centroid_lat = row.centroid_lat,
      s.centroid_lon = row.centroid_lon,
      s.point_count = row.point_count,
      s.length_m = row.length_m,
      s.last_osm_sync = $sync_ts
    ON MATCH SET
      s.osm_ids = row.osm_ids,
      s.geometry_wkt = row.geometry_wkt,
      s.length_m = row.length_m,
      s.point_count = coalesce(s.point_count, row.point_count),
      s.last_osm_sync = $sync_ts
    """

    intersect_query = """
    UNWIND $batch AS row
    MATCH (a:Street {name: row.name_a}), (b:Street {name: row.name_b})
    MERGE (a)-[r:INTERSECTS]-(b)
    ON CREATE SET
      r.source = 'osm',
      r.junction_count = row.junction_count,
      r.lat = row.lat,
      r.lon = row.lon,
      r.osm_node_ids = row.osm_node_ids,
      r.last_osm_sync = $sync_ts
    ON MATCH SET
      r.junction_count = row.junction_count,
      r.lat = row.lat,
      r.lon = row.lon,
      r.osm_node_ids = row.osm_node_ids,
      r.last_osm_sync = $sync_ts
    """

    BATCH = 500
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            for i in range(0, len(streets), BATCH):
                session.run(street_query, batch=streets[i:i + BATCH], sync_ts=sync_ts)
            for i in range(0, len(intersects), BATCH):
                session.run(intersect_query, batch=intersects[i:i + BATCH], sync_ts=sync_ts)

    return sync_ts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="skip Neo4j write; only produce processed JSON")
    parser.add_argument("--bbox", type=str, default=None,
                        help="MIN_LAT,MIN_LON,MAX_LAT,MAX_LON")
    parser.add_argument("--production", action="store_true",
                        help="Target NEO4J_* (production Aura). Default is NEO4J_STAGING_*.")
    args = parser.parse_args()

    bbox = None
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        if len(parts) != 4:
            raise SystemExit("--bbox needs exactly 4 floats: MIN_LAT,MIN_LON,MAX_LAT,MAX_LON")
        bbox = tuple(parts)

    load_dotenv(ROOT / ".env")

    print("Reading raw OSM dump...")
    edges = gpd.read_file(RAW_DIR / "streets_edges.geojson")
    nodes = gpd.read_file(RAW_DIR / "streets_nodes.geojson")
    print(f"  edges: {len(edges):,} | nodes: {len(nodes):,}")

    print("Aggregating named streets...")
    streets = aggregate_streets(edges)
    print(f"  named streets: {len(streets):,}")

    print("Computing INTERSECTS pairs...")
    intersects = compute_intersects(edges, nodes)
    print(f"  intersect pairs: {len(intersects):,}")

    if bbox:
        before_streets = len(streets)
        before_inter = len(intersects)
        streets = filter_bbox(streets, bbox)
        kept = {s["name"] for s in streets}
        intersects = [r for r in intersects if r["name_a"] in kept and r["name_b"] in kept]
        print(f"  bbox filter: streets {len(streets):,}/{before_streets:,}, intersects {len(intersects):,}/{before_inter:,}")

    streets_path = OUT_DIR / "streets.json"
    intersects_path = OUT_DIR / "streets_intersects.json"
    streets_path.write_text(json.dumps(streets, indent=2, ensure_ascii=False), encoding="utf-8")
    intersects_path.write_text(json.dumps(intersects, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {streets_path.relative_to(ROOT)}")
    print(f"  wrote {intersects_path.relative_to(ROOT)}")

    if args.dry_run:
        print("Dry run — skipping Neo4j write.")
        return

    print("Writing to Neo4j (MERGE; idempotent)...")
    sync_ts = push_to_neo4j(streets, intersects, production=args.production)
    print(f"  done, last_osm_sync={sync_ts}")


if __name__ == "__main__":
    main()
