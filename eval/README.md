# Eval

Test suite for the Dashbot Magdeburg Campus Assistant. All files here are used to detect hallucinations, refusal failures, threshold regressions, and factuality drift.

## JSONL test files

| File | What it tests | Expected behavior |
|---|---|---|
| `eval_out_of_domain.jsonl` | Jokes, math, unrelated cities, politics, scheduling. | Assistant refuses and redirects to campus/mobility scope. |
| `eval_null_properties.jsonl` | Buildings that resolve cleanly but whose property (hours, capacity, accessibility) is absent in the database. | Assistant says "I don't have ... in the database" — does NOT guess. |
| `eval_fusion.jsonl` | Queries that need both Neo4j (location) and the knowledge base (IMIQ / OVGU facts). | Assistant combines both without contradiction; cites only KB items with score >= 0.65. |
| `eval_typos.jsonl` | Misspelled building/stop names (e.g. `Rectorat`, `Mechnical Engineering`). | Resolver still picks the right entity via `TYPO_FALLBACK=0.30`. |
| `eval_hauptbahnhof_ambiguity.jsonl` | The two Magdeburg Hauptbahnhof stops (`/Kölner Platz` vs `/Willy-Brandt-Platz`). | Assistant either asks which one, or lists both — NEVER silently picks one. |

Each line is a JSON object. Common fields:
- `id` — stable identifier for diffing runs
- `query` — user-facing prompt
- `expected_behavior` — one of `refuse_out_of_scope`, `admit_unknown`, `resolve_to_<entity>`, `disambiguate`, `answer_with_fusion`
- `must_contain` / `must_not_contain` — substring assertions on the synthesized answer

## Scripts

### `threshold_sweep.py`

Ablation over `KB_MIN_SCORE` x `BUILDING_EXACT`. Writes `eval/reports/threshold_sweep_<ts>.md` + a JSON sidecar. Runs with the live resolvers when `NEO4J_URI` and `OPENAI_API_KEY` are present; otherwise degrades to a deterministic mock — so it always runs in CI.

```bash
python eval/threshold_sweep.py                                 # built-in 20 probes
python eval/threshold_sweep.py --queries eval/eval_typos.jsonl # swap probe set
python eval/threshold_sweep.py --dry-run                       # force mocked runner
```

### `factuality_judge.py`

LLM-judge factuality scorer. Input JSONL with `{query, reference_answer, assistant_answer}`; output summary JSON with `n_total`, `n_faithful`, `n_hallucinated`, `mean_score`, `cases[]`. Runs 4 judges in parallel via `ThreadPoolExecutor`.

```bash
# Anthropic (default)
export ANTHROPIC_API_KEY=sk-ant-...
python eval/factuality_judge.py --input eval_runs/latest.jsonl --output eval/reports/factuality.json

# OpenAI
export FACTUALITY_JUDGE_PROVIDER=openai
export OPENAI_API_KEY=sk-...
python eval/factuality_judge.py --input eval_runs/latest.jsonl --output eval/reports/factuality.json --model gpt-4o-mini
```

The judge scores each case on three binary axes: no fabricated places, no fabricated numbers, admits unknown correctly. A case is `faithful` iff `score >= 0.8` (i.e. 3/3 binaries; 2/3 is flagged as hallucinated).

### `neo4j_eval.py`, `neo4j_eval_transit.py`

Pre-existing graph-specific evals (not covered by this doc).

## Conventions

- New evals go into a topical JSONL here; keep ids monotonically increasing per file.
- When adding a new data source or intent, see `DATA_ADDITION_PROMPT.md` → "Guardrails" for the minimum number of eval cases required.
- Reports written by the scripts above land in `eval/reports/` (gitignored unless you intentionally commit a baseline).
