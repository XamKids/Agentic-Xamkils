"""Tâches de l'agent en arrière-plan : les pages ne se bloquent jamais pendant qu'il travaille.

L'interface affiche les tâches en cours et se recharge quand elles sont terminées.
"""
from __future__ import annotations

import threading
import uuid
from typing import Callable

from ..i18n import tr
from ..records.audit import now

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def start(label: str, fn: Callable[[Callable[[int, str], None]], str | None], total: int = 1) -> str:
    """Lance fn(progress) dans un fil séparé ; fn renvoie le message final."""
    job_id = uuid.uuid4().hex[:10]
    job = {"id": job_id, "label": label, "status": "running", "done": 0, "total": total, "message": "", "started": now()}

    def progress(done: int, message: str = "") -> None:
        job.update(done=done, message=message)

    def target() -> None:
        try:
            job.update(status="done", message=fn(progress) or tr("Terminé."), done=total)
        except Exception as e:  # l'erreur est affichée à l'enseignant, rien n'est caché
            job.update(status="error", message=repr(e)[:300])

    with _lock:
        _jobs[job_id] = job
    threading.Thread(target=target, daemon=True).start()
    return job_id


def recent(limit: int = 5) -> list[dict]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j["started"], reverse=True)[:limit]


def running() -> list[dict]:
    return [j for j in recent(50) if j["status"] == "running"]


def take_finished() -> list[dict]:
    """Tâches terminées pas encore annoncées à l'enseignant (affichées une seule fois)."""
    with _lock:
        out = [j for j in _jobs.values() if j["status"] != "running" and not j.get("shown")]
        for j in out:
            j["shown"] = True
    return out
