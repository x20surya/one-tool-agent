"""Route classification — runs before anything expensive.

memory  -> answered directly from the episodic store (no LLM, no search)
search  -> factual / current / verifiable: exactly one web_search call
direct  -> conversational or stable general knowledge: LLM (or fallback)
"""
from __future__ import annotations

import re

MEMORY_PATTERNS = [
    r"\b(what|when|where) did i (ask|say|mention|tell)\b",
    r"\bdid i (ask|say|mention|ever ask)\b",
    r"\bhave i (asked|mentioned|said)\b",
    r"\bfirst thing i (asked|said)\b",
    r"\blast thing i (asked|said)\b",
    r"\bwhat did we (discuss|talk about|cover)\b",
    r"\bwhat have i asked\b",
    r"\bmy (previous|earlier|last|first) (question|message|ask)\b",
    r"\bremember when i\b",
    r"\bwhen did i\b",
    r"\bearlier (today|yesterday|this)\b.*\bi (asked|said)\b",
]

SEARCH_HINTS = [
    "latest", "current", "currently", "news", "today's", "price", "stock",
    "weather", "forecast", "exchange rate", "score", "who won", "election",
    "released", "release date", "capital of", "population of", "ceo of",
    "founded", "died", "born", "how tall is", "how old is", "how many people",
    "in 2024", "in 2025", "in 2026",
]

SEARCH_PATTERNS = [
    r"\bwho is the (current|present)\b",
    r"\bwhat is the (current|latest|price|population|capital)\b",
    r"\bwhen (did|was|is) .{0,40}\b(happen|born|founded|released|die|launch|start|end)",
]


def classify(text: str) -> str:
    t = text.lower().strip()
    for pat in MEMORY_PATTERNS:
        if re.search(pat, t):
            return "memory"
    for pat in SEARCH_PATTERNS:
        if re.search(pat, t):
            return "search"
    if any(hint in t for hint in SEARCH_HINTS):
        return "search"
    return "direct"
