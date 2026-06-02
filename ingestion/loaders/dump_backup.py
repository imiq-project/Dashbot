"""
Dump a Neo4j database to JSON (nodes + relationships).

Counterpart to restore_backup.py. Default target is PRODUCTION (NEO4J_*).
Writes timestamped files into backups/ so they're safe to keep alongside earlier dumps.

Usage:
    python dump_backup.py                       # production
    python dump_backup.py --staging             # local staging (for parity tests)
    python dump_backup.py --tag pre-cutover     # adds a tag into the filename
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", action="store_true",
                        help="Dump NEO4J_STAGING_* instead of NEO4J_* (production).")
    parser.add_argument("--tag", default="",
                        help="Optional tag inserted into filename (e.g. 'pre-cutover').")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    prefix = "NEO4J_STAGING" if args.staging else "NEO4J"
    label = "STAGING" if args.staging else "PRODUCTION"

    uri = os.getenv(f"{prefix}_URI")
    user = os.getenv(f"{prefix}_USERNAME", "neo4j")
    password = os.getenv(f"{prefix}_PASSWORD")
    database = os.getenv(f"{prefix}_DATABASE", "neo4j")
    if not uri or not password:
        raise SystemExit(f"Missing {prefix}_URI or {prefix}_PASSWORD in .env")

    print(f"Source: {label} ({uri})")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M")
    tag = f"_{args.tag}" if args.tag else ""
    nodes_path = BACKUP_DIR / f"nodes{tag}_{ts}.json"
    rels_path = BACKUP_DIR / f"relationships{tag}_{ts}.json"
    counts_path = BACKUP_DIR / f"counts{tag}_{ts}.json"

    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            print("Reading nodes...")
            nodes = [
                {"_id": rec["_id"], "_labels": rec["_labels"], "props": rec["props"]}
                for rec in session.run(
                    "MATCH (n) RETURN id(n) AS _id, labels(n) AS _labels, "
                    "properties(n) AS props ORDER BY id(n)"
                ).data()
            ]
            print(f"  {len(nodes):,} nodes")

            print("Reading relationships...")
            rels = [
                {
                    "_id": rec["_id"],
                    "_start": rec["_start"],
                    "_end": rec["_end"],
                    "_type": rec["_type"],
                    "props": rec["props"],
                }
                for rec in session.run(
                    "MATCH (a)-[r]->(b) RETURN id(r) AS _id, id(a) AS _start, "
                    "id(b) AS _end, type(r) AS _type, properties(r) AS props ORDER BY id(r)"
                ).data()
            ]
            print(f"  {len(rels):,} relationships")

            node_counts = {
                row["label"]: row["c"]
                for row in session.run(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c"
                ).data()
            }
            rel_counts = {
                row["t"]: row["c"]
                for row in session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c"
                ).data()
            }

    nodes_path.write_text(json.dumps(nodes, indent=2, ensure_ascii=False), encoding="utf-8")
    rels_path.write_text(json.dumps(rels, indent=2, ensure_ascii=False), encoding="utf-8")
    counts_path.write_text(json.dumps({
        "snapshot_taken_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": label,
        "totals": {"nodes": len(nodes), "relationships": len(rels)},
        "nodes_by_label": node_counts,
        "relationships_by_type": rel_counts,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"  wrote {nodes_path.name}")
    print(f"  wrote {rels_path.name}")
    print(f"  wrote {counts_path.name}")


if __name__ == "__main__":
    main()
