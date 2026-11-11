# Design — one-tool-agent

## Goals

1. **One tool only.** The agent may call exactly one external tool: `web_search`.
   No calculators, no code execution, no browsing/fetch API distinct from search.
2. **Fast.** Memory questions never touch the network or an LLM. Factual
   questions cost exactly one search, over a small top-k context, with repeat
   queries served from a 15-minute cache. Every REPL turn prints its latency.
3. **Right.** Searched answers are grounded only in retrieved snippets and
   carry numbered citations a reader can audit. When sources don't support an
   answer, the agent says so instead of guessing.
4. **It remembers what you asked, and when.** Every turn is persisted with a
   timestamp; temporal recall ("when did I ask about X?", "what did I ask
   yesterday?") is answered deterministically from that store.
5. **Runs with zero keys.** A reviewer with no API key gets the full loop:
   DuckDuckGo search + extractive, cited answers + complete memory recall.

## Non-goals

- Multi-tool planning, browsing full pages, or acting on the user's behalf.
- Semantic/vector memory. Episodic recall here is lexical + temporal, on purpose:
  it is exact, inspectable, and has no embedding dependency.
- Streaming tokens (the CLI prints whole answers; latency is measured per turn).

## Architecture

```
                ┌────────────┐
   user text ──▶│   Router   │  classify() — regex/heuristic, ~0 ms
                └─────┬──────┘
          ┌───────────┼────────────┐
          ▼           ▼            ▼
      memory        search       direct
   ┌────────────┐ ┌─────────┐ ┌──────────────┐
   │ Episodic   │ │ ONE     │ │ LLM with     │
   │ store      │ │ web_    │ │ recent-turn  │
   │ (SQLite +  │ │ search  │ │ context, or  │
   │ FTS5)      │ │ call    │ │ zero-key     │
   │ answered   │ │ (cache  │ │ fallback     │
   │ directly,  │ │ first)  │ └──────┬───────┘
   │ no LLM     │ └────┬────┘        │
   └─────┬──────┘      │ grounded    │
         │             ▼ synthesis   │
         │      (LLM if keyed, else  │
         │       extractive + cites) │
         └───────────┬───────────────┘
                     ▼
        persist user + assistant turns
        (ISO ts, UTC + local) — AFTER
        answering, so a memory question
        recalls prior turns, not itself
```

Modules: `agent/router.py` (classification), `agent/search.py` (the tool +
cache), `agent/memory.py` (episodic store), `agent/temporal.py` (date parsing),
`agent/llm.py` (stdlib-only OpenAI-compatible client), `agent/core.py`
(orchestration + extractive fallback), `agent/cli.py` (REPL / one-shot).

## The one-tool constraint, and why

Search is the highest-leverage single tool: it covers current events, prices,
release dates, documentation, and fact-checking — everything that goes stale
in model weights. Restricting the agent to one tool keeps the loop auditable
(one call site, one cache, one citation format) and removes tool-selection
errors entirely. Memory is *storage*, not a tool: it is internal state the
agent reads directly, the same way a chat app reads its own transcript.

## Routing logic

First match wins (`agent/router.py`):

1. **Memory patterns** — "what/when did I ask…", "did I ever ask…",
   "first/last thing I asked", "what did we discuss…" → memory fast path.
2. **Search patterns/hints** — "latest", "current", "price", "news",
   "capital of", "who is the current…", explicit years 2024–2026, etc.
3. **Direct** — greetings, explanations, creative tasks: stable knowledge
   the model (or the zero-key notice) can handle without retrieval.

Ambiguity policy: when a message could be either ("when did X happen?" vs
"when did *I ask about* X?"), the first-person patterns are checked first —
misrouting a memory question to search would both slow it down and answer
the wrong question.

## Memory schema + temporal queries

```sql
turns(id INTEGER PK, role TEXT, text TEXT, ts_utc TEXT, ts_local TEXT);
turns_fts USING fts5(text, turn_id UNINDEXED, role UNINDEXED);
search_cache(query TEXT PK, results TEXT, fetched_at REAL);
```

- Both UTC and local ISO-8601 timestamps are stored: UTC for ordering/sanity,
  local for calendar questions ("yesterday" is a local-calendar concept).
- **Temporal design** (`agent/temporal.py`, pure functions over `now`):
  relative windows — today, yesterday, last N days, last/this week — and
  explicit dates (`2026-11-05`, `5 November`, `November 5`) resolve to a
  `[start_date, end_date)` pair matched against `substr(ts_local,1,10)`.
- **Topic recall**: the question scaffolding is stripped
  ("when did I ask about ~bittorrent~?" → `bittorrent`) and the remainder is
  run as an FTS5 prefix query over user turns (LIKE fallback if FTS5 is
  unavailable). First/last questions read the ordered user-turn index directly.
- Memory answers are **formatted from stored timestamps**, never generated —
  they cannot hallucinate a date.

## Caching & latency budget

| Path | Budget | How |
|---|---|---|
| Memory | < 10 ms | local SQLite + FTS, no network, no LLM |
| Search, cache hit | < 20 ms | SQLite cache, 15-min TTL, normalised query key |
| Search, cache miss | 1 search RTT + 1 LLM call | one call, top-5 snippets only, small prompt |
| Direct | 1 LLM call (or 0 in zero-key mode) | last 6 turns of context, no more |

Cache key = lowercased, whitespace-collapsed query. TTL is configurable
(`SEARCH_CACHE_TTL`); 15 min balances freshness for news/prices against the
huge win on follow-up and repeat questions.

## Accuracy & citation strategy

- The LLM synthesis prompt instructs: *use only the provided sources, cite
  every factual claim with `[n]`, refuse if unsupported*. If a keyed model's
  reply drops citations, the source list is appended so claims stay auditable.
- Zero-key extractive mode quotes the top snippets verbatim (trimmed), each
  with its `[n]`, title, publication date when the backend provides one, and URL.
- Empty/thin results produce an explicit "the sources don't support an
  answer, so I won't guess" — in both modes.
- Search backends are ranked by result quality when keys exist
  (Tavily → Serper → ddgs → DuckDuckGo HTML); the zero-key default needs no signup.

## Trade-offs

- **Lexical (FTS) memory vs embeddings:** FTS misses paraphrases ("the torrent
  thing" won't match "bittorrent"). Accepted: recall stays exact, offline,
  dependency-free, and its failures are visible rather than silent.
- **Extractive fallback quality:** without an LLM key, answers are quoted
  snippets, not prose. Accepted: the repo must be reviewable end-to-end with
  zero keys; synthesis is a drop-in upgrade via one env var.
- **One search per turn:** multi-hop questions ("compare X's price in A vs B")
  get one broad search, not a research loop. Accepted for latency; the cache
  makes a user's follow-up refinement cheap.
- **Regex router vs LLM router:** an LLM router would catch more phrasings but
  adds a full model call to every turn — defeating the speed goal. The regexes
  cover the brief's canonical phrasings and fail toward `direct`, never toward
  a wrong memory answer.

## Failure modes

- **Search backend down / blocked:** the fetcher chain falls through
  (ddgs → DDG HTML); total failure returns no results and the agent refuses
  rather than guessing from weights.
- **LLM down or unkeyed:** silent fallback to extractive answers (search path)
  or a clear zero-key notice (direct path). Memory path is unaffected.
- **FTS5 missing in SQLite build:** detected at startup; LIKE fallback used.
- **Clock/timezone:** timestamps use the host's local tz; a user who travels
  gets calendar answers in the *new* local tz for old turns' stored local
  strings. Storing UTC alongside keeps a correct absolute record.
- **Cache staleness:** a fast-moving story can be up to 15 min stale; the TTL
  is one env var, and the trade-off is stated rather than hidden.

## Evaluation

- **Offline test suite** (`tests/`, pytest, no network): memory add/recall,
  FTS "when did I ask about X", temporal windows (today/yesterday/last-N/
  explicit dates), topic extraction, router classification (10 cases),
  search-cache hit avoiding a second fetcher call + TTL expiry, extractive
  citations, refusal on empty results, and the full agent memory flow with an
  exploding fetcher proving memory questions never search.
- **Manual smoke tests:** REPL session covering a cited search answer, a
  repeat query (cache-hit latency drop), "when did I ask about X", "what did
  I ask yesterday", and the first-question recall.
- **Latency:** per-turn footer in the REPL (`[N ms · route=… · sources=…]`)
  makes the budget above observable on every run.
