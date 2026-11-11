"""The ONE tool: web_search.

Backends, in priority order: Tavily (env key) -> Serper (env key) ->
ddgs package -> DuckDuckGo HTML via stdlib urllib (zero-key default).
Results are cached in SQLite with a TTL; a repeat query inside the TTL
never touches the network.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Callable


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    date: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SearchResult":
        return cls(d.get("title", ""), d.get("url", ""), d.get("snippet", ""), d.get("date"))


Fetcher = Callable[[str, int], list[SearchResult]]


class SearchCache:
    def __init__(self, path: str = "memory.db", ttl_seconds: int = 900):
        self.ttl = ttl_seconds
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS search_cache(
                 query TEXT PRIMARY KEY, results TEXT NOT NULL, fetched_at REAL NOT NULL)"""
        )
        self.conn.commit()

    @staticmethod
    def _norm(query: str) -> str:
        return re.sub(r"\s+", " ", query.strip().lower())

    def get(self, query: str, now: float | None = None) -> list[SearchResult] | None:
        now = time.time() if now is None else now
        row = self.conn.execute(
            "SELECT results, fetched_at FROM search_cache WHERE query=?",
            (self._norm(query),),
        ).fetchone()
        if not row or now - row[1] > self.ttl:
            return None
        return [SearchResult.from_dict(d) for d in json.loads(row[0])]

    def put(self, query: str, results: list[SearchResult], now: float | None = None) -> None:
        now = time.time() if now is None else now
        self.conn.execute(
            "INSERT OR REPLACE INTO search_cache(query, results, fetched_at) VALUES (?,?,?)",
            (self._norm(query), json.dumps([r.to_dict() for r in results]), now),
        )
        self.conn.commit()


class WebSearch:
    """Callable search tool with injectable fetcher (for offline tests)."""

    def __init__(self, cache: SearchCache | None = None, fetcher: Fetcher | None = None):
        self.cache = cache
        self.fetcher = fetcher or default_fetcher

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        if self.cache:
            hit = self.cache.get(query)
            if hit is not None:
                return hit[:k]
        results = self.fetcher(query, k)
        if self.cache:
            self.cache.put(query, results)
        return results[:k]

    __call__ = search


# -- backends ------------------------------------------------------------

def _http_json(url: str, payload: dict, headers: dict, timeout: int = 10) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_tavily(query: str, k: int, api_key: str) -> list[SearchResult]:
    data = _http_json("https://api.tavily.com/search",
                      {"query": query, "max_results": k, "search_depth": "basic"},
                      {"Authorization": f"Bearer {api_key}"})
    return [SearchResult(r.get("title", ""), r.get("url", ""), r.get("content", ""),
                         r.get("published_date")) for r in data.get("results", [])]


def fetch_serper(query: str, k: int, api_key: str) -> list[SearchResult]:
    data = _http_json("https://google.serper.dev/search", {"q": query, "num": k},
                      {"X-API-KEY": api_key})
    return [SearchResult(r.get("title", ""), r.get("link", ""), r.get("snippet", ""),
                         r.get("date")) for r in data.get("organic", [])]


def fetch_ddgs(query: str, k: int) -> list[SearchResult]:
    from ddgs import DDGS  # optional dependency
    with DDGS() as ddgs:
        rows = list(ddgs.text(query, max_results=k))
    return [SearchResult(r.get("title", ""), r.get("href", ""), r.get("body", ""))
            for r in rows]


class _DDGParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[SearchResult] = []
        self._cur: dict | None = None
        self._field: str | None = None

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "")
        if tag == "a" and "result__a" in cls:
            href = dict(attrs).get("href", "")
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            url = qs.get("uddg", [href])[0]
            self._cur = {"title": "", "url": url, "snippet": ""}
            self._field = "title"
        elif tag == "a" and "result__snippet" in cls and self._cur is not None:
            self._field = "snippet"

    def handle_data(self, data):
        if self._cur is not None and self._field:
            self._cur[self._field] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._field == "snippet" and self._cur is not None:
            self.results.append(SearchResult(**self._cur))
            self._cur, self._field = None, None
        elif tag == "a" and self._field == "title":
            self._field = None


def fetch_ddg_html(query: str, k: int) -> list[SearchResult]:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    req = urllib.request.Request(url, headers={"User-Agent": "one-tool-agent/0.1"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        parser = _DDGParser()
        parser.feed(resp.read().decode("utf-8", "ignore"))
    return parser.results[:k]


def default_fetcher(query: str, k: int) -> list[SearchResult]:
    import os
    if os.environ.get("TAVILY_API_KEY"):
        return fetch_tavily(query, k, os.environ["TAVILY_API_KEY"])
    if os.environ.get("SERPER_API_KEY"):
        return fetch_serper(query, k, os.environ["SERPER_API_KEY"])
    try:
        return fetch_ddgs(query, k)
    except Exception:
        return fetch_ddg_html(query, k)
