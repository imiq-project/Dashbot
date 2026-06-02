"""
Download Magdeburg POIs from OSM via osmnx.

Pulls features tagged with amenity/shop/tourism in our category list. Saves the raw
GeoDataFrame to GeoJSON for the loader to process. No DB writes here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import osmnx as ox

PLACE_QUERY = "Magdeburg, Germany"

POI_TAGS = {
    "amenity": [
        "cafe", "restaurant", "bar", "pub", "ice_cream", "fast_food", "biergarten",
        "bank", "atm", "post_office", "pharmacy",
    ],
    "shop": ["supermarket", "convenience", "bakery", "kiosk"],
    "tourism": ["hotel", "museum"],
}

THIS_DIR = Path(__file__).resolve().parent
RAW_DIR = THIS_DIR.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    print(f"Downloading POIs from OSM: place={PLACE_QUERY!r}")
    print(f"Tags: {POI_TAGS}")
    started = datetime.now(timezone.utc)

    gdf = ox.features_from_place(PLACE_QUERY, tags=POI_TAGS)

    # osmnx returns a MultiIndex (element_type, osmid). GeoJSON drops indexes,
    # so promote to columns before saving — we need the osm id for stable MERGE keys.
    gdf = gdf.reset_index()

    pois_path = RAW_DIR / "pois.geojson"
    meta_path = RAW_DIR / "pois_meta.json"

    gdf.to_file(pois_path, driver="GeoJSON")

    finished = datetime.now(timezone.utc)
    type_breakdown: dict[str, int] = {}
    for col in ("amenity", "shop", "tourism"):
        if col in gdf.columns:
            counts = gdf[col].dropna().value_counts().to_dict()
            for k, v in counts.items():
                type_breakdown[f"{col}={k}"] = int(v)

    meta = {
        "place_query": PLACE_QUERY,
        "tags": POI_TAGS,
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "feature_count": int(len(gdf)),
        "geometry_type_counts": gdf.geom_type.value_counts().to_dict(),
        "type_breakdown": dict(sorted(type_breakdown.items(), key=lambda kv: -kv[1])),
        "osmnx_version": ox.__version__,
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"  feature count: {meta['feature_count']:,}")
    print(f"  geometry types: {meta['geometry_type_counts']}")
    print(f"  duration: {meta['duration_seconds']:.1f}s")
    print(f"  raw file: {pois_path}")
    print()
    print("  Top 10 type breakdown:")
    for k, v in list(meta["type_breakdown"].items())[:10]:
        print(f"    {v:>5} {k}")


if __name__ == "__main__":
    main()
