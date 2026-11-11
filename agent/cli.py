from __future__ import annotations

import argparse
import sys

from .config import Config
from .core import Agent
from .llm import LLMClient
from .memory import MemoryStore
from .search import SearchCache, WebSearch


def build_agent(db_path: str | None = None) -> Agent:
    cfg = Config.from_env()
    db = db_path or cfg.db_path
    memory = MemoryStore(db)
    searcher = WebSearch(cache=SearchCache(db, cfg.cache_ttl_seconds))
    llm = LLMClient(cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model)
    return Agent(memory, searcher, llm, top_k=cfg.search_top_k)


def _footer(agent_answer) -> str:
    return f"[{agent_answer.latency_ms} ms · route={agent_answer.route} · sources={len(agent_answer.sources)}]"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent", description="One-tool (web search) chat agent")
    ap.add_argument("--ask", help="One-shot question; omit for the interactive REPL")
    ap.add_argument("--db", help="SQLite memory DB path (default: memory.db or $ONE_TOOL_DB)")
    args = ap.parse_args(argv)

    agent = build_agent(args.db)
    if args.ask:
        ans = agent.handle(args.ask)
        print(ans.text)
        print(_footer(ans), file=sys.stderr)
        return 0

    dim = "\033[2m" if sys.stdout.isatty() else ""
    reset = "\033[0m" if dim else ""
    print("one-tool-agent — /exit to quit. I search the web for facts and remember what you asked, and when.")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text in {"/exit", "/quit", "exit", "quit"}:
            break
        ans = agent.handle(text)
        print(f"agent> {ans.text}")
        print(f"{dim}{_footer(ans)}{reset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
