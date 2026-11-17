"""Canal interne pour les serveurs MCP déployés dans leurs propres services.

Les bases SQLite restent dans la plateforme ; un serveur MCP distant y accède par transactions
(begin → exec… → end), authentifiées par un secret partagé (XAMKIDS_INTERNAL_TOKEN).
"""
from __future__ import annotations

import hmac
import os
import sqlite3
import threading
import time
import uuid

from flask import abort, jsonify, request

from ..config import AUDIT_DB, RECORDS_DB

TTL = 120  # une transaction oubliée est annulée après 2 minutes
_open: dict[str, tuple[sqlite3.Connection, float]] = {}
_lock = threading.Lock()
_PATHS = {"records": RECORDS_DB, "audit": AUDIT_DB}


def _reap() -> None:
    now = time.time()
    for k in [k for k, (_, t) in _open.items() if now - t > TTL]:
        c, _ = _open.pop(k)
        try:
            c.rollback()
            c.close()
        except sqlite3.Error:
            pass


def register(app) -> None:
    @app.post("/internal/db/<kind>")
    def internal_db(kind: str):
        want = os.environ.get("XAMKIDS_INTERNAL_TOKEN", "")
        if not want or kind not in _PATHS:
            abort(404)
        if not hmac.compare_digest(request.headers.get("X-Internal-Token", "").encode(), want.encode()):
            abort(403)
        body = request.get_json(force=True)
        op = body.get("op")
        if op == "begin":
            c = sqlite3.connect(_PATHS[kind], timeout=30, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            tid = uuid.uuid4().hex
            with _lock:
                _reap()
                _open[tid] = (c, time.time())
            return jsonify({"id": tid})
        with _lock:
            entry = _open.get(body.get("id"))
        if not entry:
            abort(410)
        c = entry[0]
        if op == "exec":
            cur = c.execute(body["sql"], body.get("args") or [])
            keys = [d[0] for d in cur.description] if cur.description else []
            rows = [list(r) for r in cur.fetchall()] if cur.description else []
            _open[body["id"]] = (c, time.time())
            return jsonify({"keys": keys, "rows": rows, "lastrowid": cur.lastrowid, "rowcount": cur.rowcount})
        if op == "end":
            with _lock:
                _open.pop(body["id"], None)
            try:
                c.commit() if body.get("commit") else c.rollback()
            finally:
                c.close()
            return jsonify({"ok": True})
        abort(400)
