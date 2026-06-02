"""
Load OSM buildings into Neo4j, filtered to "interesting" ones only.

Of Magdeburg's ~50K building polygons, ~95% are residential houses/garages with no
identity beyond a footprint. This loader keeps only buildings that satisfy ANY of:
  - has a name
  - has amenity / office / shop / tourism / historic / leisure tag
  - building value is in our "civic/institutional/commercial" allowlist

For each kept building:
  - canonical (latitude, longitude) = polygon centroid (matches existing schema)
  - geometry_wkt = full polygon (used by linkers and spatial queries later)
  - function = derived from highest-priority OSM tag (amenity > office > shop > ...)
  - osm_amenity / osm_building / osm_office / osm_shop / osm_tourism / osm_historic /
    osm_leisure / osm_operator preserved as raw values

MERGE on osm_id; manual buildings (no osm_id) are never touched.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
from dotenv import load_dotenv
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "ingestion" / "data" / "raw"
OUT_DIR = ROOT / "ingestion" / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)


CIVIC_BUILDING_VALUES = {
    "public", "civic", "government", "school", "university", "college",
    "hospital", "clinic", "church", "cathedral", "chapel", "mosque", "synagogue",
    "shrine", "temple", "monastery", "kindergarten", "fire_station",
    "train_station", "transportation", "stadium", "sports_hall", "sports_centre",
    "library", "theatre", "cinema", "museum", "hotel", "exhibition", "fairground",
}

INTERESTING_TAGS = ("amenity", "office", "shop", "tourism", "historic", "leisure")
ALL_OSM_TAGS_TO_KEEP = (
    "name", "operator", "brand", "amenity", "office", "shop", "tourism", "historic",
    "leisure", "building", "building:levels", "building:material", "height",
    "addr:street", "addr:housenumber", "addr:postcode", "addr:city",
    "opening_hours", "phone", "website", "email", "wheelchair", "wikidata", "wikipedia",
    "start_date", "heritage", "denomination",
)


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, np.ndarray):
        cleaned = [_clean(x) for x in v]
        cleaned = [x for x in cleaned if x is not None]
        return cleaned[0] if cleaned else None
    return v


def _is_interesting(row) -> bool:
    if _clean(row.get("name")):
        return True
    for tag in INTERESTING_TAGS:
        if _clean(row.get(tag)):
            return True
    building_val = _clean(row.get("building"))
    return bool(building_val) and building_val in CIVIC_BUILDING_VALUES


def _derive_function(row) -> str | None:
    """Pick the most informative OSM tag value for our 'function' field."""
    for tag in ("amenity", "office", "shop", "tourism", "historic", "leisure"):
        v = _clean(row.get(tag))
        if v:
            return v
    building_val = _clean(row.get("building"))
    if building_val and building_val in CIVIC_BUILDING_VALUES:
        return building_val
    return None


def _centroid(geom):
    if geom is None:
        return None
    if isinstance(geom, Point):
        return float(geom.y), float(geom.x), geom.wkt
    centroid = geom.centroid
    return float(centroid.y), float(centroid.x), geom.wkt


def normalize(gdf: gpd.GeoDataFrame) -> list[dict]:
    out = []
    skipped = Counter()
    for _, row in gdf.iterrows():
        if not _is_interesting(row):
            skipped["not_interesting"] += 1
            continue

        centroid_data = _centroid(row.get("geometry"))
        if centroid_data is None:
            skipped["no_geometry"] += 1
            continue
        lat, lon, wkt = centroid_data

        osmid = _clean(row.get("id"))
        element = _clean(row.get("element"))
        if osmid is None or element is None:
            skipped["no_osmid"] += 1
            continue

        rec = {
            "osm_id": f"{element}/{osmid}",
            "latitude": lat,
            "longitude": lon,
            "geometry_wkt": wkt,
            "function": _derive_function(row),
        }
        for tag in ALL_OSM_TAGS_TO_KEEP:
            v = _clean(row.get(tag))
            if v is not None:
                key = tag.replace(":", "_")
                # Prefix raw OSM-only fields so they don't collide with manual schema
                if tag in ("amenity", "office", "shop", "tourism", "historic", "leisure", "building"):
                    rec[f"osm_{tag}"] = v
                else:
                    rec[key] = v
        out.append(rec)

    if skipped:
        print(f"  skipped: {dict(skipped)}")
    return out


def push_to_neo4j(records: list[dict], production: bool):
    from neo4j import GraphDatabase

    prefix = "NEO4J" if production else "NEO4J_STAGING"
    label = "PRODUCTION" if production else "STAGING"
    uri = os.getenv(f"{prefix}_URI", "")
    user = os.getenv(f"{prefix}_USERNAME", "neo4j")
    password = os.getenv(f"{prefix}_PASSWORD", "")
    database = os.getenv(f"{prefix}_DATABASE", "neo4j")

    if not uri or not password:
        raise SystemExit(f"{prefix}_URI / {prefix}_PASSWORD missing in .env")

    print(f"  target: {label} ({uri})")
    if production:
        confirm = input("This writes Buildings to PRODUCTION Aura. Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            raise SystemExit("aborted")

    sync_ts = datetime.now(timezone.utc).isoformat()
    query = """
    UNWIND $batch AS row
    MERGE (b:Building {osm_id: row.osm_id})
    ON CREATE SET b = row, b.source = 'osm', b.last_osm_sync = $sync_ts
    ON MATCH SET b += row, b.last_osm_sync = $sync_ts
    """
    BATCH = 500
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            for i in range(0, len(records), BATCH):
                session.run(query, batch=records[i:i + BATCH], sync_ts=sync_ts)
    return sync_ts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    print("Reading raw building dump...")
    gdf = gpd.read_file(RAW_DIR / "buildings.geojson")
    print(f"  total features: {len(gdf):,}")

    print("Filtering + normalizing...")
    records = normalize(gdf)
    print(f"  kept: {len(records):,}")

    fn_counts = Counter(r["function"] or "(no_function)" for r in records)
    print(f"  function distribution (top 15):")
    for k, v in fn_counts.most_common(15):
        print(f"    {v:>5,} {k}")

    out_path = OUT_DIR / "buildings.json"
    out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {out_path.relative_to(ROOT)}")

    if args.dry_run:
        print("Dry run — skipping Neo4j write.")
        return

    print("Writing to Neo4j (MERGE on osm_id; idempotent)...")
    sync_ts = push_to_neo4j(records, production=args.production)
    print(f"  done, last_osm_sync={sync_ts}")


if __name__ == "__main__":
    main()
