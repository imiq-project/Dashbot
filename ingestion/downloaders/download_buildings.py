"""
Download Magdeburg buildings from OSM via osmnx.

Pulls all features tagged with building=*. Filtering to "interesting" ones (name /
operator / amenity / etc.) happens in the loader, not here — we want the raw set on
disk so we can iterate on filter rules without re-hitting Overpass.

Heads up: Magdeburg has ~80–120K building polygons; this download is the largest single
fetch in the pipeline. Expect 30–90s and a 50–200MB GeoJSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import osmnx as ox

PLACE_QUERY = "Magdeburg, Germany"

THIS_DIR = Path(__file__).resolve().parent
RAW_DIR = THIS_DIR.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    print(f"Downloading buildings from OSM: place={PLACE_QUERY!r}")
    print("Fetching all building=* features (filter applied in loader)")
    started = datetime.now(timezone.utc)

    gdf = ox.features_from_place(PLACE_QUERY, tags={"building": True})
    gdf = gdf.reset_index()

    out_path = RAW_DIR / "buildings.geojson"
    meta_path = RAW_DIR / "buildings_meta.json"
    gdf.to_file(out_path, driver="GeoJSON")

    finished = datetime.now(timezone.utc)
    type_breakdown = {}
    if "building" in gdf.columns:
        type_breakdown = {
            str(k): int(v) for k, v in gdf["building"].dropna().value_counts().head(20).items()
        }

    has_name = int(gdf["name"].notna().sum()) if "name" in gdf.columns else 0
    has_amenity = int(gdf["amenity"].notna().sum()) if "amenity" in gdf.columns else 0

    meta = {
        "place_query": PLACE_QUERY,
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "feature_count": int(len(gdf)),
        "geometry_type_counts": gdf.geom_type.value_counts().to_dict(),
        "with_name": has_name,
        "with_amenity": has_amenity,
        "top_building_values": type_breakdown,
        "osmnx_version": ox.__version__,
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"  feature count   : {meta['feature_count']:,}")
    print(f"  with name       : {has_name:,} ({has_name/meta['feature_count']*100:.1f}%)")
    print(f"  with amenity tag: {has_amenity:,} ({has_amenity/meta['feature_count']*100:.1f}%)")
    print(f"  geometry types  : {meta['geometry_type_counts']}")
    print(f"  duration        : {meta['duration_seconds']:.1f}s")
    print(f"  raw file        : {out_path}")
    print()
    print("  Top building tag values:")
    for k, v in list(meta["top_building_values"].items())[:10]:
        print(f"    {v:>6,} {k}")


if __name__ == "__main__":
    main()
