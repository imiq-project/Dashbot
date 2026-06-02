"""
Apply hardcoded review decisions to duplicate_candidates.json.

This is a one-shot helper that codifies my review of the 36 medium + 1 low
candidates produced by detect_duplicates.py. It reads the candidate JSON, looks
up each entry by (manual_name, osm_name) in the DECISIONS map, and sets the
'resolution' field accordingly.

Usable on both staging and production candidate JSONs because matching is by
name pair (eids change between targets, names don't).

Decisions:
  - Buildings where manual centroid sits inside an OSM polygon: MERGE.
    OSM gets full polygon geometry, address, etc. for the manual node.
  - POIs with typo/format/brand-variant names at the same coordinates: MERGE.
  - POIs at the same address that are clearly different establishments: KEEP_BOTH.
  - Borderline institutional cases where merging risks losing distinct identity:
    KEEP_BOTH (cost of keeping both is small; cost of wrong merge is high).

Usage:
    python resolve_medium_candidates.py     # rewrites duplicate_candidates.json in place
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "ingestion" / "data" / "processed" / "duplicate_candidates.json"


# Keys: (manual_name, osm_name)  — None if either side has no name
# Values: "merge" / "keep_both"
DECISIONS: dict[tuple[str | None, str | None], str] = {
    # ---- Buildings: same place, different naming convention -> MERGE ----
    ("Campus Welcome Center", "Campus-Welcome-Center"): "merge",
    ("Experimental Factory Magdeburg (ExFa)", "Experimentelle Fabrik"): "merge",
    ("Building 30 (University Library)", "Universitätsbibliothek"): "merge",
    ("Building 30", "Universitätsbibliothek"): "merge",
    ("Faculty of Humanities", "Gebäude 40"): "merge",
    ("Lecture Hall VI (HS VI)", "Hörsaal 6"): "merge",
    ("Institute for Manufacturing Technology and Quality Assurance (IFQ)", "G12"): "merge",

    # ---- Buildings: manual centroid inside unnamed OSM polygon -> MERGE ----
    ("Faculty of Electrical Engineering and Information Technology", None): "merge",
    ("Rectorate", None): "merge",
    ("Media Technology / Faculty of EIT", None): "merge",
    ("Finance & Student Affairs Building", None): "merge",
    ("Institute for Automation Technology (IFAT)", None): "merge",
    ("Faculty of Process and Systems Engineering / Interaktionszentrum Entrepreneurship", None): "merge",
    ("Faculty of Mechanical Engineering / Process and Systems Engineering / EIT", None): "merge",
    ("Test Facilities - Faculty of Mechanical Engineering", None): "merge",
    ("Institute for Competence in Automotive Mobility (IKAM)", None): "merge",
    ("Test Facilities - Faculty of Process and Systems Engineering / Mechanical Engineering", None): "merge",
    ("Test Facilities - Faculty of Process and Systems Engineering / Institute of Apparatus and Environmental Engineering (AUT)", None): "merge",
    ("Faculty of Natural Sciences / Institute of Experimental Physics / Institute of Chemistry", None): "merge",
    ("OvGU Vehicle Fleet", None): "merge",
    ("Faculty of Economics (Chairs)", None): "merge",
    ("Faculty of Natural Sciences", None): "merge",
    ("Student Council / Lecture Hall I / University Computer Center (URZ)", None): "merge",
    ("Systems Biology Research Center", None): "merge",
    ("Sports Hall 3 (SH3) / Institute of Sports Science", None): "merge",
    ("Sports Hall 2 (SH2) / Institute of Sports Science", None): "merge",
    ("Institute for Materials and Joining Technology / Lecture Hall III", None): "merge",
    ("IMIQ Project Building", None): "merge",
    ("Speicher B / STIMULATE Research Campus", None): "merge",

    # ---- Buildings: borderline (different institutions possibly sharing/neighboring) -> KEEP_BOTH ----
    # ifak (Institute for Automation and Communication) and Denkfabrik (innovation hub) may share a
    # campus structure but are conceptually distinct. Merging would lose the distinct identity.
    ("ifak - Institute for Automation and Communication", "Denkfabrik"): "keep_both",

    # ---- POIs: typos / formatting / brand variants -> MERGE ----
    ("Worldof Pizza", "World of Pizza"): "merge",
    ("Uni Shop", "Uni-Shop"): "merge",
    ("Saporid Italia", "Sapori d'Italia"): "merge",
    ("ALDINord", "Aldi"): "merge",
    ("Niedrig Preis", "NP"): "merge",  # the low-confidence one — NP is the brand abbreviation

    # ---- POIs: distinct establishments at the same address -> KEEP_BOTH ----
    ("Shirokuro", "Asia Wok"): "keep_both",       # Japanese vs Chinese, different restaurants
    ("Tucherstube", "Magdeburger Otto"): "keep_both",  # Beer house vs different establishment
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    candidates = data["candidates"]

    matched = unknown = 0
    by_resolution: dict[str, int] = {}
    for c in candidates:
        if c["confidence"] == "high":
            continue   # already auto-merged in a prior step
        manual_name = c["manual"]["name"]
        osm_name = c["osm"]["name"]
        key = (manual_name, osm_name)
        if key in DECISIONS:
            c["resolution"] = DECISIONS[key]
            matched += 1
            by_resolution[c["resolution"]] = by_resolution.get(c["resolution"], 0) + 1
        else:
            unknown += 1
            print(f"  unmatched candidate: {manual_name!r} <-> {osm_name!r}")

    JSON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Annotated {matched} medium/low candidates ({unknown} unmatched).")
    for k, v in sorted(by_resolution.items()):
        print(f"  resolution='{k}': {v}")


if __name__ == "__main__":
    main()
