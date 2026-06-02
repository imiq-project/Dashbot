"""
Detect candidate duplicates between manually-curated nodes and OSM-imported nodes.

This script is READ-ONLY. It produces a ranked candidate list at:
    ingestion/data/processed/duplicate_candidates.json

Each candidate has:
    - manual node info (elementId, name, lat/lon, aliases, function/type)
    - OSM node info (elementId, name, lat/lon, osm_id, address)
    - evidence (point-in-polygon, distance, name similarity, category match)
    - confidence: "high" / "medium" / "low"
    - suggested resolution: "merge" (high-confidence) or "review" (everything else)

You then edit the file: change "review" entries to "merge" / "keep_both" / "skip".
A second script (apply_duplicate_resolutions.py, written separately) reads the
annotated file and applies the merges.

Detection logic:

  Buildings:
    - HIGH confidence: manual centroid is INSIDE an OSM building's polygon
                       AND name similarity >= 0.85
    - MEDIUM:          inside polygon (any name) OR within 10m + name sim >= 0.7
    - LOW:             within 30m + name sim >= 0.6

  POIs:
    - score = 0.6 * distance_score + 0.3 * name_sim + 0.1 * category_match
    - distance_score = 1.0 at 0m, linearly to 0.0 at 30m
    - HIGH:   score >= 0.85
    - MEDIUM: score >= 0.75
    - LOW:    score >= 0.65

Default target is staging. Pass --production to detect against Aura.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from pyproj import Transformer
from rapidfuzz import fuzz
from shapely import wkt
from shapely.geometry import Point
from shapely.ops import transform
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "ingestion" / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _target(production: bool):
    prefix = "NEO4J" if production else "NEO4J_STAGING"
    label = "PRODUCTION" if production else "STAGING"
    uri = os.getenv(f"{prefix}_URI")
    user = os.getenv(f"{prefix}_USERNAME", "neo4j")
    password = os.getenv(f"{prefix}_PASSWORD")
    database = os.getenv(f"{prefix}_DATABASE", "neo4j")
    if not uri or not password:
        raise SystemExit(f"Missing {prefix}_URI or {prefix}_PASSWORD in .env")
    return label, uri, user, password, database


def _name_sim(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(a, b) / 100.0


def _suggested(confidence: str) -> str:
    return "merge" if confidence == "high" else "review"


def _classify_building(contains: bool, distance: float, name_sim: float) -> str | None:
    if contains and name_sim >= 0.85:
        return "high"
    if contains:
        return "medium"
    if distance <= 10.0 and name_sim >= 0.7:
        return "medium"
    if distance <= 30.0 and name_sim >= 0.6:
        return "low"
    return None


def _classify_poi(distance: float, name_sim: float, category_match: float) -> tuple[str | None, float]:
    distance_score = max(0.0, 1.0 - distance / 30.0)
    score = 0.6 * distance_score + 0.3 * name_sim + 0.1 * category_match
    if score >= 0.85:
        return "high", score
    if score >= 0.75:
        return "medium", score
    if score >= 0.65:
        return "low", score
    return None, score


def detect_buildings(session, to_utm) -> list[dict]:
    print("  Loading manual Buildings...")
    manual_rows = session.run(
        "MATCH (b:Building) WHERE b.source IS NULL "
        "RETURN elementId(b) AS eid, b.name AS name, b.latitude AS lat, b.longitude AS lon, "
        "b.aliases AS aliases, b.function AS function"
    ).data()

    print("  Loading OSM Buildings (with polygons)...")
    osm_rows = session.run(
        "MATCH (b:Building) WHERE b.source = 'osm' "
        "RETURN elementId(b) AS eid, b.name AS name, b.latitude AS lat, b.longitude AS lon, "
        "b.geometry_wkt AS wkt, b.osm_id AS osm_id, b.addr_street AS street, "
        "b.osm_amenity AS amenity, b.function AS function"
    ).data()

    print(f"  manual: {len(manual_rows)} | osm: {len(osm_rows)}")

    osm_geoms, osm_meta = [], []
    for r in osm_rows:
        geom = None
        if r["wkt"]:
            try:
                geom = transform(lambda x, y, z=None: to_utm.transform(x, y), wkt.loads(r["wkt"]))
            except Exception:
                geom = None
        if geom is None and r["lat"] is not None and r["lon"] is not None:
            x, y = to_utm.transform(r["lon"], r["lat"])
            geom = Point(x, y)
        if geom is None or geom.is_empty:
            continue
        osm_geoms.append(geom)
        osm_meta.append(r)

    tree = STRtree(osm_geoms)
    candidates = []
    for m in manual_rows:
        if m["lat"] is None or m["lon"] is None:
            continue
        mx, my = to_utm.transform(m["lon"], m["lat"])
        manual_point = Point(mx, my)
        # Candidates within 30m bbox of the manual point
        for idx in tree.query(manual_point.buffer(30.0)):
            idx = int(idx)
            osm = osm_meta[idx]
            ogeom = osm_geoms[idx]
            # Polygon-contains test (only if it's a polygon)
            contains = bool(hasattr(ogeom, "contains") and hasattr(ogeom, "exterior")
                            and ogeom.contains(manual_point))
            distance = float(manual_point.distance(ogeom))
            name_sim = _name_sim(m["name"], osm["name"])
            confidence = _classify_building(contains, distance, name_sim)
            if confidence is None:
                continue
            candidates.append({
                "kind": "Building",
                "confidence": confidence,
                "manual": {
                    "eid": m["eid"], "name": m["name"], "lat": m["lat"], "lon": m["lon"],
                    "aliases": m.get("aliases"), "function": m.get("function"),
                },
                "osm": {
                    "eid": osm["eid"], "name": osm["name"], "lat": osm["lat"], "lon": osm["lon"],
                    "osm_id": osm["osm_id"], "street": osm.get("street"),
                    "amenity": osm.get("amenity"), "function": osm.get("function"),
                },
                "evidence": {
                    "polygon_contains_manual": contains,
                    "distance_m": round(distance, 2),
                    "name_similarity": round(name_sim, 3),
                },
                "resolution": _suggested(confidence),
            })
    return candidates


def detect_pois(session, to_utm) -> list[dict]:
    print("  Loading manual POIs...")
    manual_rows = session.run(
        "MATCH (p:POI) WHERE p.source IS NULL "
        "RETURN elementId(p) AS eid, p.name AS name, p.latitude AS lat, p.longitude AS lon, "
        "p.type AS type, p.aliases AS aliases"
    ).data()

    print("  Loading OSM POIs...")
    osm_rows = session.run(
        "MATCH (p:POI) WHERE p.source = 'osm' "
        "RETURN elementId(p) AS eid, p.name AS name, p.latitude AS lat, p.longitude AS lon, "
        "p.type AS type, p.osm_id AS osm_id, p.addr_street AS street, p.cuisine AS cuisine"
    ).data()

    print(f"  manual: {len(manual_rows)} | osm: {len(osm_rows)}")

    osm_points, osm_meta = [], []
    for r in osm_rows:
        if r["lat"] is None or r["lon"] is None:
            continue
        x, y = to_utm.transform(r["lon"], r["lat"])
        osm_points.append(Point(x, y))
        osm_meta.append(r)

    tree = STRtree(osm_points)
    candidates = []
    for m in manual_rows:
        if m["lat"] is None or m["lon"] is None:
            continue
        mx, my = to_utm.transform(m["lon"], m["lat"])
        manual_point = Point(mx, my)
        for idx in tree.query(manual_point.buffer(30.0)):
            idx = int(idx)
            osm = osm_meta[idx]
            distance = float(manual_point.distance(osm_points[idx]))
            name_sim = _name_sim(m["name"], osm["name"])
            category_match = 1.0 if (m["type"] and osm["type"] and m["type"] == osm["type"]) else 0.0
            confidence, score = _classify_poi(distance, name_sim, category_match)
            if confidence is None:
                continue
            candidates.append({
                "kind": "POI",
                "confidence": confidence,
                "score": round(score, 3),
                "manual": {
                    "eid": m["eid"], "name": m["name"], "lat": m["lat"], "lon": m["lon"],
                    "type": m.get("type"), "aliases": m.get("aliases"),
                },
                "osm": {
                    "eid": osm["eid"], "name": osm["name"], "lat": osm["lat"], "lon": osm["lon"],
                    "type": osm.get("type"), "osm_id": osm["osm_id"],
                    "street": osm.get("street"), "cuisine": osm.get("cuisine"),
                },
                "evidence": {
                    "distance_m": round(distance, 2),
                    "name_similarity": round(name_sim, 3),
                    "category_match": category_match,
                },
                "resolution": _suggested(confidence),
            })
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", action="store_true",
                        help="Detect against NEO4J_* (production). Default: staging.")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    label, uri, user, password, database = _target(args.production)
    print(f"Source: {label} ({uri})")

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)

    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            print("Detecting Building duplicates...")
            building_candidates = detect_buildings(session, to_utm)
            print(f"  -> {len(building_candidates)} Building candidates")

            print("Detecting POI duplicates...")
            poi_candidates = detect_pois(session, to_utm)
            print(f"  -> {len(poi_candidates)} POI candidates")

    # Sort: high first, then by name_similarity descending
    def sort_key(c):
        order = {"high": 0, "medium": 1, "low": 2}
        return (order.get(c["confidence"], 3), -c["evidence"]["name_similarity"])

    all_candidates = sorted(building_candidates + poi_candidates, key=sort_key)

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": label,
        "totals": {
            "Building_candidates": len(building_candidates),
            "POI_candidates": len(poi_candidates),
            "by_confidence": {
                lvl: sum(1 for c in all_candidates if c["confidence"] == lvl)
                for lvl in ("high", "medium", "low")
            },
        },
        "instructions": (
            "Edit each candidate's 'resolution' field. Options: "
            "'merge' (collapse OSM into manual), 'keep_both' (they are not duplicates), "
            "'skip' (leave as-is for now). High-confidence are pre-marked 'merge'; review them."
        ),
        "candidates": all_candidates,
    }

    out_path = OUT_DIR / "duplicate_candidates.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("=== Summary ===")
    print(f"  high   : {out['totals']['by_confidence']['high']:,}")
    print(f"  medium : {out['totals']['by_confidence']['medium']:,}")
    print(f"  low    : {out['totals']['by_confidence']['low']:,}")
    print()
    print(f"Wrote {out_path.relative_to(ROOT)}")
    print()
    print("=== Top 10 high-confidence candidates ===")
    high = [c for c in all_candidates if c["confidence"] == "high"][:10]
    for c in high:
        ev = c["evidence"]
        print(f"  [{c['kind']}] {c['manual']['name']!r} <-> {c['osm']['name']!r}")
        print(f"    distance={ev['distance_m']}m, name_sim={ev['name_similarity']}", end="")
        if c["kind"] == "Building":
            print(f", contains={ev['polygon_contains_manual']}")
        else:
            print(f", category={ev['category_match']}")


if __name__ == "__main__":
    main()
