"""Côté élève : choix des exercices, réponses, progrès personnels, ressenti et centres d'intérêt.

Ce que l'élève voit ne compare jamais avec ses camarades et ne montre aucun constat de son profil :
seulement ses propres progrès et ses efforts.
"""
from __future__ import annotations

import random

from ..config import CURRENT_TERM, CURRENT_YEAR
from ..i18n import pick, tr
from ..knowledge import SKILLS
from . import audit
from .db import connect, decode_exercise, learner, row, rows

# Le premier mot de chaque centre d'intérêt doit rester unique : interests() le retrouve dans l'observation.
INTERESTS = pick(["Dessin 🎨", "Calcul 🔢", "Lecture 📚", "Sciences 🔬", "Sport ⚽", "Musique 🎵",
                  "Raconter des histoires 🗣️", "Construire, bricoler 🔧", "Nature et animaux 🌿", "Aider les autres 🤝"],
                 ["Drawing 🎨", "Maths 🔢", "Reading 📚", "Science 🔬", "Sport ⚽", "Music 🎵",
                  "Telling stories 🗣️", "Building, making things 🔧", "Nature and animals 🌿", "Helping others 🤝"])
FEELINGS = pick({"facile": "Facile", "moyen": "Ça allait", "difficile": "Difficile"},
                {"facile": "Easy", "moyen": "It was okay", "difficile": "Hard"})
SUBJECT_LABEL = pick({"maths": "Mathématiques", "francais": "Français"}, {"maths": "Maths", "francais": "English"})


def next_exercises(learner_id: int, n: int = 8, subject: str | None = None) -> tuple[str, list[dict]]:
    """Séance du jour : exercices ciblés validés en priorité, sinon un mélange au niveau de l'élève.
    Avec `subject` (maths | francais) : entraînement libre dans cette matière."""
    if subject is None:
        targeted = rows("SELECT * FROM exercises WHERE origin = 'targeted' AND status = 'approved' "
                        "AND target_learner_id = ? ORDER BY created_at, rowid", (learner_id,))
        if targeted:
            return "targeted", [decode_exercise(e) for e in targeted]
    pool = rows("SELECT * FROM exercises WHERE origin = 'bank' AND level = ?", (learner(learner_id)["level"],))
    rng = random.Random()
    by_skill: dict[str, list] = {}
    for e in pool:
        by_skill.setdefault(e["skill"], []).append(e)
    picked = []
    skills = [s for s in SKILLS if subject is None or SKILLS[s]["subject"] == subject]
    rng.shuffle(skills)
    while len(picked) < n and skills:
        for s in list(skills):
            if by_skill.get(s):
                picked.append(by_skill[s].pop(rng.randrange(len(by_skill[s]))))
            else:
                skills.remove(s)
            if len(picked) >= n:
                break
    return "regular", [decode_exercise(e) for e in picked]


def start_session(learner_id: int, kind: str) -> int:
    with connect() as c:
        cur = c.execute("INSERT INTO sessions (learner_id, school_year, term, kind, started_at) VALUES (?,?,?,?,?)",
                        (learner_id, CURRENT_YEAR, CURRENT_TERM, kind, audit.now()))
        return cur.lastrowid


def save_answer(session_id: int, learner_id: int, exercise_id: str, given: str, correct: bool, seconds: float,
                attempts: int, used_read_aloud: bool, used_hint: bool, retry_correct: bool | None = None) -> int:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO answers (session_id, learner_id, exercise_id, given, correct, retry_correct, seconds, attempts,"
            " used_read_aloud, used_hint, school_year, term, answered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, learner_id, exercise_id, given, int(correct), None if retry_correct is None else int(retry_correct),
             round(seconds, 1), attempts, int(used_read_aloud),
             int(used_hint), CURRENT_YEAR, CURRENT_TERM, audit.now()))
        return cur.lastrowid


def end_session(session_id: int) -> None:
    with connect() as c:
        c.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (audit.now(), session_id))
        c.execute("UPDATE exercises SET status = 'done' WHERE origin = 'targeted' AND status = 'approved' AND id IN "
                  "(SELECT exercise_id FROM answers WHERE session_id = ?)", (session_id,))


# ---------------------------------------------------------------------------
# Mon carnet : progrès comparés à soi-même uniquement
# ---------------------------------------------------------------------------

def _previous_term() -> tuple[str, int]:
    if CURRENT_TERM > 1:
        return CURRENT_YEAR, CURRENT_TERM - 1
    start = int(CURRENT_YEAR[:4]) - 1
    return f"{start}-{start + 1}", 3


def progress(learner_id: int) -> dict:
    """Séances, bonnes réponses et étoiles du trimestre ; réussite par matière, ce trimestre et le précédent."""
    sessions_done = row("SELECT COUNT(*) AS n FROM sessions WHERE learner_id = ? AND school_year = ? AND term = ? "
                        "AND ended_at IS NOT NULL", (learner_id, CURRENT_YEAR, CURRENT_TERM))["n"]
    answers = row("SELECT COUNT(*) AS n, COALESCE(SUM(correct), 0) AS first_try, "
                  "COALESCE(SUM(CASE WHEN correct = 0 AND retry_correct = 1 THEN 1 ELSE 0 END), 0) AS second_try "
                  "FROM answers WHERE learner_id = ? AND school_year = ? AND term = ?",
                  (learner_id, CURRENT_YEAR, CURRENT_TERM))
    by_subject = {}
    for year, term, key in ((CURRENT_YEAR, CURRENT_TERM, "now"), (*_previous_term(), "before")):
        for r in rows("SELECT x.subject, AVG(a.correct) AS acc, COUNT(*) AS n FROM answers a "
                      "JOIN exercises x ON x.id = a.exercise_id WHERE a.learner_id = ? AND a.school_year = ? "
                      "AND a.term = ? GROUP BY x.subject", (learner_id, year, term)):
            by_subject.setdefault(r["subject"], {})[key] = r["acc"]
    # Étoiles d'effort : une par séance terminée, une par réponse trouvée au deuxième essai (persévérance).
    return {"sessions": sessions_done, "answers": answers["n"], "first_try": answers["first_try"],
            "stars": sessions_done + answers["second_try"], "by_subject": by_subject}


def encouragement(learner_id: int) -> str:
    """Phrase de fin de séance : le chemin parcouru (exercices faits depuis le début de sa scolarité) et
    l'effort du trimestre. Aucune note, aucun pourcentage, aucune comparaison avec les camarades."""
    total = row("SELECT COUNT(*) AS n FROM answers WHERE learner_id = ?", (learner_id,))["n"]
    first = row("SELECT e.level FROM enrollments e WHERE e.learner_id = ? ORDER BY e.school_year LIMIT 1", (learner_id,))
    p = progress(learner_id)
    since = tr("Depuis le {level}", level=first["level"]) if first else tr("Depuis le début")
    text = tr("{since}, tu as fait {total} exercice{s}.", since=since, total=total, s="s" if total > 1 else "")
    if p["first_try"]:
        text += tr(" Ce trimestre, tu as trouvé {n} réponse{s} du premier coup !", n=p["first_try"],
                   s="s" if p["first_try"] > 1 else "")
    return text


# ---------------------------------------------------------------------------
# Ressenti et centres d'intérêt : des observations sourcées, visibles par l'enseignant
# ---------------------------------------------------------------------------

def _add_learner_observation(learner_id: int, text: str, source: str) -> int:
    with connect() as c:
        cur = c.execute("INSERT INTO observations (learner_id, author, school_year, term, date, text, source)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (learner_id, tr("Élève"), CURRENT_YEAR, CURRENT_TERM, audit.now()[:10], text, source))
    audit.log("élève", "interface", source, {"learner_id": learner_id, "text": text}, learner_id=learner_id)
    return cur.lastrowid


def save_reflection(learner_id: int, session_id: int, feeling: str | None, liked: list[str]) -> None:
    parts = [tr("ressenti : « {feeling} »", feeling=FEELINGS[feeling].lower())] if feeling else []
    if liked:
        parts.append(tr("a préféré : ") + ", ".join(liked))
    if parts:
        _add_learner_observation(learner_id, tr("Après la séance {n}, ", n=session_id) + pick(" ; ", "; ").join(parts) + ".",
                                 "auto-évaluation élève")


def interests(learner_id: int) -> list[str]:
    r = row("SELECT text FROM observations WHERE learner_id = ? AND source = 'intérêts (élève)' "
            "ORDER BY id DESC LIMIT 1", (learner_id,))
    return [i for i in INTERESTS if r and i.split(" ")[0] in r["text"]]


def save_interests(learner_id: int, chosen: list[str]) -> None:
    labels = ", ".join(i.rsplit(" ", 1)[0] for i in chosen)
    _add_learner_observation(learner_id, tr("Centres d'intérêt déclarés par l'élève : {labels}.", labels=labels), "intérêts (élève)")
