from datetime import datetime, timedelta, timezone

from agent.temporal import extract_topic, parse_explicit_date, parse_time_window

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 11, 9, 30, tzinfo=IST)


def test_yesterday_window():
    start, end, label = parse_time_window("what did I ask yesterday?", NOW)
    assert (start.isoformat(), end.isoformat(), label) == ("2026-11-10", "2026-11-11", "yesterday")


def test_today_window():
    start, end, _ = parse_time_window("what did we discuss today", NOW)
    assert start.isoformat() == "2026-11-11" and end.isoformat() == "2026-11-12"


def test_last_n_days_window():
    start, end, label = parse_time_window("what did I ask in the last 3 days", NOW)
    assert start.isoformat() == "2026-11-09" and end.isoformat() == "2026-11-12"
    assert label == "the last 3 days"


def test_explicit_dates():
    assert parse_explicit_date("on 2026-11-05", NOW).isoformat() == "2026-11-05"
    assert parse_explicit_date("on 5 November 2026", NOW).isoformat() == "2026-11-05"
    assert parse_explicit_date("on November 5", NOW).isoformat() == "2026-11-05"
    start, _, label = parse_time_window("what did I ask on 2026-11-05", NOW)
    assert start.isoformat() == "2026-11-05" and "2026-11-05" in label


def test_no_window():
    assert parse_time_window("hello there", NOW) is None


def test_extract_topic():
    assert extract_topic("when did I ask about bittorrent?") == "bittorrent"
    assert extract_topic("did I ever ask about MeshSync pairing") == "meshsync pairing"
