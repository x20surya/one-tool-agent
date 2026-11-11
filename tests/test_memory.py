from datetime import datetime, timedelta, timezone

import pytest

from agent.memory import MemoryStore

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 10, 20, 0, tzinfo=IST)  # yesterday evening, IST


@pytest.fixture()
def store(tmp_path):
    s = MemoryStore(str(tmp_path / "m.db"))
    yield s
    s.close()


def test_add_and_recall_with_timestamps(store):
    turn = store.add_turn("user", "how does a bittorrent client work?", T0)
    assert turn.ts_utc == T0.astimezone(timezone.utc)
    assert turn.ts_local.date().isoformat() == "2026-11-10"
    got = store.all_turns(role="user")
    assert [t.text for t in got] == ["how does a bittorrent client work?"]


def test_first_and_last_user_turn(store):
    store.add_turn("user", "first question", T0)
    store.add_turn("assistant", "an answer", T0)
    store.add_turn("user", "second question", T0 + timedelta(hours=1))
    assert store.first_user_turn().text == "first question"
    assert store.last_user_turn().text == "second question"


def test_turns_between_dates(store):
    store.add_turn("user", "yesterday q", T0)
    store.add_turn("user", "today q", T0 + timedelta(days=1))
    rows = store.turns_between(T0.date(), T0.date() + timedelta(days=1), role="user")
    assert [t.text for t in rows] == ["yesterday q"]


def test_fts_search(store):
    store.add_turn("user", "tell me about meshsync pairing", T0)
    store.add_turn("user", "what is the weather in ranchi", T0)
    hits = store.search("meshsync")
    assert len(hits) == 1 and "meshsync" in hits[0].text
    assert store.search("nonexistenttopic") == []
