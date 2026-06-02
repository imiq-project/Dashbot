"""
Inspect the raw streets dump before deciding loader strategy.

Reports:
- Total edge segments
- Named vs unnamed share
- Distribution of unique street names (this becomes our Street node count)
- highway-type breakdown
- Sample of named-way aggregation (segments per named street)
- Sample row showing all available OSM tags
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import geopandas as gpd

THIS_DIR = Path(__file__).resolve().parent
EDGES_PATH = THIS_DIR.parent / "data" / "raw" / "streets_edges.geojson"


def main() -> None:
    edges = gpd.read_file(EDGES_PATH)
    total = len(edges)
    print(f"Total edge segments: {total:,}")
    print(f"Columns: {sorted(edges.columns.tolist())}")
    print()

    has_name = edges["name"].notna() if "name" in edges.columns else None
    if has_name is not None:
        named = int(has_name.sum())
        unnamed = total - named
        print(f"Named segments  : {named:,} ({named / total:.1%})")
        print(f"Unnamed segments: {unnamed:,} ({unnamed / total:.1%})")
        unique_names = edges.loc[has_name, "name"].dropna()
        unique_names = unique_names.apply(lambda v: v if isinstance(v, str) else str(v))
        print(f"Unique street names: {unique_names.nunique():,}")
        print()
        print("Top 10 named streets by segment count:")
        for name, cnt in unique_names.value_counts().head(10).items():
            print(f"  {cnt:>4} x  {name}")
        print()

    if "highway" in edges.columns:
        hw_values = edges["highway"].apply(
            lambda v: v if isinstance(v, str) else (v[0] if isinstance(v, list) and v else "unknown")
        )
        print("highway-type breakdown:")
        for hw, cnt in Counter(hw_values).most_common():
            print(f"  {cnt:>6,} x  {hw}")
        print()

    print("--- Sample edge (first row, all properties) ---")
    sample = edges.iloc[0].to_dict()
    for k, v in sample.items():
        if k == "geometry":
            v = f"<{type(v).__name__} with {len(v.coords) if hasattr(v, 'coords') else '?'} coords>"
        print(f"  {k!r}: {v!r}")


if __name__ == "__main__":
    main()
