"""Quick look at the POI dump before deciding loader strategy."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import geopandas as gpd

THIS_DIR = Path(__file__).resolve().parent
POIS_PATH = THIS_DIR.parent / "data" / "raw" / "pois.geojson"


def main() -> None:
    gdf = gpd.read_file(POIS_PATH)
    print(f"Total features: {len(gdf):,}")
    print(f"Geometry types: {dict(gdf.geom_type.value_counts())}")
    print(f"Columns ({len(gdf.columns)}):")
    print(f"  {sorted(gdf.columns.tolist())}")
    print()

    # OSM id format in osmnx: tuple-like or string with prefix?
    sample = gdf.iloc[0]
    print("--- Sample row 0 ---")
    print(f"  index value: {gdf.index[0]!r}  (this should encode the osm element type+id)")
    for col in sorted(gdf.columns):
        v = sample[col]
        if col == "geometry":
            v = f"<{type(v).__name__}>"
        print(f"  {col!r}: {v!r}")
    print()

    # Coverage of useful fields
    fields_to_check = [
        "name", "cuisine", "opening_hours", "phone", "website", "email",
        "wheelchair", "outdoor_seating", "addr:street", "addr:housenumber",
        "addr:postcode", "addr:city", "operator", "brand", "internet_access",
        "takeaway", "delivery", "smoking", "diet:vegan", "diet:vegetarian",
    ]
    print("--- Field coverage (% of rows non-null) ---")
    for f in fields_to_check:
        if f in gdf.columns:
            non_null = int(gdf[f].notna().sum())
            pct = non_null / len(gdf) * 100
            print(f"  {f:<22} {non_null:>4} ({pct:5.1f}%)")
        else:
            print(f"  {f:<22} (column missing)")
    print()

    # How many POIs have a name?
    if "name" in gdf.columns:
        with_name = gdf["name"].notna().sum()
        print(f"POIs with a name: {with_name:,} of {len(gdf):,}")

    # Sample 5 named restaurants to see real data shape
    if "amenity" in gdf.columns and "name" in gdf.columns:
        sub = gdf[(gdf["amenity"] == "restaurant") & gdf["name"].notna()].head(5)
        print()
        print("--- Sample 5 named restaurants ---")
        for idx, row in sub.iterrows():
            print(f"  osm_id={idx}: {row['name']}")
            for k in ("cuisine", "opening_hours", "phone", "website", "addr:street"):
                if k in row and not (row[k] is None or (hasattr(row[k], "__class__") and row[k].__class__.__name__ == "float" and str(row[k]) == "nan")):
                    val = row[k]
                    if isinstance(val, str) and len(val) > 60:
                        val = val[:60] + "..."
                    print(f"      {k}: {val}")


if __name__ == "__main__":
    main()
