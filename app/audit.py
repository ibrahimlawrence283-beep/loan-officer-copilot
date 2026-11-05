"""Append-only, hash-chained audit log (SQLite). Any edit to history breaks verification."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time


class AuditLog:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS audit (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, case_id TEXT NOT NULL,
                 actor TEXT NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL,
                 prev_hash TEXT NOT NULL, hash TEXT NOT NULL)"""
        )
        self._conn.commit()

    @staticmethod
    def _digest(prev: str, ts: float, case_id: str, actor: str, event: str, payload: str) -> str:
        return hashlib.sha256(f"{prev}|{ts}|{case_id}|{actor}|{event}|{payload}".encode()).hexdigest()

    def append(self, case_id: str, actor: str, event: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload or {}, sort_keys=True, default=str)
        with self._lock:
            row = self._conn.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
            prev = row[0] if row else "GENESIS"
            ts = time.time()
            h = self._digest(prev, ts, case_id, actor, event, body)
            cur = self._conn.execute(
                "INSERT INTO audit (ts, case_id, actor, event, payload, prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
                (ts, case_id, actor, event, body, prev, h),
            )
            self._conn.commit()
            return {"id": cur.lastrowid, "ts": ts, "case_id": case_id, "actor": actor,
                    "event": event, "payload": json.loads(body), "hash": h}

    def entries(self, case_id: str | None = None) -> list[dict]:
        q = "SELECT id, ts, case_id, actor, event, payload, prev_hash, hash FROM audit"
        args: tuple = ()
        if case_id:
            q += " WHERE case_id = ?"
            args = (case_id,)
        rows = self._conn.execute(q + " ORDER BY id", args).fetchall()
        return [{"id": r[0], "ts": r[1], "case_id": r[2], "actor": r[3], "event": r[4],
                 "payload": json.loads(r[5]), "prev_hash": r[6], "hash": r[7]} for r in rows]

    def verify(self) -> tuple[bool, int | None]:
        """Return (ok, first_bad_id)."""
        prev = "GENESIS"
        for r in self._conn.execute(
                "SELECT id, ts, case_id, actor, event, payload, prev_hash, hash FROM audit ORDER BY id"):
            id_, ts, case_id, actor, event, payload, prev_hash, h = r
            if prev_hash != prev or self._digest(prev, ts, case_id, actor, event, payload) != h:
                return False, id_
            prev = h
        return True, None
