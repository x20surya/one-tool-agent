"""Temporal parsing for memory questions.

Pure functions over a supplied ``now`` so they are trivially testable offline.
Windows are returned as ``(start_date, end_date_exclusive, label)`` using
local calendar dates.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def parse_explicit_date(text: str, now: datetime) -> date | None:
    t = text.lower()
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", t)
    if m:  # assume day/month/year (the user's locale convention)
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:\s+(20\d{2}))?\b", t)
    if m and m.group(2) in MONTHS:
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            return date(year, MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?\b", t)
    if m and m.group(1) in MONTHS:
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            return date(year, MONTHS[m.group(1)], int(m.group(2)))
        except ValueError:
            return None
    return None


def parse_time_window(text: str, now: datetime) -> tuple[date, date, str] | None:
    t = text.lower()
    today = now.date()
    if "today" in t or "this morning" in t or "this evening" in t:
        return today, today + timedelta(days=1), "today"
    if "yesterday" in t:
        return today - timedelta(days=1), today, "yesterday"
    m = re.search(r"last\s+(\d+)\s+days?", t)
    if m:
        n = int(m.group(1))
        return today - timedelta(days=n - 1), today + timedelta(days=1), f"the last {n} days"
    if "last week" in t or "past week" in t:
        return today - timedelta(days=6), today + timedelta(days=1), "the last 7 days"
    if "this week" in t:
        monday = today - timedelta(days=today.weekday())
        return monday, today + timedelta(days=1), "this week"
    explicit = parse_explicit_date(t, now)
    if explicit is not None:
        return explicit, explicit + timedelta(days=1), f"on {explicit.isoformat()}"
    return None


_MEMORY_FILLER = [
    r"when did i (ask|asked|say|said|mention|mentioned)( about| regarding)?",
    r"what did i (ask|asked|say|said|mention|mentioned)( about| regarding)?",
    r"(did|have) i (ask|asked|ever ask|mention|mentioned)( about| regarding)?",
    r"ask(ed)?( me)? about",
    r"\babout\b", r"\bmention(ed)?\b", r"\bdiscuss(ed)?\b",
    r"\bwhen\b", r"\bwhat\b", r"\bdid\b", r"\bi\b",
]


def extract_topic(text: str) -> str:
    """Strip the memory-question scaffolding, leaving the topic, e.g.
    'when did I ask about bittorrent?' -> 'bittorrent'."""
    t = text.lower().strip().rstrip("?.! ")
    for pattern in _MEMORY_FILLER:
        t = re.sub(pattern, " ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def format_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M %Z").strip()
