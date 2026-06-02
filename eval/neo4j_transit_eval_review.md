# Transit Routing Eval — Review

Model: `mistral-large-3-675b-instruct-2512` · 35 questions · `find_transit_route` tool available.

---

## Score summary

| Status | Count | Questions |
|---|---|---|
| ✅ OK | 30 | Q2-3, Q6-14, Q16-19, Q21-35 |
| ⚠️ Partial | 2 | Q15 (no route found, fallback), Q20 (unresolvable "Stadtfeld") |
| ⏱ Timeout | 3 | Q1, Q4, Q5 |

**86% clean pass rate (91% including partials). 0 errors.**

---

## Key findings

### 1. Agent consistently uses `find_transit_route` — prompt rule works

All 32 answered questions used `find_transit_route`. The agent correctly reaches for the tool instead of manually writing NEXT_STOP path queries. This is exactly the behavior we wanted.

Complex scenarios (Q30 Zoo→Turkish food→Hbf, Q35 3-leg day plan) correctly combined `find_transit_route` with `execute_cypher` and `sample_values` for the non-routing parts.

### 2. Three timeouts on SIMPLE questions — LLM stalling, not tool failure

Q1 (Building 3→Hauptbahnhof), Q4 (library→Hasselbachplatz), Q5 (PENNY→Hauptbahnhof) all timed out at 120s with zero tool calls completed. These are Tier A (easiest) questions.

**Root cause hypothesis:** the LLM spent 120s generating a response (possibly looping in its reasoning) without ever calling a tool. This is a model-level stall, not a tool or DB issue — similar questions (Q2, Q6, Q8) completed in 4-20s.

**Fix:** add a "must call a tool within first response" constraint, or increase timeout to 180s, or retry on timeout.

### 3. `shortestPath()` produces excessive transfers — confirmed

| Q | Route | Transfers | Should be |
|---|---|---|---|
| Q13 | Kannenstieg → Reform | **12** | ~2 (Tram 1 to center, Tram 9 to Reform) |
| Q14 | Herrenkrug → Diesdorf | **9** | ~1 (Tram 6 direct or 1 transfer) |
| Q16 | Rothensee → Leipziger Chaussee | **9** | ~2 |
| Q11 | ENERCON → Wissenschaftshafen | **5** | ~1-2 |
| Q19 | Messegelände → Zoo | **6** | ~1-2 |

`shortestPath()` minimizes hops, not transfers. At shared stops it freely jumps between lines, producing routes with 5-12 transfers that no human would take.

**This is the single biggest quality issue.** Routes are technically valid (all stops connected) but practically unusable.

**Fix (Tier 2):** Use `allShortestPaths()` and post-select the path with fewest line changes. Or: try single-line paths first, fall back to shortestPath only when no direct line exists.

### 4. Successful complex scenarios

| Q | Scenario | Result |
|---|---|---|
| Q21 | Building 3 → Building 22 | ✅ Tram 1→2, 4 stops, 1 transfer, 299m walk |
| Q22 | IMIQ → Faculty of CS | ✅ Bus 73→Tram 2, 4 stops, 1 transfer |
| Q23 | Faculty of Economics → Speicher B | ✅ Bus 73 direct, 0 transfers |
| Q27 | Library → IMIQ | ✅ Bus 73 direct, 0 transfers |
| Q34 | Round trip Building 5 ↔ Alter Markt | ✅ Both legs via Tram 1, 0 transfers |
| Q35 | 3-leg day plan (Hbf→CS→Mensa→Hbf) | ✅ 3 separate route calls, all resolved |

Campus-local routes work well because stops are closer and fewer line-hop opportunities exist.

### 5. Name resolution handles edge cases

- **Building aliases:** "Building 3" → Building 03 → Faculty of EE/IT → nearest stop ✅
- **POI names:** "Izgaram" → nearest stop ✅, "PENNY" → nearest stop (timed out for other reasons)
- **Ambiguous names:** "Hauptbahnhof" → Magdeburg Hauptbahnhof/Kölner Platz ✅
- **Non-existent area:** "Stadtfeld" → no stop found → agent adaptively fell back to Cypher (Q20) ✅
- **No route:** Cracau → Westerhüsen → tool returned error → agent tried Cypher fallback (Q15) ✅

---

## Priority improvements

### P0 — Transfer optimization (biggest quality win)
Replace `shortestPath()` with a two-pass approach:
1. First try: check if origin and destination share a line → single-line path (0 transfers)
2. Second try: `allShortestPaths()` → pick path with fewest distinct lines

### P1 — Timeout investigation
Q1, Q4, Q5 timed out on simple questions. Need to check if:
- LLM is stalling before tool call (likely)
- Tool resolution is hanging (unlikely — same inputs work in other Qs)

### P2 — No-route fallback
Q15 (Cracau→Westerhüsen) got no route from `shortestPath()`. Could mean the NEXT_STOP graph isn't fully connected in that direction. Tool should try reverse direction or suggest walking.
