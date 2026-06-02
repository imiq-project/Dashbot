"""
Restore a Neo4j JSON backup into the configured target database.

Reads:
  backups/nodes_<date>.json
  backups/relationships_<date>.json

Two-phase load:
  1. Create all nodes, tagging each with a temporary `_backup_id` property so we
     can resolve relationship endpoints in phase 2.
  2. Create all relationships, matching endpoints by `_backup_id`.
  3. Drop the `_backup_id` markers afterwards.

Target by default is the local staging instance (NEO4J_STAGING_*). Pass --production
to target the Aura production vars (NEO4J_*). The script refuses to write into a
non-empty DB unless you pass --wipe.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT / "backups"


def _load_target(production: bool) -> tuple[str, str, str, str, str]:
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
    parser.add_argument("--nodes", type=Path, default=BACKUP_DIR / "nodes_2026-04-29.json")
    parser.add_argument("--relationships", type=Path,
                        default=BACKUP_DIR / "relationships_2026-04-29.json")
    parser.add_argument("--production", action="store_true",
                        help="Target NEO4J_* (production Aura). Default is NEO4J_STAGING_*.")
    parser.add_argument("--wipe", action="store_true",
                        help="DETACH DELETE all existing data in target before restoring.")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    label, uri, user, password, database = _load_target(args.production)

    print(f"Target: {label} ({uri})")
    if args.production:
        confirm = input("This writes to PRODUCTION. Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            raise SystemExit("aborted")

    nodes = json.loads(args.nodes.read_text(encoding="utf-8"))
    rels = json.loads(args.relationships.read_text(encoding="utf-8"))
    print(f"Backup: {len(nodes):,} nodes, {len(rels):,} relationships")

    BATCH = 500
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database=database) as session:
            existing = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            if existing > 0 and not args.wipe:
                raise SystemExit(
                    f"Target has {existing:,} nodes already. "
                    "Use --wipe to clear it, or restore into an empty DB."
                )
            if args.wipe and existing > 0:
                print(f"Wiping {existing:,} existing nodes (and all relationships)...")
                session.run(
                    "CALL apoc.periodic.iterate("
                    "'MATCH (n) RETURN n',"
                    "'DETACH DELETE n',"
                    "{batchSize: 1000, parallel: false})"
                )

            print("Phase 1: creating nodes...")
            node_payload = [
                {
                    "labels": n["_labels"],
                    "props": {**n["props"], "_backup_id": n["_id"]},
                }
                for n in nodes
            ]
            for i in range(0, len(node_payload), BATCH):
                session.run(
                    "UNWIND $batch AS row "
                    "CALL apoc.create.node(row.labels, row.props) YIELD node "
                    "RETURN count(node)",
                    batch=node_payload[i:i + BATCH],
                )

            print("Phase 2: creating relationships...")
            rel_payload = [
                {
                    "start": r["_start"],
                    "end": r["_end"],
                    "type": r["_type"],
                    "props": r["props"],
                }
                for r in rels
            ]
            for i in range(0, len(rel_payload), BATCH):
                session.run(
                    "UNWIND $batch AS row "
                    "MATCH (a {_backup_id: row.start}), (b {_backup_id: row.end}) "
                    "CALL apoc.create.relationship(a, row.type, row.props, b) YIELD rel "
                    "RETURN count(rel)",
                    batch=rel_payload[i:i + BATCH],
                )

            print("Phase 3: removing _backup_id markers...")
            session.run(
                "CALL apoc.periodic.iterate("
                "'MATCH (n) WHERE n._backup_id IS NOT NULL RETURN n',"
                "'REMOVE n._backup_id',"
                "{batchSize: 1000})"
            )

            final_nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            final_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            print()
            print(f"After restore: {final_nodes:,} nodes, {final_rels:,} relationships")
            print(f"Expected:      {len(nodes):,} nodes, {len(rels):,} relationships")
            if final_nodes == len(nodes) and final_rels == len(rels):
                print("OK counts match")
            else:
                print("WARN counts DIFFER -- investigate before proceeding")


if __name__ == "__main__":
    main()
