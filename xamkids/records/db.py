"""Dossier scolaire longitudinal (SQLite) : schéma, connexion et lectures.

L'agent n'importe jamais ce package : il passe par les outils MCP du serveur xamkids-profile.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from ..config import CURRENT_TERM, CURRENT_YEAR, RECORDS_DB
from ..i18n import tr
from ..knowledge import EXERCISE_BANK

SCHEMA = """
CREATE TABLE IF NOT EXISTS schools (
    id INTEGER PRIMARY KEY, name TEXT, city TEXT,
    cycle TEXT);                         -- elementaire (CI → CM2) | moyen (6e → 3e, prévu, pas encore géré)
CREATE TABLE IF NOT EXISTS teachers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY, name TEXT, level TEXT, school_year TEXT, teacher_id INTEGER REFERENCES teachers(id),
    school_id INTEGER REFERENCES schools(id));
CREATE TABLE IF NOT EXISTS learners (
    id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, birth_year INTEGER, guardian_name TEXT,
    matricule TEXT);                     -- identifiant qui suit l'élève d'une école à l'autre
CREATE TABLE IF NOT EXISTS enrollments (
    learner_id INTEGER REFERENCES learners(id), class_id INTEGER REFERENCES classes(id),
    school_year TEXT, level TEXT, PRIMARY KEY (learner_id, school_year));
CREATE TABLE IF NOT EXISTS exercises (
    id TEXT PRIMARY KEY, subject TEXT, skill TEXT, level TEXT, prompt TEXT, answer TEXT,
    choices TEXT, error_map TEXT, hint TEXT, read_aloud_text TEXT,
    origin TEXT DEFAULT 'bank',          -- bank | targeted
    status TEXT DEFAULT 'active',        -- active (banque) | pending | approved | rejected | done
    target_learner_id INTEGER, hypothesis TEXT, thread_id TEXT, created_at TEXT,
    probe TEXT,                          -- exercices ciblés : target (hypothèse) | contrast (compétence voisine)
    reviewed_by TEXT, reviewed_at TEXT, review_comment TEXT);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id INTEGER, school_year TEXT, term INTEGER,
    kind TEXT DEFAULT 'regular', started_at TEXT, ended_at TEXT);
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER REFERENCES sessions(id),
    learner_id INTEGER, exercise_id TEXT REFERENCES exercises(id),
    given TEXT, correct INTEGER,         -- première réponse et sa justesse
    retry_correct INTEGER,               -- 2e essai réussi (NULL si pas de 2e essai)
    seconds REAL, attempts INTEGER, used_read_aloud INTEGER DEFAULT 0, used_hint INTEGER DEFAULT 0,
    error_type TEXT, school_year TEXT, term INTEGER, answered_at TEXT);
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id INTEGER, school_year TEXT, term INTEGER,
    days_present INTEGER, days_total INTEGER, source TEXT,
    UNIQUE (learner_id, school_year, term));
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id INTEGER, author TEXT, school_year TEXT,
    term INTEGER, date TEXT, text TEXT, source TEXT DEFAULT 'saisie');
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id INTEGER,
    kind TEXT,                           -- difficulty | strength | watch (à surveiller)
    subject TEXT, skill TEXT, statement TEXT,
    status TEXT,                         -- active | ruled_out | resolved | contested
    since TEXT,                          -- trimestre depuis lequel c'est observé
    sources TEXT, evidence TEXT, thread_id TEXT, created_at TEXT, updated_at TEXT,
    validated_by TEXT, validated_at TEXT, review_comment TEXT);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id INTEGER, teacher_id INTEGER,
    kind TEXT,                           -- difficulty | persistent | strength | ruled_out | question | document
    message TEXT, finding_id INTEGER, payload TEXT,
    status TEXT DEFAULT 'open',          -- open | answered | closed
    response TEXT, responded_by TEXT, thread_id TEXT, created_at TEXT, responded_at TEXT);
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id INTEGER, text TEXT, final_text TEXT,
    status TEXT DEFAULT 'pending',       -- pending | approved | rejected
    sources TEXT, thread_id TEXT, created_at TEXT, reviewed_by TEXT, reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS report_cards (    -- notes recopiées du livret scolaire (papier) à l'arrivée d'un élève
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id INTEGER, school_year TEXT, level TEXT, term INTEGER,
    subject TEXT,                        -- matière telle qu'écrite dans le livret
    domain TEXT,                         -- maths | francais | autre
    score REAL, max_score REAL, school TEXT, source TEXT,
    UNIQUE (learner_id, school_year, term, subject));
CREATE TABLE IF NOT EXISTS followups (       -- vérifications que l'agent se programme lui-même
    id INTEGER PRIMARY KEY AUTOINCREMENT, learner_id INTEGER, finding_id INTEGER, reason TEXT,
    after_sessions INTEGER,              -- relancer après ce nombre de séances terminées…
    sessions_at_creation INTEGER,
    due_year TEXT, due_term INTEGER,     -- …ou au début de ce trimestre, selon ce qui arrive en premier
    status TEXT DEFAULT 'pending',       -- pending | running | done
    created_at TEXT, thread_id TEXT, done_at TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, uploaded_by TEXT, class_id INTEGER,
    status TEXT DEFAULT 'uploaded',      -- uploaded | awaiting_confirmation | imported | rejected
    thread_id TEXT, uploaded_at TEXT);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(RECORDS_DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


# Colonnes ajoutées après la première version : ajoutées aux bases existantes au démarrage.
MIGRATIONS = [("classes", "school_id", "INTEGER"), ("learners", "matricule", "TEXT"), ("exercises", "probe", "TEXT"), ("findings", "since", "TEXT"), ("findings", "validated_by", "TEXT"),
              ("findings", "validated_at", "TEXT"), ("findings", "review_comment", "TEXT"),
              ("learners", "pin", "TEXT"), ("exercises", "teacher_text", "TEXT")]


def init(reset: bool = False) -> None:
    if reset and RECORDS_DB.exists():
        RECORDS_DB.unlink()
    with connect() as c:
        c.executescript(SCHEMA)
        for table, column, kind in MIGRATIONS:
            if column not in {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        for e in EXERCISE_BANK:
            c.execute(
                "INSERT OR IGNORE INTO exercises (id, subject, skill, level, prompt, answer, choices, error_map, hint,"
                " read_aloud_text, origin, status) VALUES (?,?,?,?,?,?,?,?,?,?, 'bank', 'active')",
                (e["id"], e["subject"], e["skill"], e["level"], e["prompt"], e["answer"], json.dumps(e["choices"], ensure_ascii=False),
                 json.dumps(e["error_map"], ensure_ascii=False), e["hint"], e.get("read_aloud_text")),
            )


def rows(sql: str, args: tuple = ()) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute(sql, args)]


def row(sql: str, args: tuple = ()) -> dict | None:
    r = rows(sql, args)
    return r[0] if r else None


def decode_exercise(e: dict) -> dict:
    e = dict(e)
    for k in ("choices", "error_map"):
        if isinstance(e.get(k), str):
            e[k] = json.loads(e[k])
    return e


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------

def teachers() -> list[dict]:
    return rows("SELECT * FROM teachers ORDER BY id")


def classes_for(teacher_id: int, school_year: str = CURRENT_YEAR) -> list[dict]:
    return rows("SELECT * FROM classes WHERE teacher_id = ? AND school_year = ?", (teacher_id, school_year))


def learners_in_class(class_id: int) -> list[dict]:
    return rows(
        "SELECT l.*, e.level FROM learners l JOIN enrollments e ON e.learner_id = l.id "
        "WHERE e.class_id = ? ORDER BY l.first_name", (class_id,))


def learner_pin(learner_id: int) -> str:
    """Code à 4 chiffres de l'élève (créé au premier besoin). L'enseignant le voit sur le profil et le donne à l'élève."""
    import secrets
    from ..config import DEMO_PIN
    if DEMO_PIN:
        return DEMO_PIN
    r = row("SELECT pin FROM learners WHERE id = ?", (learner_id,))
    if r and r["pin"]:
        return r["pin"]
    pin = f"{secrets.randbelow(9000) + 1000}"
    with connect() as c:
        c.execute("UPDATE learners SET pin = ? WHERE id = ?", (pin, learner_id))
    return pin


def learner(learner_id: int) -> dict | None:
    return row(
        "SELECT l.*, e.level, e.class_id, c.name AS class_name, c.teacher_id, s.name AS school_name FROM learners l "
        "LEFT JOIN enrollments e ON e.learner_id = l.id AND e.school_year = ? "
        "LEFT JOIN classes c ON c.id = e.class_id LEFT JOIN schools s ON s.id = c.school_id WHERE l.id = ?",
        (CURRENT_YEAR, learner_id))


def schooling(learner_id: int) -> list[dict]:
    """Parcours scolaire : une ligne par année (niveau, classe, école, enseignant)."""
    return rows(
        "SELECT e.school_year, e.level, c.name AS class_name, s.name AS school, s.city, t.name AS teacher "
        "FROM enrollments e JOIN classes c ON c.id = e.class_id LEFT JOIN schools s ON s.id = c.school_id "
        "LEFT JOIN teachers t ON t.id = c.teacher_id WHERE e.learner_id = ? ORDER BY e.school_year", (learner_id,))


def learner_name(learner_id: int) -> str:
    l = learner(learner_id)
    return f"{l['first_name']} {l['last_name']}" if l else tr("élève {learner_id}", learner_id=learner_id)


def term_skill_stats(learner_id: int) -> list[dict]:
    return rows(
        "SELECT a.school_year, a.term, x.skill, COUNT(*) AS n, AVG(a.correct) AS accuracy "
        "FROM answers a JOIN exercises x ON x.id = a.exercise_id WHERE a.learner_id = ? "
        "GROUP BY a.school_year, a.term, x.skill ORDER BY a.school_year, a.term", (learner_id,))


def findings(learner_id: int | None = None, status: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM findings WHERE 1=1", []
    if learner_id is not None:
        q += " AND learner_id = ?"; args.append(learner_id)
    if status:
        q += " AND status = ?"; args.append(status)
    out = rows(q + " ORDER BY updated_at DESC", tuple(args))
    for f in out:
        f["sources"] = json.loads(f["sources"] or "[]")
        f["evidence"] = json.loads(f["evidence"] or "{}")
    return out


def resolve_sources(sources: list[str]) -> list[dict]:
    """Transforme les références citées (answer:12, observation:3…) en éléments lisibles."""
    out = []
    for ref in sources:
        kind, _, rid = ref.partition(":")
        if kind == "answer":
            r = row("SELECT a.*, x.prompt, x.answer AS expected, x.skill FROM answers a "
                    "JOIN exercises x ON x.id = a.exercise_id WHERE a.id = ?", (rid,))
        elif kind == "observation":
            r = row("SELECT * FROM observations WHERE id = ?", (rid,))
        elif kind == "attendance":
            r = row("SELECT * FROM attendance WHERE id = ?", (rid,))
        elif kind == "report":
            r = row("SELECT * FROM report_cards WHERE id = ?", (rid,))
        elif kind == "exercise":
            r = row("SELECT id, skill, probe, prompt, answer, hypothesis, status, reviewed_by FROM exercises WHERE id = ?", (rid,))
        else:
            r = None
        out.append({"ref": ref, "kind": kind, "data": r})
    return out


def alerts(teacher_id: int | None = None, status: str | None = None, learner_id: int | None = None) -> list[dict]:
    q, args = "SELECT * FROM alerts WHERE 1=1", []
    for col, val in (("teacher_id", teacher_id), ("status", status), ("learner_id", learner_id)):
        if val is not None:
            q += f" AND {col} = ?"; args.append(val)
    out = rows(q + " ORDER BY id DESC", tuple(args))
    for a in out:
        a["payload"] = json.loads(a["payload"] or "null")
    return out


def pending_exercises(teacher_id: int | None = None) -> list[dict]:
    q = ("SELECT x.* FROM exercises x JOIN enrollments e ON e.learner_id = x.target_learner_id AND e.school_year = ? "
         "JOIN classes c ON c.id = e.class_id WHERE x.origin = 'targeted' AND x.status = 'pending'")
    args: list = [CURRENT_YEAR]
    if teacher_id is not None:
        q += " AND c.teacher_id = ?"; args.append(teacher_id)
    return [decode_exercise(e) for e in rows(q + " ORDER BY x.created_at", tuple(args))]


def pending_summaries(teacher_id: int | None = None) -> list[dict]:
    q = ("SELECT s.* FROM summaries s JOIN enrollments e ON e.learner_id = s.learner_id AND e.school_year = ? "
         "JOIN classes c ON c.id = e.class_id WHERE s.status = 'pending'")
    args: list = [CURRENT_YEAR]
    if teacher_id is not None:
        q += " AND c.teacher_id = ?"; args.append(teacher_id)
    return rows(q + " ORDER BY s.id", tuple(args))


def summaries(learner_id: int) -> list[dict]:
    return rows("SELECT * FROM summaries WHERE learner_id = ? ORDER BY id DESC", (learner_id,))


def observations(learner_id: int) -> list[dict]:
    return rows("SELECT * FROM observations WHERE learner_id = ? ORDER BY school_year DESC, term DESC, id DESC", (learner_id,))


def completed_sessions(learner_id: int) -> int:
    return row("SELECT COUNT(*) AS n FROM sessions WHERE learner_id = ? AND ended_at IS NOT NULL", (learner_id,))["n"]


def followups(learner_id: int, status: str = "pending") -> list[dict]:
    """Vérifications programmées par l'agent, avec le nombre de séances qu'il reste avant la relance."""
    done = completed_sessions(learner_id)
    out = rows("SELECT * FROM followups WHERE learner_id = ? AND status = ? ORDER BY id", (learner_id, status))
    for f in out:
        f["sessions_left"] = max(0, f["after_sessions"] - (done - f["sessions_at_creation"]))
    return out


def due_followups(learner_id: int | None = None) -> list[dict]:
    """Vérifications arrivées à échéance : assez de séances depuis, ou trimestre prévu atteint."""
    ids = [learner_id] if learner_id else [r["learner_id"] for r in rows(
        "SELECT DISTINCT learner_id FROM followups WHERE status = 'pending'")]
    return [f for lid in ids for f in followups(lid)
            if f["sessions_left"] == 0 or (CURRENT_YEAR, CURRENT_TERM) >= (f["due_year"], f["due_term"])]


def report_cards(learner_id: int) -> list[dict]:
    """Notes du livret scolaire, une ligne par trimestre et par matière."""
    return rows("SELECT * FROM report_cards WHERE learner_id = ? ORDER BY school_year, term, domain, subject", (learner_id,))


def attendance(learner_id: int) -> list[dict]:
    return rows("SELECT * FROM attendance WHERE learner_id = ? ORDER BY school_year, term", (learner_id,))
