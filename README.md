Dashbot — The Magdeburg Campus Assistant
Ask a city anything.

Dashbot is an AI assistant that knows Magdeburg, buildings on the OVGU campus, tram stops, parking garages and what the Mensa is serving today. It answers in plain language, draws routes on a live map, and reads its answers out loud if you ask it to.

Under the hood it's a single LLM agent wired to a knowledge graph and a live IoT sensor network through MCP, a setup that's part chatbot, part digital twin.

 What it can do
"Where is Building 5?" — resolves campus buildings, lecture halls, POIs, and streets from a Neo4j knowledge graph built from OpenStreetMap data, and drops a pin on the map.
"How do I get from Hauptbahnhof to the university?" plans transit routes over the tram/bus network graph, and walking/cycling/driving routes via OpenRouteService, rendered as route cards with geometry on the map.
"What's the temperature right now?"  live weather, parking availability, air quality, traffic flow, and Elbe water levels straight from the city's FIWARE IoT context broker.
"What's in the Mensa today?" yes, including the daily menu.
Location-aware, share your position and it quietly finds your nearest stop, so "how do I get home from here" just works.
Talks back, optional text-to-speech, streamed paragraph by paragraph while the answer is still being written.
How it thinks
One ReAct agent (a reasoning LLM, gpt-5.4-thinking by default) owns the entire tool surface. No supervisor, no agent hand-offs, the model's native tool-calling loop does the routing, fans out calls in parallel, and composes the final answer.

The tools live in four MCP servers, each a separate stdio subprocess with a single responsibility:

                        ┌──────────────────────────────┐
  Browser widget  ───►  │   FastAPI  (api.py)          │
  (SSE token stream)    │   sessions · rate limiting   │
                        │   PII redaction · caching    │
                        └──────────────┬───────────────┘
                                       │
                        ┌──────────────▼───────────────┐
                        │   LangGraph ReAct agent      │
                        │   (one LLM, all the tools)   │
                        └──┬─────────┬─────────┬───────┘
                           │   MCP   │  (stdio)│
            ┌──────────────▼──┐ ┌────▼─────┐ ┌─▼──────────────┐ ┌────────────────┐
            │  neo4j-campus   │ │ fiware-  │ │    routing     │ │ context-bridge │
            │  buildings,     │ │ sensors  │ │  ORS walking / │ │ "what's near   │
            │  stops, POIs,   │ │ weather, │ │  cycling /     │ │  X?" — graph + │
            │  transit lines  │ │ parking, │ │  driving       │ │  sensors + ORS │
            │                 │ │ traffic  │ │                │ │  in one call   │
            └───────┬─────────┘ └────┬─────┘ └───────┬────────┘ └───────┬────────┘
                    │                │               │                  │
               Neo4j graph      FIWARE Orion    OpenRouteService   (all three)
              (knowledge)      (live city IoT)    (routing API)
The division of labor is strict and deliberate: the graph server answers "what exists and where" (static knowledge), FIWARE answers "what's happening right now" (live readings), routing answers "how do I get there", and the context bridge fuses all three for "what's around X?" questions in a single round-trip.

The supporting cast
Piece	What it does
Token streaming	Answers stream word-by-word over SSE, with <think>…</think> reasoning spans stripped on the fly and heartbeats keeping the connection warm during tool calls.
Semantic cache	Repeated questions (even paraphrased — cosine similarity ≥ 0.88) skip the LLM entirely. Keys are composite (query, user, location bucket) so one user's "parking near me" never leaks to another.
Embeddings	One shared BAAI/bge-base-en-v1.5 sentence-transformer per process, behind an LRU so hot queries never re-encode.
Place resolver	Fuzzy + embedding-based matching so "hauptbanhof" (typo and all) still finds the Hauptbahnhof.
Session security	Per-session bearer tokens (constant-time compared), 30-min idle expiry, per-IP rate limiting (Redis-backed when available).
PII hygiene	Emails, phone numbers, and street addresses are redacted before anything is logged or replayed into LLM context.
Map widget	A zero-dependency embeddable JS widget (static/dashbot-widget.js) — chat bubble, streaming text, map pins, route polylines, TTS. Drop it into any page.

Where the knowledge comes from
The ingestion/ pipeline builds the Neo4j graph from raw city data:

downloaders/  pull buildings, streets, and POIs from OpenStreetMap.
loaders/ — batch-load them into Neo4j with embeddings.
linkers/ — the clever part: spatially link buildings ↔ streets ↔ stops ↔ POIs, detect duplicates, and resolve ambiguous matches so the graph is connected, not just populated.
There's also a proper eval harness (eval/) with an LLM factuality judge and adversarial test sets — typos, ambiguous place names ("Hauptbahnhof" the stop vs. the building), out-of-domain questions, and null-data edge cases — plus threshold sweeps that picked the cache/resolver cutoffs from data instead of vibes.
