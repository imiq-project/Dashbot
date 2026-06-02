"""LLM-judge factuality scorer.

Input:  JSONL with {query, reference_answer, assistant_answer}.
Output: summary JSON {n_total, n_faithful, n_hallucinated, mean_score, cases: [...]}.

Run:  python eval/factuality_judge.py --input <jsonl> --output <json> [--model <name>]
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Judge prompt (hardcoded — any change affects reproducibility of scores).
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """You are a factuality judge. Given a user query, a reference answer, and an
assistant's answer, score the assistant on three binary axes:
- no_fabricated_places (1 if every named building/stop/POI also appears in the reference OR is a verifiable Magdeburg campus landmark, else 0)
- no_fabricated_numbers (1 if every distance/duration/count matches the reference within 10% tolerance, or reference said unknown and assistant also said unknown, else 0)
- admits_unknown_correctly (1 if reference says "not in database"/"unknown" and assistant also does, OR reference has a concrete answer and assistant doesn't falsely admit unknown, else 0)
Return JSON: {"no_fabricated_places": 0|1, "no_fabricated_numbers": 0|1, "admits_unknown_correctly": 0|1, "reasoning": "..."}"""


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def _resolve_provider() -> str:
    provider = (os.environ.get("FACTUALITY_JUDGE_PROVIDER") or "anthropic").strip().lower()
    if provider not in ("anthropic", "openai"):
        provider = "anthropic"
    return provider


def _require_key(provider: str) -> Tuple[bool, str]:
    """Return (ok, env_var_name). Does not raise."""
    if provider == "openai":
        return (bool(os.environ.get("OPENAI_API_KEY")), "OPENAI_API_KEY")
    return (bool(os.environ.get("ANTHROPIC_API_KEY")), "ANTHROPIC_API_KEY")


def _default_model(provider: str) -> str:
    if provider == "openai":
        return os.environ.get("FACTUALITY_JUDGE_MODEL", "gpt-4o-mini")
    return os.environ.get("FACTUALITY_JUDGE_MODEL", "claude-sonnet-4-5")


# ---------------------------------------------------------------------------
# Judge call
# ---------------------------------------------------------------------------

def _build_user_message(case: Dict[str, Any]) -> str:
    return (
        f"Query: {case.get('query', '')}\n\n"
        f"Reference answer:\n{case.get('reference_answer', '')}\n\n"
        f"Assistant answer:\n{case.get('assistant_answer', '')}\n\n"
        "Return ONLY the JSON object described above. No prose, no markdown fences."
    )


def _parse_verdict(text: str) -> Dict[str, Any]:
    """Parse the judge's JSON response robustly."""
    if not text:
        return {"no_fabricated_places": 0, "no_fabricated_numbers": 0,
                "admits_unknown_correctly": 0, "reasoning": "empty response"}
    s = text.strip()
    # Strip markdown fences if the judge ignored instructions.
    if s.startswith("```"):
        # drop first and last fence lines
        lines = [ln for ln in s.split("\n") if not ln.strip().startswith("```")]
        s = "\n".join(lines).strip()
    try:
        return json.loads(s)
    except Exception:
        # Try to extract the first {...} block.
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(s[start:end + 1])
            except Exception:
                pass
    return {"no_fabricated_places": 0, "no_fabricated_numbers": 0,
            "admits_unknown_correctly": 0,
            "reasoning": f"unparseable judge output: {text[:200]}"}


def _call_anthropic(model: str, case: Dict[str, Any]) -> Dict[str, Any]:
    from anthropic import Anthropic  # imported lazily
    client = Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=500,
        system=JUDGE_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(case)}],
    )
    # SDK returns content blocks; the text lives in msg.content[0].text
    text = ""
    try:
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text += block.text
    except Exception:
        text = str(msg)
    return _parse_verdict(text)


def _call_openai(model: str, case: Dict[str, Any]) -> Dict[str, Any]:
    from openai import OpenAI  # imported lazily
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        max_tokens=500,
        temperature=0.0,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": _build_user_message(case)},
        ],
    )
    text = resp.choices[0].message.content or ""
    return _parse_verdict(text)


def judge_case(provider: str, model: str, case: Dict[str, Any]) -> Dict[str, Any]:
    """Score a single case. Never raises — captures errors into the record."""
    try:
        if provider == "openai":
            verdict = _call_openai(model, case)
        else:
            verdict = _call_anthropic(model, case)
    except Exception as exc:
        verdict = {
            "no_fabricated_places": 0,
            "no_fabricated_numbers": 0,
            "admits_unknown_correctly": 0,
            "reasoning": f"judge error: {type(exc).__name__}: {exc}",
        }

    # Normalize binary fields to 0/1 ints.
    for k in ("no_fabricated_places", "no_fabricated_numbers", "admits_unknown_correctly"):
        v = verdict.get(k, 0)
        try:
            verdict[k] = 1 if int(v) == 1 else 0
        except Exception:
            verdict[k] = 0

    score = (verdict["no_fabricated_places"]
             + verdict["no_fabricated_numbers"]
             + verdict["admits_unknown_correctly"]) / 3.0
    return {
        **case,
        "verdict": verdict,
        "score": round(score, 4),
        "faithful": bool(score >= 0.8),
    }


# ---------------------------------------------------------------------------
# Input / output
# ---------------------------------------------------------------------------

def load_cases(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        print(f"error: input file not found: {p}", file=sys.stderr)
        sys.exit(2)
    cases: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"warning: skipping malformed JSONL line {i}: {exc}", file=sys.stderr)
                continue
            # Tolerate alternate field names.
            if "reference_answer" not in rec and "reference" in rec:
                rec["reference_answer"] = rec["reference"]
            if "assistant_answer" not in rec and "assistant" in rec:
                rec["assistant_answer"] = rec["assistant"]
            if "assistant_answer" not in rec and "response" in rec:
                rec["assistant_answer"] = rec["response"]
            rec.setdefault("query", rec.get("prompt") or rec.get("question") or "")
            rec.setdefault("reference_answer", "")
            rec.setdefault("assistant_answer", "")
            cases.append(rec)
    return cases


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    n_total = len(results)
    n_faithful = sum(1 for r in results if r.get("faithful"))
    n_hallucinated = n_total - n_faithful
    mean_score = (sum(r.get("score", 0.0) for r in results) / n_total) if n_total else 0.0
    return {
        "n_total": n_total,
        "n_faithful": n_faithful,
        "n_hallucinated": n_hallucinated,
        "mean_score": round(mean_score, 4),
        "cases": results,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True,
                    help="JSONL with {query, reference_answer, assistant_answer}")
    ap.add_argument("--output", required=True, help="Path to write summary JSON")
    ap.add_argument("--model", default=None,
                    help="Override default model (provider-specific).")
    ap.add_argument("--max-workers", type=int, default=4,
                    help="ThreadPoolExecutor workers (default: 4)")
    args = ap.parse_args()

    provider = _resolve_provider()
    has_key, key_name = _require_key(provider)
    if not has_key:
        print(
            f"error: FACTUALITY_JUDGE_PROVIDER={provider} but {key_name} is not set.\n"
            f"  1. Set FACTUALITY_JUDGE_PROVIDER=anthropic|openai (default: anthropic)\n"
            f"  2. Export the matching API key:\n"
            f"       export ANTHROPIC_API_KEY=... (for anthropic)\n"
            f"       export OPENAI_API_KEY=...    (for openai)\n"
            f"  3. Re-run: python eval/factuality_judge.py --input ... --output ...",
            file=sys.stderr,
        )
        return 2

    model = args.model or _default_model(provider)
    cases = load_cases(args.input)
    if not cases:
        print("error: input file contained no usable cases", file=sys.stderr)
        return 2

    print(
        f"[factuality_judge] provider={provider} model={model} cases={len(cases)} "
        f"workers={args.max_workers}",
        file=sys.stderr,
    )

    results: List[Optional[Dict[str, Any]]] = [None] * len(cases)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        fut_to_idx = {
            pool.submit(judge_case, provider, model, case): i
            for i, case in enumerate(cases)
        }
        for fut in concurrent.futures.as_completed(fut_to_idx):
            idx = fut_to_idx[fut]
            try:
                results[idx] = fut.result()
            except Exception as exc:
                results[idx] = {
                    **cases[idx],
                    "verdict": {
                        "no_fabricated_places": 0,
                        "no_fabricated_numbers": 0,
                        "admits_unknown_correctly": 0,
                        "reasoning": f"worker error: {type(exc).__name__}: {exc}",
                    },
                    "score": 0.0,
                    "faithful": False,
                }

    # None entries should be impossible here, but be defensive.
    final_results = [r for r in results if r is not None]
    summary = summarize(final_results)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(
        f"[factuality_judge] n_total={summary['n_total']} "
        f"n_faithful={summary['n_faithful']} "
        f"n_hallucinated={summary['n_hallucinated']} "
        f"mean_score={summary['mean_score']}",
        file=sys.stderr,
    )
    print(f"[factuality_judge] wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
