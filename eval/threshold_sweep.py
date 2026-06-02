"""Ablation sweep for semantic thresholds.

Runs a fixed query set at multiple threshold combos, records counts of
correct / wrong / refused / ambiguous outcomes, writes a markdown table
to eval/reports/threshold_sweep_<timestamp>.md.

Run:  python eval/threshold_sweep.py [--queries eval/eval_typos.jsonl] [--dry-run]
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Sweep grid
# ---------------------------------------------------------------------------

KB_GRID: List[float] = [0.20, 0.40, 0.55, 0.70]
BUILDING_GRID: List[float] = [0.40, 0.60, 0.75]


# ---------------------------------------------------------------------------
# Default probe set (20 queries keyed to real Magdeburg campus entities).
# Each probe carries the expected resolved entity (or None for refusal /
# ambiguous) and a `kind` tag driving the mock classifier's monotone
# behavior across the threshold grid.
# ---------------------------------------------------------------------------

DEFAULT_PROBES: List[Dict[str, Any]] = [
    # strong exact-or-near-exact building hits
    {"query": "Where is the Campus Welcome Center?", "expected_entity": "Campus Welcome Center",
     "expected_outcome": "correct", "kind": "strong_building"},
    {"query": "Find the Faculty of Mathematics", "expected_entity": "Faculty of Mathematics",
     "expected_outcome": "correct", "kind": "strong_building"},
    {"query": "How do I get to the Rectorate?", "expected_entity": "Rectorate",
     "expected_outcome": "correct", "kind": "strong_building"},
    {"query": "Where is IFAT?", "expected_entity": "IFAT",
     "expected_outcome": "correct", "kind": "strong_building"},
    {"query": "Find Mechanical Engineering building", "expected_entity": "Mechanical Engineering",
     "expected_outcome": "correct", "kind": "strong_building"},
    {"query": "Where is IFQ?", "expected_entity": "IFQ",
     "expected_outcome": "correct", "kind": "strong_building"},
    {"query": "How do I reach IKAM?", "expected_entity": "IKAM",
     "expected_outcome": "correct", "kind": "strong_building"},
    # weak-ish building references (short codes / partial names)
    {"query": "Where is B01?", "expected_entity": "Campus Welcome Center",
     "expected_outcome": "correct", "kind": "weak_building"},
    {"query": "Where is B04?", "expected_entity": "Rectorate",
     "expected_outcome": "correct", "kind": "weak_building"},
    {"query": "Tell me about Building 12", "expected_entity": "IFQ",
     "expected_outcome": "correct", "kind": "weak_building"},
    # strong knowledge-base queries
    {"query": "What is the IMIQ project?", "expected_entity": "IMIQ",
     "expected_outcome": "correct", "kind": "strong_kb"},
    {"query": "Tell me about OVGU Magdeburg", "expected_entity": "OVGU",
     "expected_outcome": "correct", "kind": "strong_kb"},
    # ambiguous Hauptbahnhof probes (must disambiguate, not silently pick one)
    {"query": "Where is Hauptbahnhof?", "expected_entity": None,
     "expected_outcome": "ambiguous", "kind": "ambiguous"},
    {"query": "Next tram from Magdeburg Hauptbahnhof", "expected_entity": None,
     "expected_outcome": "ambiguous", "kind": "ambiguous"},
    # out-of-domain (must refuse at any sane threshold)
    {"query": "What is 2+2?", "expected_entity": None,
     "expected_outcome": "refused", "kind": "ood"},
    {"query": "Tell me a joke", "expected_entity": None,
     "expected_outcome": "refused", "kind": "ood"},
    {"query": "What's the weather in Tokyo?", "expected_entity": None,
     "expected_outcome": "refused", "kind": "ood"},
    # NULL-property queries — building resolves, property is missing; must admit unknown
    {"query": "What are the opening hours of the Rectorate?", "expected_entity": "Rectorate",
     "expected_outcome": "refused", "kind": "null_prop"},
    {"query": "When does IFAT close?", "expected_entity": "IFAT",
     "expected_outcome": "refused", "kind": "null_prop"},
    {"query": "Is IKAM open on Sundays?", "expected_entity": "IKAM",
     "expected_outcome": "refused", "kind": "null_prop"},
]


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------

@dataclass
class Counts:
    correct: int = 0
    wrong: int = 0
    refused: int = 0
    ambiguous: int = 0
    scores: List[float] = field(default_factory=list)

    def bump(self, label: str, score: Optional[float] = None) -> None:
        if label not in ("correct", "wrong", "refused", "ambiguous"):
            label = "wrong"
        setattr(self, label, getattr(self, label) + 1)
        if score is not None:
            self.scores.append(float(score))

    def avg_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores) / len(self.scores)


# ---------------------------------------------------------------------------
# Query loading
# ---------------------------------------------------------------------------

def load_queries(path: Optional[str]) -> List[Dict[str, Any]]:
    """Load probes from JSONL. Each record should include at least a `query`
    field; `expected_entity`, `expected_outcome`, and `kind` are used when
    present. Falls back to DEFAULT_PROBES when path is None or unreadable.
    """
    if not path:
        return list(DEFAULT_PROBES)
    p = Path(path)
    if not p.exists():
        print(f"[threshold_sweep] queries file not found: {p} — using defaults",
              file=sys.stderr)
        return list(DEFAULT_PROBES)
    probes: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "query" not in rec:
                continue
            rec.setdefault("expected_entity", None)
            rec.setdefault("expected_outcome",
                           "correct" if rec.get("expected_entity") else "refused")
            rec.setdefault("kind", _infer_kind(rec))
            probes.append(rec)
    if not probes:
        return list(DEFAULT_PROBES)
    return probes


def _infer_kind(rec: Dict[str, Any]) -> str:
    behavior = (rec.get("expected_behavior") or "").lower()
    if "out_of_scope" in behavior or "refuse_out" in behavior:
        return "ood"
    if "null" in behavior or "unknown" in behavior:
        return "null_prop"
    if "ambig" in behavior or "disambig" in behavior:
        return "ambiguous"
    if "typo" in behavior:
        return "weak_building"
    if "knowledge" in behavior or "kb" in behavior:
        return "strong_kb"
    return "strong_building"


# ---------------------------------------------------------------------------
# Mock runner (used when --dry-run or when live infra is unavailable)
# ---------------------------------------------------------------------------

def _mock_runner(
    probe: Dict[str, Any],
    kb_min: float,
    building_exact: float,
) -> Dict[str, Any]:
    """Deterministic simulation of the four outcomes as a monotone function
    of the two thresholds. The returned record mirrors the live-runner
    schema so downstream aggregation is agnostic to mode.
    """
    kind = probe.get("kind", "strong_building")
    expected_entity = probe.get("expected_entity")

    # Simulated top-1 / top-2 scores — chosen to cross the grid thresholds
    # in a way that roughly reflects how real queries behave.
    if kind == "strong_building":
        score_top1, score_top2 = 0.88, 0.42
    elif kind == "weak_building":
        score_top1, score_top2 = 0.58, 0.50
    elif kind == "strong_kb":
        score_top1, score_top2 = 0.80, 0.35
    elif kind == "weak_kb":
        score_top1, score_top2 = 0.45, 0.38
    elif kind == "null_prop":
        score_top1, score_top2 = 0.85, 0.40
    elif kind == "ambiguous":
        score_top1, score_top2 = 0.78, 0.76
    else:  # ood
        score_top1, score_top2 = 0.22, 0.18

    outcome = "wrong"
    resolved_entity: Optional[str] = None
    resolve_method = "simulated"

    if kind == "ood":
        outcome = "wrong" if kb_min < 0.40 else "refused"

    elif kind == "null_prop":
        # Building resolves, but property is absent. Loose building match
        # causes the agent to confidently pick a wrong building AND invent
        # hours -> counted as wrong.
        if building_exact < 0.60:
            outcome = "wrong"
        else:
            outcome = "refused"
            resolved_entity = expected_entity

    elif kind == "ambiguous":
        # Two near-tied candidates (Hauptbahnhof/Kölner Platz vs
        # /Willy-Brandt-Platz). The top-gap guard catches this unless
        # building_exact is too loose.
        if building_exact < 0.60:
            outcome = "wrong"
        else:
            outcome = "ambiguous"

    elif kind == "strong_building":
        if score_top1 >= building_exact:
            outcome = "correct"
            resolved_entity = expected_entity
            resolve_method = "exact"
        else:
            outcome = "refused"

    elif kind == "weak_building":
        if building_exact <= 0.45:
            outcome = "wrong"          # noise match at very-loose threshold
        elif score_top1 >= building_exact:
            outcome = "correct"
            resolved_entity = expected_entity
            resolve_method = "fuzzy"
        else:
            outcome = "refused"

    elif kind == "strong_kb":
        if kb_min > 0.75:
            outcome = "refused"
        else:
            outcome = "correct"
            resolved_entity = expected_entity
            resolve_method = "kb"

    elif kind == "weak_kb":
        if kb_min <= 0.20:
            outcome = "wrong"          # noise chunks sneak in
        elif kb_min >= 0.55:
            outcome = "refused"
        else:
            outcome = "correct"
            resolved_entity = expected_entity
            resolve_method = "kb"

    return {
        "query": probe.get("query"),
        "expected_entity": expected_entity,
        "resolved_entity": resolved_entity,
        "resolve_method": resolve_method,
        "score_top1": score_top1,
        "score_top2": score_top2,
        "outcome": outcome,
    }


# ---------------------------------------------------------------------------
# Optional live runner — monkeypatches services.thresholds + queries the
# real CoordinateResolver / KnowledgeBase.
# ---------------------------------------------------------------------------

def _try_load_live_runner() -> Optional[Callable[[Dict[str, Any], float, float], Dict[str, Any]]]:
    """Return a callable that runs a probe through the live resolvers if
    everything imports and initializes successfully. Returns None on any
    failure so the sweep falls back to the mock runner.
    """
    try:
        thresholds = importlib.import_module("services.thresholds")
        cr_mod = importlib.import_module("services.coordinate_resolver")
        kb_mod = importlib.import_module("services.knowledge_base")
    except Exception as exc:
        print(f"[threshold_sweep] live runner unavailable — import failed: {exc}",
              file=sys.stderr)
        return None

    resolver_cls = getattr(cr_mod, "CoordinateResolver", None)
    kb_cls = getattr(kb_mod, "KnowledgeBase", None)
    if resolver_cls is None or kb_cls is None:
        return None

    try:
        resolver = resolver_cls()
        kb = kb_cls()
    except Exception as exc:
        print(f"[threshold_sweep] live runner unavailable — init failed: {exc}",
              file=sys.stderr)
        return None

    def _resolve(query: str) -> Dict[str, Any]:
        """Try the resolver first; fall back to KB."""
        try:
            r = resolver.resolve(query)  # expected to return dict
            if isinstance(r, dict):
                return r
        except Exception:
            pass
        try:
            hits = kb.search(query, top_k=2)  # expected list of dicts
            if hits:
                top1 = hits[0]
                top2 = hits[1] if len(hits) > 1 else {}
                return {
                    "entity": top1.get("entity") or top1.get("source"),
                    "method": "kb",
                    "score_top1": float(top1.get("score", 0.0)),
                    "score_top2": float(top2.get("score", 0.0)),
                }
        except Exception:
            pass
        return {}

    def _run(probe: Dict[str, Any], kb_min: float, building_exact: float) -> Dict[str, Any]:
        # Monkeypatch the shared thresholds module for this cell.
        thresholds.KB_MIN_SCORE = kb_min
        thresholds.BUILDING_EXACT = building_exact
        thresholds.STOP_EXACT = building_exact
        thresholds.POI_EXACT = max(0.0, building_exact - 0.05)

        q = probe.get("query", "")
        try:
            r = _resolve(q)
        except Exception:
            r = {}

        resolved_entity = r.get("entity") if isinstance(r, dict) else None
        resolve_method = r.get("method") if isinstance(r, dict) else "unknown"
        score_top1 = float(r.get("score_top1", 0.0)) if isinstance(r, dict) else 0.0
        score_top2 = float(r.get("score_top2", 0.0)) if isinstance(r, dict) else 0.0

        expected_entity = probe.get("expected_entity")
        expected_outcome = probe.get("expected_outcome", "correct")

        # Classify outcome by comparing resolved vs expected.
        if expected_outcome == "refused":
            outcome = "refused" if not resolved_entity else "wrong"
        elif expected_outcome == "ambiguous":
            if not resolved_entity:
                outcome = "ambiguous"
            elif (score_top1 - score_top2) < thresholds.TOP_GAP_MIN:
                outcome = "ambiguous"
            else:
                outcome = "wrong"
        else:  # correct
            if (resolved_entity and expected_entity
                    and str(expected_entity).lower() in str(resolved_entity).lower()):
                outcome = "correct"
            elif resolved_entity is None:
                outcome = "refused"
            else:
                outcome = "wrong"

        return {
            "query": q,
            "expected_entity": expected_entity,
            "resolved_entity": resolved_entity,
            "resolve_method": resolve_method or "unknown",
            "score_top1": score_top1,
            "score_top2": score_top2,
            "outcome": outcome,
        }

    return _run


# ---------------------------------------------------------------------------
# Sweep + report
# ---------------------------------------------------------------------------

def run_sweep(
    probes: List[Dict[str, Any]],
    runner: Callable[[Dict[str, Any], float, float], Dict[str, Any]],
) -> Tuple[Dict[Tuple[float, float], Counts], List[Dict[str, Any]]]:
    cells: Dict[Tuple[float, float], Counts] = {}
    raw_rows: List[Dict[str, Any]] = []
    for kb_min in KB_GRID:
        for building_exact in BUILDING_GRID:
            counts = Counts()
            for probe in probes:
                rec = runner(probe, kb_min, building_exact)
                counts.bump(rec["outcome"], rec.get("score_top1"))
                raw_rows.append({
                    "KB_MIN_SCORE": kb_min,
                    "BUILDING_EXACT": building_exact,
                    **rec,
                })
            cells[(kb_min, building_exact)] = counts
    return cells, raw_rows


def to_markdown(
    cells: Dict[Tuple[float, float], Counts],
    mode: str,
    n_probes: int,
) -> str:
    rows = []
    for (kb_min, building_exact), c in cells.items():
        rows.append({
            "KB_MIN": kb_min,
            "BUILDING_EXACT": building_exact,
            "correct": c.correct,
            "wrong": c.wrong,
            "refused": c.refused,
            "ambiguous": c.ambiguous,
            "avg_score": round(c.avg_score(), 3),
        })
    # Sort by correct desc, then wrong asc
    rows.sort(key=lambda r: (-r["correct"], r["wrong"]))

    lines: List[str] = []
    lines.append(f"# Threshold sweep — {n_probes} probes ({mode} mode)")
    lines.append("")
    lines.append(f"Grid: KB_MIN_SCORE ∈ {KB_GRID}, BUILDING_EXACT ∈ {BUILDING_GRID}")
    lines.append("")
    lines.append("| KB_MIN | BUILDING_EXACT | correct | wrong | refused | ambiguous | avg_score |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['KB_MIN']:.2f} | {r['BUILDING_EXACT']:.2f} | "
            f"{r['correct']} | {r['wrong']} | {r['refused']} | {r['ambiguous']} | "
            f"{r['avg_score']:.3f} |"
        )
    lines.append("")
    lines.append("Rows sorted by `correct` descending, then `wrong` ascending.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", default=None,
                    help="JSONL of probes (default: built-in 20-query set)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Force the mock runner even if live infra is importable")
    ap.add_argument("--out", default=None,
                    help="Markdown output path (default: eval/reports/threshold_sweep_<ts>.md)")
    args = ap.parse_args()

    probes = load_queries(args.queries)

    runner: Callable[[Dict[str, Any], float, float], Dict[str, Any]]
    if args.dry_run:
        runner = _mock_runner
        mode = "dry-run"
    else:
        live = _try_load_live_runner()
        if live is not None:
            runner = live
            mode = "live"
        else:
            runner = _mock_runner
            mode = "mocked"

    print(f"[threshold_sweep] running in {mode} mode over {len(probes)} probes "
          f"x {len(KB_GRID) * len(BUILDING_GRID)} cells", file=sys.stderr)

    t0 = time.time()
    cells, raw_rows = run_sweep(probes, runner)
    elapsed = time.time() - t0

    # Determine output path.
    if args.out:
        out_path = Path(args.out)
    else:
        reports_dir = REPO_ROOT / "eval" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = reports_dir / f"threshold_sweep_{ts}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    md = to_markdown(cells, mode, len(probes))
    out_path.write_text(md, encoding="utf-8")

    # Sidecar JSON with per-query rows for deeper analysis.
    json_path = out_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(
            {
                "mode": mode,
                "elapsed_seconds": round(elapsed, 2),
                "n_probes": len(probes),
                "grid": {"KB_MIN_SCORE": KB_GRID, "BUILDING_EXACT": BUILDING_GRID},
                "rows": raw_rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(md)
    print(f"\n[threshold_sweep] wrote {out_path}", file=sys.stderr)
    print(f"[threshold_sweep] wrote {json_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
