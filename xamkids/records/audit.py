"""Journal d'audit : chaque appel d'outil, calcul exécuté et validation humaine, horodaté."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from ..config import AUDIT_DB
from ..i18n import tr

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,          -- 'agent' ou nom de l'enseignant
    server TEXT,                  -- serveur MCP concerné (xamkids-profile, run-python, filesystem) ou 'interface'
    action TEXT NOT NULL,         -- nom de l'outil ou de l'action humaine
    thread_id TEXT,               -- exécution de l'agent concernée
    learner_id INTEGER,
    inputs TEXT,
    outputs TEXT,
    status TEXT DEFAULT 'ok'      -- ok | refused | error
);
"""


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(AUDIT_DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def _dump(x: Any, limit: int = 20000) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + tr("…[tronqué]")


def log(actor: str, server: str, action: str, inputs: Any = None, outputs: Any = None,
        status: str = "ok", thread_id: str | None = None, learner_id: int | None = None) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO audit_log (ts, actor, server, action, thread_id, learner_id, inputs, outputs, status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (now(), actor, server, action, thread_id, learner_id, _dump(inputs), _dump(outputs), status),
        )


def entries(limit: int = 500, learner_id: int | None = None, thread_id: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM audit_log WHERE 1=1", []
    if learner_id is not None:
        q += " AND learner_id = ?"
        args.append(learner_id)
    if thread_id is not None:
        q += " AND thread_id = ?"
        args.append(thread_id)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args)]
