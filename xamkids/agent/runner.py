"""Lancement, reprise après décision humaine et suivi des exécutions de l'agent."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from typing import Any, Callable

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from ..config import AGENT_DB
from ..i18n import tr
from ..records import audit
from .graph import build_graph
from .toolkit import Toolkit

WAITING_MESSAGES = {
    "approval": "En attente de la validation des exercices ciblés par l'enseignant.",
    "results": "En attente des réponses de l'élève aux exercices ciblés.",
}
_RUNS_SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
    thread_id TEXT PRIMARY KEY, learner_id INTEGER, trigger TEXT,
    status TEXT,          -- running | waiting | done | error
    waiting_for TEXT,     -- approval | results
    created_at TEXT, updated_at TEXT, outcome TEXT, steps TEXT)"""


def _db() -> sqlite3.Connection:
    c = sqlite3.connect(AGENT_DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute(_RUNS_SCHEMA)
    return c


def _save_run(thread_id: str, **fields) -> None:
    with _db() as c:
        c.execute("INSERT OR IGNORE INTO runs (thread_id, created_at) VALUES (?, ?)", (thread_id, audit.now()))
        fields["updated_at"] = audit.now()
        c.execute(f"UPDATE runs SET {', '.join(f'{k} = ?' for k in fields)} WHERE thread_id = ?",
                  (*fields.values(), thread_id))


async def _run_one(graph, job: dict) -> dict:
    tid = job.get("thread_id") or f"{job['trigger']}-{job.get('learner_id') or 'classe'}-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": tid}}
    if "resume" in job:
        payload: Any = Command(resume=job["resume"])
    else:
        payload = {"thread_id": tid, "trigger": job["trigger"], "learner_id": job.get("learner_id"),
                   "session_id": job.get("session_id"), "document": job.get("document"),
                   "followup": job.get("followup"), "steps": []}
        _save_run(tid, learner_id=job.get("learner_id"), trigger=job["trigger"], status="running")
    try:
        await graph.ainvoke(payload, config)
        snap = await graph.aget_state(config)
    except Exception as e:
        _save_run(tid, status="error", outcome=repr(e)[:500])
        audit.log("agent", "agent", "run_error", job, repr(e), "error", tid, job.get("learner_id"))
        return {"thread_id": tid, "status": "error", "outcome": repr(e)}
    interrupts = [i.value for t in snap.tasks for i in t.interrupts]
    waiting = interrupts[0]["type"] if interrupts else None
    status = "waiting" if waiting else "done"
    outcome = tr(WAITING_MESSAGES[waiting]) if waiting else snap.values.get("outcome")
    _save_run(tid, status=status, waiting_for=waiting, outcome=outcome,
              steps=json.dumps(snap.values.get("steps", []), ensure_ascii=False, default=str))
    return {"thread_id": tid, "status": status, "waiting_for": waiting, "outcome": outcome}


async def _execute(jobs: list[dict], on_progress: Callable[[int, dict], None] | None = None) -> list[dict]:
    """Une seule connexion aux serveurs MCP pour toutes les exécutions demandées."""
    results = []
    async with Toolkit() as tk, AsyncSqliteSaver.from_conn_string(str(AGENT_DB)) as saver:
        graph = build_graph(tk, saver)
        for i, job in enumerate(jobs):
            if on_progress:
                on_progress(i, job)
            results.append(await _run_one(graph, job))
    return results


# -- API publique (synchrone, utilisée par l'interface) -------------------------

def run(trigger: str, learner_id: int | None = None, session_id: int | None = None, document: dict | None = None,
        followup: dict | None = None) -> dict:
    job = {"trigger": trigger, "learner_id": learner_id, "session_id": session_id, "document": document,
           "followup": followup}
    return asyncio.run(_execute([job]))[0]


def run_many(trigger: str, learner_ids: list[int], on_progress: Callable[[int, dict], None] | None = None) -> list[dict]:
    """Plusieurs élèves à la suite (revue de trimestre) ; on_progress(i, job) est appelé avant chaque élève."""
    return asyncio.run(_execute([{"trigger": trigger, "learner_id": lid} for lid in learner_ids], on_progress))


def resume(thread_id: str, value: dict) -> dict:
    return asyncio.run(_execute([{"thread_id": thread_id, "resume": value}]))[0]


def run_due_followups(learner_id: int | None = None) -> list[dict]:
    """Relance l'agent pour chaque vérification qu'il s'était programmée et qui arrive à échéance
    (assez de séances depuis, ou trimestre prévu atteint). Appelé après chaque séance et périodiquement."""
    from ..records import db
    results = []
    for f in db.due_followups(learner_id):
        with db.connect() as c:  # réservation : une vérification n'est lancée qu'une fois
            if c.execute("UPDATE followups SET status = 'running' WHERE id = ? AND status = 'pending'",
                         (f["id"],)).rowcount == 0:
                continue
        r = run("followup", learner_id=f["learner_id"], followup=f)
        with db.connect() as c:
            c.execute("UPDATE followups SET status = 'done', done_at = ?, outcome = ? WHERE id = ?",
                      (audit.now(), r.get("outcome"), f["id"]))
        results.append(r)
    return results


def runs(learner_id: int | None = None, limit: int = 50) -> list[dict]:
    q, args = "SELECT * FROM runs", []
    if learner_id is not None:
        q += " WHERE learner_id = ?"
        args.append(learner_id)
    with _db() as c:
        out = [dict(r) for r in c.execute(q + " ORDER BY updated_at DESC LIMIT ?", (*args, limit))]
    for r in out:
        r["steps"] = json.loads(r["steps"] or "[]")
    return out


def waiting_threads(learner_id: int, waiting_for: str) -> list[str]:
    with _db() as c:
        return [r["thread_id"] for r in c.execute(
            "SELECT thread_id FROM runs WHERE learner_id = ? AND status = 'waiting' AND waiting_for = ?",
            (learner_id, waiting_for))]
