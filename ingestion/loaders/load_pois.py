"""
Load OSM POIs into Neo4j.

Reads:
  ingestion/data/raw/pois.geojson       (1,051 features from download_pois.py)

Writes (always):
  ingestion/data/processed/pois.json    (one record per POI, normalized to our schema)

Then (unless --dry-run) MERGEs into Neo4j by osm_id:
  - new POI nodes with source='osm', stable osm_id key, full tag set
  - existing manual POI nodes are NEVER touched (they don't have osm_id)

Skip rules:
  - features without a name (47 of 1,051) — names are required for assistant queries
  - geometry types we can't reduce to a point (none in current dump)

Default target is NEO4J_STAGING_*. Pass --production to write to Aura (asks for confirmation).
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


CATEGORY_MAP = {
    # match existing POI.type values where possible (Cafe, Restaurant, Supermarket, Kiosk),
    # introduce new ones for OSM-only categories
    ("amenity", "cafe"): "Cafe",
    ("amenity", "restaurant"): "Restaurant",
    ("amenity", "bar"): "Bar",
    ("amenity", "pub"): "Bar",
    ("amenity", "biergarten"): "Bar",
    ("amenity", "ice_cream"): "IceCream",
    ("amenity", "fast_food"): "FastFood",
    ("amenity", "bank"): "Bank",
    ("amenity", "atm"): "ATM",
    ("amenity", "post_office"): "PostOffice",
    ("amenity", "pharmacy"): "Pharmacy",
    ("shop", "supermarket"): "Supermarket",
    ("shop", "convenience"): "Convenience",
    ("shop", "bakery"): "Bakery",
    ("shop", "kiosk"): "Kiosk",
    ("tourism", "hotel"): "Hotel",
    ("tourism", "museum"): "Museum",
}

# Tag columns we care about — anything not in this list is dropped on import
USEFUL_TAGS = [
    "amenity", "shop", "tourism", "cuisine", "opening_hours",
    "phone", "website", "email", "operator", "brand",
    "addr:street", "addr:housenumber", "addr:postcode", "addr:city",
    "wheelchair", "outdoor_seating", "internet_access",
    "takeaway", "delivery", "smoking",
    "diet:vegan", "diet:vegetarian",
    "wikidata", "wikipedia",
]


def _clean(value):
    """Convert pandas/geopandas null markers to plain Python None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, np.ndarray):
        # rare: a tag that came back as an array
        cleaned = [_clean(v) for v in value]
        cleaned = [v for v in cleaned if v is not None]
        return cleaned[0] if cleaned else None
    return value


def _categorize(amenity, shop, tourism):
    for col, val in (("amenity", amenity), ("shop", shop), ("tourism", tourism)):
        if val and (col, val) in CATEGORY_MAP:
            return CATEGORY_MAP[(col, val)]
    return "Other"


def _extract_point(geom):
    if geom is None:
        return None
    if isinstance(geom, Point):
        return float(geom.y), float(geom.x)
    centroid = geom.centroid
    return float(centroid.y), float(centroid.x)


def normalize(gdf: gpd.GeoDataFrame) -> list[dict]:
    out = []
    skipped = Counter()
    for _, row in gdf.iterrows():
        name = _clean(row.get("name"))
        if not name:
            skipped["no_name"] += 1
            continue

        latlon = _extract_point(row.get("geometry"))
        if latlon is None:
            skipped["no_geometry"] += 1
            continue
        lat, lon = latlon

        # osmnx 2.x reset_index() produces 'element' and 'id' columns
        osmid = _clean(row.get("id"))
        element_type = _clean(row.get("element"))
        if osmid is None or element_type is None:
            skipped["no_osmid"] += 1
            continue

        amenity = _clean(row.get("amenity"))
        shop = _clean(row.get("shop"))
        tourism = _clean(row.get("tourism"))
        category = _categorize(amenity, shop, tourism)

        rec: dict = {
            "osm_id": f"{element_type}/{osmid}",   # stable, e.g. "node/1234567"
            "name": str(name),
            "type": category,
            "latitude": lat,
            "longitude": lon,
            "osm_amenity": amenity,
            "osm_shop": shop,
            "osm_tourism": tourism,
        }
        for tag in USEFUL_TAGS:
            if tag in {"amenity", "shop", "tourism"}:
                continue
            v = _clean(row.get(tag))
            if v is not None:
                rec[tag.replace(":", "_")] = v   # 'addr:street' -> 'addr_street'
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
        confirm = input("This writes POIs to PRODUCTION Aura. Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            raise SystemExit("aborted")

    sync_ts = datetime.now(timezone.utc).isoformat()

    # MERGE on osm_id; manual POIs (no osm_id) are never touched.
    query = """
    UNWIND $batch AS row
    MERGE (p:POI {osm_id: row.osm_id})
    ON CREATE SET p = row, p.source = 'osm', p.last_osm_sync = $sync_ts
    ON MATCH SET p += row, p.last_osm_sync = $sync_ts
    """

    BATCH = 500
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            for i in range(0, len(records), BATCH):
                session.run(query, batch=records[i:i + BATCH], sync_ts=sync_ts)
    return sync_ts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="emit processed JSON only; no Neo4j writes")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    print("Reading raw POI dump...")
    gdf = gpd.read_file(RAW_DIR / "pois.geojson")
    print(f"  features: {len(gdf):,}")

    print("Normalizing...")
    records = normalize(gdf)
    print(f"  named POIs: {len(records):,}")

    cat_counts = Counter(r["type"] for r in records)
    print(f"  category distribution: {dict(cat_counts.most_common())}")

    out_path = OUT_DIR / "pois.json"
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
