"""Episodic memory: every turn in SQLite, with ISO timestamps and FTS5 search.

Schema
------
turns(id, role, text, ts_utc, ts_local)   -- ts_* are ISO-8601 strings
turns_fts(text, turn_id, role)            -- FTS5 index over turn text
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass
class Turn:
    id: int
    role: str  # "user" | "assistant"
    text: str
    ts_utc: datetime
    ts_local: datetime

    @property
    def when_local(self) -> str:
        from .temporal import format_ts
        return format_ts(self.ts_local)


class MemoryStore:
    def __init__(self, path: str = "memory.db"):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS turns(
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 role TEXT NOT NULL,
                 text TEXT NOT NULL,
                 ts_utc TEXT NOT NULL,
                 ts_local TEXT NOT NULL)"""
        )
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(text, turn_id UNINDEXED, role UNINDEXED)"
            )
            self._fts = True
        except sqlite3.OperationalError:
            self._fts = False
        self.conn.commit()

    # -- writes ---------------------------------------------------------
    def add_turn(self, role: str, text: str, when: datetime | None = None) -> Turn:
        when = when or datetime.now().astimezone()
        if when.tzinfo is None:
            when = when.astimezone()
        ts_utc = when.astimezone(timezone.utc)
        ts_local = when.astimezone()
        cur = self.conn.execute(
            "INSERT INTO turns(role, text, ts_utc, ts_local) VALUES (?,?,?,?)",
            (role, text, ts_utc.isoformat(), ts_local.isoformat()),
        )
        if self._fts:
            self.conn.execute(
                "INSERT INTO turns_fts(text, turn_id, role) VALUES (?,?,?)",
                (text, cur.lastrowid, role),
            )
        self.conn.commit()
        return Turn(cur.lastrowid, role, text, ts_utc, ts_local)

    # -- reads ----------------------------------------------------------
    def _rows(self, sql: str, params: tuple = ()) -> list[Turn]:
        out = []
        for rid, role, text, ts_utc, ts_local in self.conn.execute(sql, params):
            out.append(Turn(rid, role, text,
                            datetime.fromisoformat(ts_utc),
                            datetime.fromisoformat(ts_local)))
        return out

    def all_turns(self, role: str | None = None) -> list[Turn]:
        if role:
            return self._rows("SELECT * FROM turns WHERE role=? ORDER BY id", (role,))
        return self._rows("SELECT * FROM turns ORDER BY id")

    def first_user_turn(self) -> Turn | None:
        rows = self._rows("SELECT * FROM turns WHERE role='user' ORDER BY id LIMIT 1")
        return rows[0] if rows else None

    def last_user_turn(self) -> Turn | None:
        rows = self._rows("SELECT * FROM turns WHERE role='user' ORDER BY id DESC LIMIT 1")
        return rows[0] if rows else None

    def turns_between(self, start: date, end: date, role: str | None = None) -> list[Turn]:
        """Turns whose *local* date is in [start, end)."""
        sql = "SELECT * FROM turns WHERE substr(ts_local,1,10) >= ? AND substr(ts_local,1,10) < ?"
        params: list = [start.isoformat(), end.isoformat()]
        if role:
            sql += " AND role=?"
            params.append(role)
        return self._rows(sql + " ORDER BY id", tuple(params))

    def search(self, topic: str, role: str | None = "user") -> list[Turn]:
        """FTS5 lookup with a LIKE fallback. Returns matching turns, oldest first."""
        tokens = [tok for tok in re.findall(r"[a-z0-9]+", topic.lower()) if len(tok) > 1]
        if not tokens:
            return []
        if self._fts:
            query = " AND ".join(f'"{tok}"*' for tok in tokens)
            try:
                sql = ("SELECT t.* FROM turns_fts f JOIN turns t ON t.id = f.turn_id "
                       "WHERE turns_fts MATCH ?")
                params: list = [query]
                if role:
                    sql += " AND t.role=?"
                    params.append(role)
                rows = self._rows(sql + " ORDER BY t.id", tuple(params))
                if rows:
                    return rows
            except sqlite3.OperationalError:
                pass
        like = " AND ".join("lower(text) LIKE ?" for _ in tokens)
        sql = f"SELECT * FROM turns WHERE {like}"
        params = [f"%{tok}%" for tok in tokens]
        if role:
            sql += " AND role=?"
            params.append(role)
        return self._rows(sql + " ORDER BY id", tuple(params))

    def close(self) -> None:
        self.conn.close()
