"""
Compute the full set of geometric relationships between POIs / Stops / Buildings / Streets.

Reads live state from Neo4j (geometries already populated by streets/POI/building loaders).
Projects everything to UTM 32N once, builds STRtree indexes, then computes:

  IN_BUILDING        POI inside a Building polygon (point-in-polygon)
  NEAREST_BUILDING   POI -> nearest Building within 30m (fallback when not inside)
  NEAREST_STOP       POI / Building -> nearest Stop within 300m
  BORDERED_BY        Building polygon edge within 5m of a Street line
  ADJACENT_TO        Building polygon within 5m of another Building (undirected)
  NEARBY             POI within 100m of POI or Building (undirected, top-15 per source)

All relationships use MERGE — existing manual edges are NEVER overwritten, only enriched
with `osm_distance_m` on match. New edges get `source='spatial-linker'`, `distance_m`,
`last_link_sync`.

Default target is staging. Pass --production to write to Aura (requires 'yes' confirm).
Pass --dry-run to compute and preview counts without any DB writes.
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


# Tunable thresholds (meters). Override via CLI flags.
DEFAULT_NEAREST_BUILDING_MAX = 30.0
DEFAULT_NEAREST_STOP_MAX = 300.0
DEFAULT_BORDERED_BY_TOL = 5.0
DEFAULT_ADJACENT_TO_TOL = 5.0
DEFAULT_NEARBY_RADIUS = 100.0
NEARBY_TOP_K = 15  # cap per source to avoid edge explosion


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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--nearest-building-max", type=float, default=DEFAULT_NEAREST_BUILDING_MAX)
    parser.add_argument("--nearest-stop-max", type=float, default=DEFAULT_NEAREST_STOP_MAX)
    parser.add_argument("--bordered-by-tol", type=float, default=DEFAULT_BORDERED_BY_TOL)
    parser.add_argument("--adjacent-to-tol", type=float, default=DEFAULT_ADJACENT_TO_TOL)
    parser.add_argument("--nearby-radius", type=float, default=DEFAULT_NEARBY_RADIUS)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    label, uri, user, password, database = _target(args.production)
    print(f"Target: {label} ({uri})")
    if args.production and not args.dry_run:
        confirm = input("This writes spatial relationships to PRODUCTION. Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            raise SystemExit("aborted")

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)

    def project_geom(g):
        return transform(lambda x, y, z=None: to_utm.transform(x, y), g)

    def project_point(lat, lon) -> Point:
        x, y = to_utm.transform(lon, lat)
        return Point(x, y)

    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            print("Loading nodes...")

            buildings_raw = session.run(
                "MATCH (b:Building) "
                "WHERE b.geometry_wkt IS NOT NULL OR (b.latitude IS NOT NULL AND b.longitude IS NOT NULL) "
                "RETURN elementId(b) AS eid, b.name AS name, b.geometry_wkt AS wkt, "
                "b.latitude AS lat, b.longitude AS lon"
            ).data()
            building_geoms: list = []
            building_eids: list[str] = []
            for r in buildings_raw:
                geom = None
                if r["wkt"]:
                    try:
                        g = wkt.loads(r["wkt"])
                        geom = project_geom(g)
                    except Exception:
                        geom = None
                if geom is None and r["lat"] is not None and r["lon"] is not None:
                    geom = project_point(r["lat"], r["lon"])
                if geom is None or geom.is_empty:
                    continue
                building_geoms.append(geom)
                building_eids.append(r["eid"])
            print(f"  Building: {len(building_geoms):,} usable geometries")

            streets_raw = session.run(
                "MATCH (s:Street) WHERE s.geometry_wkt IS NOT NULL "
                "RETURN elementId(s) AS eid, s.name AS name, s.geometry_wkt AS wkt"
            ).data()
            street_geoms: list = []
            street_eids: list[str] = []
            for r in streets_raw:
                try:
                    geom = project_geom(wkt.loads(r["wkt"]))
                except Exception:
                    continue
                street_geoms.append(geom)
                street_eids.append(r["eid"])
            print(f"  Street: {len(street_geoms):,} usable geometries")

            stops_raw = session.run(
                "MATCH (s:Stop) WHERE s.latitude IS NOT NULL AND s.longitude IS NOT NULL "
                "RETURN elementId(s) AS eid, s.name AS name, s.latitude AS lat, s.longitude AS lon"
            ).data()
            stop_points = [project_point(r["lat"], r["lon"]) for r in stops_raw]
            stop_eids = [r["eid"] for r in stops_raw]
            print(f"  Stop: {len(stop_points):,} usable points")

            pois_raw = session.run(
                "MATCH (p:POI) WHERE p.latitude IS NOT NULL AND p.longitude IS NOT NULL "
                "RETURN elementId(p) AS eid, p.name AS name, p.latitude AS lat, p.longitude AS lon"
            ).data()
            poi_points = [project_point(r["lat"], r["lon"]) for r in pois_raw]
            poi_eids = [r["eid"] for r in pois_raw]
            print(f"  POI: {len(poi_points):,} usable points")

            print("Building spatial indexes...")
            building_tree = STRtree(building_geoms)
            street_tree = STRtree(street_geoms)
            stop_tree = STRtree(stop_points)
            poi_tree = STRtree(poi_points)

            edges: dict[str, list[dict]] = {
                "IN_BUILDING": [],          # POI -> Building
                "NEAREST_BUILDING": [],     # POI -> Building (fallback when not inside)
                "NEAREST_STOP": [],         # POI/Building -> Stop
                "BORDERED_BY": [],          # Building -> Street
                "ADJACENT_TO": [],          # Building - Building (undirected, ordered eid_a < eid_b)
                "NEARBY": [],               # POI - {POI, Building} (undirected)
            }

            print("Computing IN_BUILDING / NEAREST_BUILDING for each POI...")
            for poi_eid, point in zip(poi_eids, poi_points):
                # Candidates whose bbox + 30m radius intersects the point
                candidate_idxs = building_tree.query(point.buffer(args.nearest_building_max))
                inside_idx = None
                best_dist = float("inf")
                best_idx = -1
                for idx in candidate_idxs:
                    bgeom = building_geoms[int(idx)]
                    if hasattr(bgeom, "contains") and bgeom.contains(point):
                        inside_idx = int(idx)
                        break
                    d = point.distance(bgeom)
                    if d < best_dist:
                        best_dist = d
                        best_idx = int(idx)
                if inside_idx is not None:
                    edges["IN_BUILDING"].append({
                        "eid_a": poi_eid, "eid_b": building_eids[inside_idx], "distance_m": 0.0,
                    })
                elif best_idx >= 0 and best_dist <= args.nearest_building_max:
                    edges["NEAREST_BUILDING"].append({
                        "eid_a": poi_eid, "eid_b": building_eids[best_idx], "distance_m": best_dist,
                    })

            print("Computing NEAREST_STOP for POIs and Buildings...")
            for label_kind, source_eids, source_geoms in (
                ("POI", poi_eids, poi_points),
                ("Building", building_eids, building_geoms),
            ):
                for src_eid, geom in zip(source_eids, source_geoms):
                    probe = geom.centroid if hasattr(geom, "centroid") else geom
                    candidates = stop_tree.query(probe.buffer(args.nearest_stop_max))
                    if len(candidates) == 0:
                        continue
                    best_idx, best_dist = -1, float("inf")
                    for idx in candidates:
                        d = probe.distance(stop_points[int(idx)])
                        if d < best_dist:
                            best_dist = d
                            best_idx = int(idx)
                    if best_idx >= 0 and best_dist <= args.nearest_stop_max:
                        edges["NEAREST_STOP"].append({
                            "eid_a": src_eid, "eid_b": stop_eids[best_idx],
                            "distance_m": best_dist,
                        })

            print("Computing BORDERED_BY (Building polygon -> Street within 5m)...")
            for b_eid, bgeom in zip(building_eids, building_geoms):
                if not hasattr(bgeom, "exterior"):  # not a polygon, skip
                    continue
                candidates = street_tree.query(bgeom.buffer(args.bordered_by_tol))
                seen_streets: set[int] = set()
                for idx in candidates:
                    idx = int(idx)
                    if idx in seen_streets:
                        continue
                    sgeom = street_geoms[idx]
                    d = bgeom.distance(sgeom)
                    if d <= args.bordered_by_tol:
                        edges["BORDERED_BY"].append({
                            "eid_a": b_eid, "eid_b": street_eids[idx], "distance_m": d,
                        })
                        seen_streets.add(idx)

            print("Computing ADJACENT_TO (Building <-> Building within 5m, undirected)...")
            seen_pairs: set[tuple[str, str]] = set()
            for i, (b_eid, bgeom) in enumerate(zip(building_eids, building_geoms)):
                if not hasattr(bgeom, "exterior"):
                    continue
                candidates = building_tree.query(bgeom.buffer(args.adjacent_to_tol))
                for idx in candidates:
                    idx = int(idx)
                    if idx == i:
                        continue
                    other_eid = building_eids[idx]
                    pair = (min(b_eid, other_eid), max(b_eid, other_eid))
                    if pair in seen_pairs:
                        continue
                    other_geom = building_geoms[idx]
                    d = bgeom.distance(other_geom)
                    if d <= args.adjacent_to_tol:
                        edges["ADJACENT_TO"].append({
                            "eid_a": pair[0], "eid_b": pair[1], "distance_m": d,
                        })
                        seen_pairs.add(pair)

            print(f"Computing NEARBY (POI <-> POI/Building within {args.nearby_radius:.0f}m, top {NEARBY_TOP_K})...")
            seen_nearby_pairs: set[tuple[str, str]] = set()
            for poi_eid, point in zip(poi_eids, poi_points):
                # Build a candidate list of (distance, target_eid) across both POIs and Buildings
                candidates: list[tuple[float, str]] = []
                for idx in poi_tree.query(point.buffer(args.nearby_radius)):
                    idx = int(idx)
                    other = poi_eids[idx]
                    if other == poi_eid:
                        continue
                    d = point.distance(poi_points[idx])
                    if d <= args.nearby_radius:
                        candidates.append((d, other))
                for idx in building_tree.query(point.buffer(args.nearby_radius)):
                    idx = int(idx)
                    bgeom = building_geoms[idx]
                    d = point.distance(bgeom)
                    if d <= args.nearby_radius:
                        candidates.append((d, building_eids[idx]))
                candidates.sort()
                for d, other_eid in candidates[:NEARBY_TOP_K]:
                    pair = (min(poi_eid, other_eid), max(poi_eid, other_eid))
                    if pair in seen_nearby_pairs:
                        continue
                    edges["NEARBY"].append({
                        "eid_a": pair[0], "eid_b": pair[1], "distance_m": d,
                    })
                    seen_nearby_pairs.add(pair)

            print()
            print("=== Edge counts ===")
            for rel, batch in edges.items():
                print(f"  {rel:<18} {len(batch):>6,}")
            total = sum(len(b) for b in edges.values())
            print(f"  {'TOTAL':<18} {total:>6,}")

            if args.dry_run:
                print()
                print("Dry run -- no DB writes. Sample edges:")
                for rel, batch in edges.items():
                    if not batch:
                        continue
                    print(f"  {rel} (showing 3 of {len(batch):,}):")
                    for e in batch[:3]:
                        print(f"    {e['eid_a']!r:<25} -> {e['eid_b']!r:<25} ({e['distance_m']:.1f}m)")
                return

            sync_ts = datetime.now(timezone.utc).isoformat()
            BATCH = 500
            queries = {
                # IN_BUILDING and NEAREST_BUILDING are directed POI -> Building
                "IN_BUILDING": (
                    "UNWIND $batch AS row "
                    "MATCH (a:POI) WHERE elementId(a) = row.eid_a "
                    "MATCH (b:Building) WHERE elementId(b) = row.eid_b "
                    "MERGE (a)-[r:IN_BUILDING]->(b) "
                    "ON CREATE SET r.source = 'spatial-linker', r.distance_m = row.distance_m, r.last_link_sync = $sync_ts "
                    "ON MATCH SET r.osm_distance_m = row.distance_m, r.last_link_sync = $sync_ts"
                ),
                "NEAREST_BUILDING": (
                    "UNWIND $batch AS row "
                    "MATCH (a:POI) WHERE elementId(a) = row.eid_a "
                    "MATCH (b:Building) WHERE elementId(b) = row.eid_b "
                    "MERGE (a)-[r:NEAREST_BUILDING]->(b) "
                    "ON CREATE SET r.source = 'spatial-linker', r.distance_m = row.distance_m, r.last_link_sync = $sync_ts "
                    "ON MATCH SET r.osm_distance_m = row.distance_m, r.last_link_sync = $sync_ts"
                ),
                "NEAREST_STOP": (
                    "UNWIND $batch AS row "
                    "MATCH (a) WHERE elementId(a) = row.eid_a "
                    "MATCH (b:Stop) WHERE elementId(b) = row.eid_b "
                    "MERGE (a)-[r:NEAREST_STOP]->(b) "
                    "ON CREATE SET r.source = 'spatial-linker', r.distance_m = row.distance_m, r.last_link_sync = $sync_ts "
                    "ON MATCH SET r.osm_distance_m = row.distance_m, r.last_link_sync = $sync_ts"
                ),
                "BORDERED_BY": (
                    "UNWIND $batch AS row "
                    "MATCH (a:Building) WHERE elementId(a) = row.eid_a "
                    "MATCH (b:Street) WHERE elementId(b) = row.eid_b "
                    "MERGE (a)-[r:BORDERED_BY]->(b) "
                    "ON CREATE SET r.source = 'spatial-linker', r.distance_m = row.distance_m, r.last_link_sync = $sync_ts "
                    "ON MATCH SET r.osm_distance_m = row.distance_m, r.last_link_sync = $sync_ts"
                ),
                # ADJACENT_TO and NEARBY are undirected MERGE
                "ADJACENT_TO": (
                    "UNWIND $batch AS row "
                    "MATCH (a:Building) WHERE elementId(a) = row.eid_a "
                    "MATCH (b:Building) WHERE elementId(b) = row.eid_b "
                    "MERGE (a)-[r:ADJACENT_TO]-(b) "
                    "ON CREATE SET r.source = 'spatial-linker', r.distance_m = row.distance_m, r.last_link_sync = $sync_ts "
                    "ON MATCH SET r.osm_distance_m = row.distance_m, r.last_link_sync = $sync_ts"
                ),
                "NEARBY": (
                    "UNWIND $batch AS row "
                    "MATCH (a) WHERE elementId(a) = row.eid_a "
                    "MATCH (b) WHERE elementId(b) = row.eid_b "
                    "MERGE (a)-[r:NEARBY]-(b) "
                    "ON CREATE SET r.source = 'spatial-linker', r.distance_m = row.distance_m, r.last_link_sync = $sync_ts "
                    "ON MATCH SET r.osm_distance_m = row.distance_m, r.last_link_sync = $sync_ts"
                ),
            }

            for rel, batch in edges.items():
                if not batch:
                    continue
                q = queries[rel]
                print(f"Writing {rel} ({len(batch):,})...")
                for i in range(0, len(batch), BATCH):
                    session.run(q, batch=batch[i:i + BATCH], sync_ts=sync_ts)

            print()
            print("Final relationship breakdown:")
            for row in session.run(
                "MATCH ()-[r]->() WHERE type(r) IN ['IN_BUILDING', 'NEAREST_BUILDING', 'NEAREST_STOP', 'BORDERED_BY', 'ADJACENT_TO', 'NEARBY'] "
                "RETURN type(r) AS rel, coalesce(r.source, 'manual') AS src, count(*) AS c "
                "ORDER BY rel, c DESC"
            ).data():
                print(f"  {row['rel']:<18} {row['src']:<16} {row['c']:>6,}")


if __name__ == "__main__":
    main()
