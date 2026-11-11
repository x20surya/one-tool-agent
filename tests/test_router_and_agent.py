from datetime import datetime, timedelta, timezone

import pytest

from agent.core import Agent, extractive_answer
from agent.llm import LLMClient
from agent.memory import MemoryStore
from agent.router import classify
from agent.search import SearchResult, WebSearch

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 11, 9, 30, tzinfo=IST)

FAKE_RESULTS = [
    SearchResult("Python 3.14 released", "https://www.python.org/downloads/",
                 "Python 3.14 was released in October 2025 with a faster interpreter.", "2025-10-07"),
    SearchResult("Release notes", "https://docs.python.org/3.14/whatsnew/",
                 "The whatsnew page lists the changes in Python 3.14.", None),
]


@pytest.mark.parametrize("text,route", [
    ("when did I ask about bittorrent?", "memory"),
    ("what did I ask yesterday?", "memory"),
    ("what was the first thing I asked?", "memory"),
    ("what did we discuss today?", "memory"),
    ("what is the latest news on the election?", "search"),
    ("what is the current price of bitcoin?", "search"),
    ("what is the capital of France?", "search"),
    ("hello", "direct"),
    ("explain recursion to me", "direct"),
    ("write a haiku about rain", "direct"),
])
def test_router_classification(text, route):
    assert classify(text) == route


def test_extractive_fallback_cites_sources():
    out = extractive_answer("when was python 3.14 released", FAKE_RESULTS)
    assert "[1]" in out and "https://www.python.org/downloads/" in out
    assert "2025-10-07" in out


def test_extractive_fallback_refuses_without_sources():
    out = extractive_answer("obscure question", [])
    assert "don't support" in out or "won't guess" in out


@pytest.fixture()
def agent(tmp_path):
    memory = MemoryStore(str(tmp_path / "a.db"))

    def exploding_fetcher(query, k):  # memory path must never search
        raise AssertionError("search must not be called for memory questions")

    llm = LLMClient("https://api.openai.com/v1", api_key="")  # unavailable
    a = Agent(memory, WebSearch(fetcher=exploding_fetcher), llm)
    yield a
    memory.close()


def test_agent_memory_flow_no_search_no_llm(agent):
    agent.handle("how does a bittorrent client work?", now=NOW - timedelta(days=1))
    ans = agent.handle("when did I ask about bittorrent?", now=NOW)
    assert ans.route == "memory"
    assert "bittorrent" in ans.text.lower()
    assert "2026-11-10" in ans.text  # answered with the stored timestamp
    first = agent.handle("what was the first thing I asked?", now=NOW)
    assert "bittorrent client" in first.text


def test_agent_memory_window_questions(agent):
    agent.handle("how does a bittorrent client work?", now=NOW - timedelta(days=1))
    agent.handle("explain recursion to me", now=NOW)
    yesterday = agent.handle("what did I ask yesterday?", now=NOW)
    assert yesterday.route == "memory" and "bittorrent client" in yesterday.text
    assert "recursion" not in yesterday.text
    today = agent.handle("what did I ask today?", now=NOW)
    assert "recursion" in today.text and "bittorrent" not in today.text


def test_agent_search_flow_uses_one_search(tmp_path):
    memory = MemoryStore(str(tmp_path / "s.db"))
    calls = {"n": 0}

    def fake_fetcher(query, k):
        calls["n"] += 1
        return FAKE_RESULTS

    llm = LLMClient("https://api.openai.com/v1", api_key="")
    a = Agent(memory, WebSearch(fetcher=fake_fetcher), llm)
    ans = a.handle("what is the latest Python release news?", now=NOW)
    assert ans.route == "search" and calls["n"] == 1
    assert "[1]" in ans.text and ans.sources == FAKE_RESULTS
    memory.close()
