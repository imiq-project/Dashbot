"""
Compute ON_STREET edges: connect every POI / Stop / Building to its nearest Street.

Approach:
  1. Read live state from Neo4j (Streets with geometry_wkt; POIs/Stops/Buildings with lat/lon).
  2. Project geometries to UTM 32N (EPSG:32632, correct zone for Magdeburg) so distances
     are in meters, not degrees.
  3. Build a Shapely STRtree spatial index over the projected street geometries — O(N log M)
     nearest-neighbour lookup.
  4. For each source node, find the nearest street; if within --threshold meters, emit an edge.

MERGE pattern:
  - Match source by elementId() (handles duplicate names like both "Building 30" entries).
  - Match street by name (already unique in our schema).
  - ON CREATE: tag with source='osm-linker' and distance_m.
  - ON MATCH (manual edge already exists): leave original fields, just add osm_distance_m.

Default target is NEO4J_STAGING_*. Pass --production to write to Aura (asks for confirmation).
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from pyproj import Transformer
from shapely import wkt
from shapely.geometry import Point
from shapely.ops import transform
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]


def _target(production: bool) -> tuple[str, str, str, str, str]:
    prefix = "NEO4J" if production else "NEO4J_STAGING"
    label = "PRODUCTION" if production else "STAGING"
    uri = os.getenv(f"{prefix}_URI")
    user = os.getenv(f"{prefix}_USERNAME", "neo4j")
    password = os.getenv(f"{prefix}_PASSWORD")
    database = os.getenv(f"{prefix}_DATABASE", "neo4j")
    if not uri or not password:
        raise SystemExit(f"Missing {prefix}_URI or {prefix}_PASSWORD in .env")
    return label, uri, user, password, database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--threshold", type=float, default=50.0,
                        help="Max distance in meters to consider a street as 'on'. Default 50.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be linked, don't write to DB.")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    label, uri, user, password, database = _target(args.production)
    print(f"Target: {label} ({uri})")
    if args.production and not args.dry_run:
        confirm = input("This writes ON_STREET edges to PRODUCTION. Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            raise SystemExit("aborted")

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)

    def project(geom):
        return transform(lambda x, y, z=None: to_utm.transform(x, y), geom)

    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            print("Loading streets...")
            streets_raw = session.run(
                "MATCH (s:Street) WHERE s.geometry_wkt IS NOT NULL "
                "RETURN s.name AS name, s.geometry_wkt AS wkt"
            ).data()
            street_geoms: list = []
            street_names: list[str] = []
            for r in streets_raw:
                try:
                    geom = wkt.loads(r["wkt"])
                except Exception:
                    continue
                street_geoms.append(project(geom))
                street_names.append(r["name"])
            print(f"  {len(street_geoms):,} streets with usable geometry")
            tree = STRtree(street_geoms)

            results: list[tuple[str, list[dict], Counter]] = []
            for src_label in ["POI", "Stop", "Building"]:
                print(f"Loading {src_label}...")
                rows = session.run(
                    f"MATCH (n:{src_label}) "
                    f"WHERE n.latitude IS NOT NULL AND n.longitude IS NOT NULL "
                    f"RETURN elementId(n) AS eid, n.name AS name, "
                    f"n.latitude AS lat, n.longitude AS lon"
                ).data()
                stats: Counter = Counter()
                edges: list[dict] = []
                for r in rows:
                    px, py = to_utm.transform(r["lon"], r["lat"])
                    point = Point(px, py)
                    idx = int(tree.nearest(point))
                    nearest = street_geoms[idx]
                    distance = float(point.distance(nearest))
                    if distance > args.threshold:
                        stats["too_far"] += 1
                        continue
                    edges.append({
                        "eid": r["eid"],
                        "street_name": street_names[idx],
                        "distance_m": distance,
                        "_source_name": r["name"],
                    })
                    stats["linked"] += 1
                results.append((src_label, edges, stats))
                print(f"  {src_label}: linked {stats['linked']:,} | too_far {stats['too_far']:,}")

            if args.dry_run:
                print()
                print("Dry run — sample edges (no DB writes):")
                for src_label, edges, _ in results:
                    print(f"  {src_label} (showing 3 of {len(edges):,}):")
                    for e in edges[:3]:
                        print(f"    {e['_source_name']!r:<40} -> {e['street_name']!r} ({e['distance_m']:.1f}m)")
                return

            sync_ts = datetime.now(timezone.utc).isoformat()
            BATCH = 500
            for src_label, edges, _ in results:
                if not edges:
                    continue
                print(f"Writing {src_label} -> Street edges ({len(edges):,})...")
                query = f"""
                UNWIND $batch AS row
                MATCH (n:{src_label}) WHERE elementId(n) = row.eid
                MATCH (s:Street {{name: row.street_name}})
                MERGE (n)-[r:ON_STREET]->(s)
                ON CREATE SET
                  r.source = 'osm-linker',
                  r.distance_m = row.distance_m,
                  r.last_link_sync = $sync_ts
                ON MATCH SET
                  r.osm_distance_m = row.distance_m,
                  r.last_link_sync = $sync_ts
                """
                for i in range(0, len(edges), BATCH):
                    session.run(query, batch=edges[i:i + BATCH], sync_ts=sync_ts)

            print()
            print("Final ON_STREET breakdown:")
            for row in session.run(
                "MATCH ()-[r:ON_STREET]->() "
                "RETURN coalesce(r.source, 'manual') AS src, count(*) AS c "
                "ORDER BY c DESC"
            ).data():
                print(f"  {row['src']}: {row['c']:,}")


if __name__ == "__main__":
    main()
