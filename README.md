# one-tool-agent

A chat agent with **exactly one tool — web search**. It answers fast (memory
questions never touch the network; factual questions cost one cached search),
gets things right (answers grounded in retrieved sources, with numbered
citations), and **remembers what you asked and when** (every turn is stored
with a timestamp and can be recalled by topic or by date).

See **[DESIGN.md](DESIGN.md)** for the architecture, routing, memory and
latency/accuracy design.

## Quickstart

```bash
git clone https://github.com/x20surya/one-tool-agent.git
cd one-tool-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # optional: ddgs gives better zero-key results
python -m agent --ask "what is the latest news on the Chandrayaan programme?"
```

That works with **zero API keys** (DuckDuckGo search + extractive cited
answers). For LLM-written answers, copy `.env.example` to `.env`, set
`LLM_API_KEY` (OpenAI, Groq, or a local Ollama needs no key), and re-run.

Interactive mode: `python -m agent` (or `python chat.py`).

## Example session

```
you> what is the latest Python version?
agent> Here is what the top sources say about "what is the latest Python version?":
       - Python 3.14 was released in October 2025 ... [1]
         Source [1]: Python 3.14 released (2025-10-07) — https://www.python.org/downloads/
       [812 ms · route=search · sources=5]

you> when did I ask about bittorrent?
agent> You asked about bittorrent 1 time(s):
       - 2026-11-10 20:14 IST — "how does a bittorrent client work?"
       [3 ms · route=memory · sources=0]

you> what did I ask yesterday?
agent> Here is what you asked yesterday:
       - 2026-11-10 20:14 IST — "how does a bittorrent client work?"
       [2 ms · route=memory · sources=0]
```

## Configuration (env vars)

| Var | Default | Meaning |
|---|---|---|
| `LLM_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` | — | LLM key; unset = extractive mode |
| `LLM_BASE_URL` / `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint (incl. Ollama) |
| `LLM_MODEL` | `gpt-4o-mini` | Model name |
| `TAVILY_API_KEY` / `SERPER_API_KEY` | — | Optional higher-quality search backends |
| `ONE_TOOL_DB` | `memory.db` | SQLite file for memory + search cache |
| `SEARCH_CACHE_TTL` | `900` | Search cache TTL, seconds |

## Tests

```bash
pip install pytest
python -m pytest -q     # fully offline
```

## Layout

```
agent/    router.py · search.py (the one tool) · memory.py · temporal.py
          llm.py · core.py · cli.py
tests/    offline pytest suite
DESIGN.md design, trade-offs, failure modes, evaluation
```
