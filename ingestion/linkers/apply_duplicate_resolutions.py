"""
Apply duplicate-resolution decisions from duplicate_candidates.json.

Reads:
    ingestion/data/processed/duplicate_candidates.json   (produced by detect_duplicates.py)

Modes (mutually exclusive):
    --auto-high       Process every entry with confidence='high' as 'merge'. Skips medium/low.
                      Useful for the obvious duplicates first, before manual review.
    (default)         Only process entries whose 'resolution' field is set to 'merge'.
                      'keep_both' / 'skip' / 'review' are left alone.

Merge semantics for one (manual, osm) pair:
    1. Manual node is the survivor. Its elementId, name, aliases, function, manually-curated
       relationships, and pre-existing properties are sacred.
    2. OSM-derived properties (osm_id, opening_hours, phone, website, addr_*, osm_amenity,
       osm_building, geometry_wkt, etc.) are copied from the OSM node IF the manual node
       does not already have them. Manual values are NEVER overwritten.
    3. All relationships pointing to/from the OSM node are re-routed to the manual node
       via apoc.refactor.mergeNodes (with discardConfig: 'discard' for property conflicts).
    4. The OSM node is deleted.

Idempotency:
    - If the OSM elementId no longer exists in the DB (already merged), the entry is skipped.
    - Re-running is safe.

Default target: staging. Pass --production to apply against Aura (asks for 'yes').
A backup is recommended before any merge run.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES_PATH = ROOT / "ingestion" / "data" / "processed" / "duplicate_candidates.json"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--auto-high", action="store_true",
                        help="Process all confidence='high' entries automatically.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be merged; don't write.")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    label, uri, user, password, database = _target(args.production)

    data = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    if data.get("source") != label:
        print(f"WARN: candidate file was generated against {data.get('source')!r}, "
              f"but applying against {label!r}. elementIds may not match.")
        print("      Re-run detect_duplicates.py against the correct target before applying.")

    candidates = data["candidates"]
    if args.auto_high:
        to_apply = [c for c in candidates if c["confidence"] == "high"]
        print(f"Mode: --auto-high -> {len(to_apply)} entries (confidence=high)")
    else:
        to_apply = [c for c in candidates if c.get("resolution") == "merge"]
        print(f"Mode: explicit -> {len(to_apply)} entries with resolution='merge'")

    if not to_apply:
        print("Nothing to do.")
        return

    print(f"Target: {label} ({uri})")
    if not args.dry_run:
        if args.production:
            confirm = input("This MUTATES PRODUCTION (deletes OSM duplicate nodes, merges into manual). Type 'yes': ").strip().lower()
            if confirm != "yes":
                raise SystemExit("aborted")
        else:
            print("(staging — proceeding)")

    # apoc.refactor.mergeNodes preserves the FIRST node (manual) and merges osm into it.
    # `properties: 'discard'` keeps the surviving node's value on conflict, and osm-only
    # properties are added to the survivor.
    #
    # Caveat: mergeNodes copies OSM-only properties to the survivor regardless of name —
    # including `source` and `last_osm_sync`, which would falsely re-tag the manual node
    # as OSM. We REMOVE those provenance fields post-merge and tag with merged_from_osm
    # so the manual provenance survives.
    merge_query = """
    MATCH (manual) WHERE elementId(manual) = $manual_eid
    MATCH (osm) WHERE elementId(osm) = $osm_eid
    CALL apoc.refactor.mergeNodes([manual, osm], {properties: 'discard', mergeRels: true}) YIELD node
    REMOVE node.source, node.last_osm_sync
    SET node.merged_from_osm = true
    RETURN elementId(node) AS surviving_eid
    """

    stats = Counter()
    failures: list[dict] = []

    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            for c in to_apply:
                manual_eid = c["manual"]["eid"]
                osm_eid = c["osm"]["eid"]
                manual_name = c["manual"]["name"]
                osm_name = c["osm"]["name"]
                kind = c["kind"]
                if args.dry_run:
                    stats[f"would_merge_{kind}"] += 1
                    continue
                try:
                    rec = session.run(
                        merge_query, manual_eid=manual_eid, osm_eid=osm_eid
                    ).single()
                    if rec is None:
                        stats[f"skip_{kind}_not_found"] += 1
                        continue
                    stats[f"merged_{kind}"] += 1
                except Exception as e:
                    stats[f"error_{kind}"] += 1
                    failures.append({
                        "kind": kind,
                        "manual_name": manual_name,
                        "osm_name": osm_name,
                        "manual_eid": manual_eid,
                        "osm_eid": osm_eid,
                        "error": str(e),
                    })

    print()
    print("=== Result ===")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    if failures:
        print()
        print("Failures:")
        for f in failures[:10]:
            print(f"  {f['kind']}: {f['manual_name']!r} <-> {f['osm_name']!r}")
            print(f"    {f['error'][:200]}")


if __name__ == "__main__":
    main()
