"""Agent orchestration: route -> (memory | one search | direct) -> persist."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from .llm import LLMClient
from .memory import MemoryStore, Turn
from .router import classify
from .search import SearchResult, WebSearch
from .temporal import extract_topic, format_ts, parse_time_window

GREETINGS = {"hi", "hello", "hey", "namaste", "thanks", "thank you", "ok", "okay"}


@dataclass
class Answer:
    text: str
    route: str
    latency_ms: int
    sources: list[SearchResult] = field(default_factory=list)


def extractive_answer(query: str, results: list[SearchResult]) -> str:
    """Zero-key fallback: answer only from retrieved snippets, cited."""
    if not results:
        return (f'I searched for "{query}" but the sources returned don\'t support '
                "an answer, so I won't guess.")
    lines = [f'Here is what the top sources say about "{query}":', ""]
    for i, r in enumerate(results, 1):
        snippet = re.sub(r"\s+", " ", r.snippet).strip()
        if len(snippet) > 280:
            snippet = snippet[:277].rsplit(" ", 1)[0] + "..."
        date = f" ({r.date})" if r.date else ""
        lines.append(f"- {snippet} [{i}]")
        lines.append(f"  Source [{i}]: {r.title}{date} — {r.url}")
    return "\n".join(lines)


class Agent:
    def __init__(self, memory: MemoryStore, searcher: WebSearch,
                 llm: LLMClient | None = None, top_k: int = 5):
        self.memory = memory
        self.searcher = searcher
        self.llm = llm
        self.top_k = top_k

    # -- main entry ------------------------------------------------------
    def handle(self, user_text: str, now: datetime | None = None) -> Answer:
        start = time.perf_counter()
        asked_at = now or datetime.now().astimezone()
        route = classify(user_text)
        sources: list[SearchResult] = []

        if route == "memory":
            text = self._answer_memory(user_text, asked_at)
        elif route == "search":
            sources = self.searcher.search(user_text, self.top_k)
            text = self._answer_search(user_text, sources)
        else:
            text = self._answer_direct(user_text)

        latency_ms = int((time.perf_counter() - start) * 1000)
        # Persist AFTER answering: a memory question must recall prior turns,
        # not itself.
        self.memory.add_turn("user", user_text, asked_at)
        self.memory.add_turn("assistant", text, datetime.now().astimezone())
        return Answer(text, route, latency_ms, sources)

    # -- memory fast path (no LLM, no search) ----------------------------
    def _answer_memory(self, text: str, now: datetime) -> str:
        t = text.lower()
        if "first thing" in t or "first question" in t or "my first" in t:
            turn = self.memory.first_user_turn()
            if not turn:
                return "You haven't asked me anything before this."
            return f'The first thing you asked was: "{turn.text}" — on {format_ts(turn.ts_local)}.'
        if "last thing" in t or "last question" in t or "most recent" in t:
            turn = self.memory.last_user_turn()
            if not turn:
                return "You haven't asked me anything before this."
            return f'The last thing you asked was: "{turn.text}" — on {format_ts(turn.ts_local)}.'

        window = parse_time_window(text, now)
        topic = extract_topic(text)
        temporal_words = {"today", "yesterday", "last", "this", "week", "days",
                          "day", "morning", "evening", "tonight", "on"}
        topic_tokens = topic.split()
        # A "topic" made only of temporal/numeric words ("today", "2026 11 05")
        # is really a date question, not a topic question.
        has_real_topic = any(tok not in temporal_words and not tok.isdigit()
                             for tok in topic_tokens)

        if window and not has_real_topic:
            return self._answer_window(window, discussed="discuss" in t)

        # "when did I ask about X" / "did I ask about X"
        if topic and ("when" in t or "did i" in t or "have i" in t) and "discuss" not in t:
            hits = self.memory.search(topic)
            if not hits:
                return f"I have no record of you asking about {topic}."
            listed = "\n".join(f'- {format_ts(h.ts_local)} — "{h.text}"' for h in hits)
            return f"You asked about {topic} {len(hits)} time(s):\n{listed}"

        if window:
            return self._answer_window(window, discussed="discuss" in t)

        if topic:
            hits = self.memory.search(topic)
            if hits:
                listed = "\n".join(f'- {format_ts(h.ts_local)} — "{h.text}"' for h in hits)
                return f"From your earlier questions about {topic}:\n{listed}"
        recent = self.memory.all_turns(role="user")[-5:]
        if not recent:
            return "You haven't asked me anything before this."
        listed = "\n".join(f'- {format_ts(x.ts_local)} — "{x.text}"' for x in recent)
        return f"Your most recent questions were:\n{listed}"

    def _answer_window(self, window, discussed: bool) -> str:
        start, end, label = window
        role = None if discussed else "user"
        turns = self.memory.turns_between(start, end, role=role)
        if not turns:
            return f"Nothing {'was discussed' if role is None else 'you asked'} {label}."
        listed = "\n".join(f'- {format_ts(x.ts_local)} — "{x.text}"' for x in turns)
        head = f"Here is what {'we discussed' if role is None else 'you asked'} {label}:"
        return f"{head}\n{listed}"

    # -- search path -------------------------------------------------------
    def _answer_search(self, query: str, results: list[SearchResult]) -> str:
        if self.llm and self.llm.available and results:
            context = "\n".join(
                f"[{i}] {r.title} ({r.date or 'no date'}) {r.url}\n{r.snippet}"
                for i, r in enumerate(results, 1))
            out = self.llm.complete([
                {"role": "system", "content":
                 "Answer using ONLY the sources provided. Cite every factual claim "
                 "with [n] markers matching the source numbers. If the sources do "
                 "not support an answer, say so explicitly. Be concise."},
                {"role": "user", "content": f"Question: {query}\n\nSources:\n{context}"},
            ])
            if out:
                if "[1]" not in out:  # keep citations auditable even if the model drops them
                    out += "\n\nSources:\n" + "\n".join(
                        f"[{i}] {r.title} — {r.url}" for i, r in enumerate(results, 1))
                return out
        return extractive_answer(query, results)

    # -- direct path -------------------------------------------------------
    def _answer_direct(self, text: str) -> str:
        if text.lower().strip().rstrip("!") in GREETINGS:
            return "Hello! Ask me anything — I'll search the web when facts matter, and I remember what you asked and when."
        if self.llm and self.llm.available:
            recent = self.memory.all_turns()[-6:]
            messages = [{"role": "system", "content":
                         "You are a concise, accurate chat assistant. Answer from "
                         "general knowledge; do not invent current facts."}]
            messages += [{"role": x.role, "content": x.text} for x in recent]
            messages.append({"role": "user", "content": text})
            out = self.llm.complete(messages)
            if out:
                return out
        return ("No LLM is configured (set LLM_API_KEY), so in zero-key mode I can "
                "still search the web for factual questions and recall what you "
                "asked and when — try a factual question, or \u201cwhen did I ask about ...?\u201d")
