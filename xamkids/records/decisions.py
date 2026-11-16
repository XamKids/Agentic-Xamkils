"""Décisions humaines : validations, réponses aux alertes, observations, import de documents.

Ces fonctions ne sont volontairement PAS exposées comme outils MCP : seul un enseignant,
depuis l'interface, peut libérer un exercice ciblé ou un résumé pour une famille.
"""
from __future__ import annotations

import json

from ..config import CURRENT_TERM, CURRENT_YEAR
from ..i18n import tr
from . import audit
from .db import connect, row


def review_exercises(ids: list[str], teacher: str, approve: bool, comment: str = "") -> None:
    status = "approved" if approve else "rejected"
    with connect() as c:
        for i in ids:
            c.execute("UPDATE exercises SET status = ?, reviewed_by = ?, reviewed_at = ?, review_comment = ? "
                      "WHERE id = ? AND status = 'pending'", (status, teacher, audit.now(), comment, i))
    audit.log(teacher, "interface", "approve_exercises" if approve else "reject_exercises",
              {"exercise_ids": ids, "comment": comment}, status)


def review_summary(summary_id: int, teacher: str, approve: bool, final_text: str | None = None) -> None:
    s = row("SELECT * FROM summaries WHERE id = ?", (summary_id,))
    with connect() as c:
        c.execute("UPDATE summaries SET status = ?, final_text = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
                  ("approved" if approve else "rejected", final_text if approve else None, teacher, audit.now(), summary_id))
    audit.log(teacher, "interface", "approve_guardian_summary" if approve else "reject_guardian_summary",
              {"summary_id": summary_id, "edited": bool(final_text and s and final_text != s["text"])},
              "approved" if approve else "rejected", learner_id=s["learner_id"] if s else None)


def validate_finding(finding_id: int, teacher: str) -> None:
    """L'enseignant valide un constat : il pourra figurer dans un résumé pour la famille."""
    f = row("SELECT learner_id FROM findings WHERE id = ?", (finding_id,))
    with connect() as c:
        c.execute("UPDATE findings SET validated_by = ?, validated_at = ? WHERE id = ?", (teacher, audit.now(), finding_id))
    audit.log(teacher, "interface", "validate_finding", {"finding_id": finding_id}, "validated",
              learner_id=f["learner_id"] if f else None)


def contest_finding(finding_id: int, teacher: str, comment: str) -> None:
    """L'enseignant conteste un constat : il sort du profil et l'agent ne le reproposera pas."""
    f = row("SELECT learner_id FROM findings WHERE id = ?", (finding_id,))
    with connect() as c:
        c.execute("UPDATE findings SET status = 'contested', review_comment = ?, validated_by = ?, validated_at = ? "
                  "WHERE id = ?", (comment, teacher, audit.now(), finding_id))
    audit.log(teacher, "interface", "contest_finding", {"finding_id": finding_id, "comment": comment}, "contested",
              learner_id=f["learner_id"] if f else None)


def answer_alert(alert_id: int, teacher: str, response: str, close: bool = True) -> None:
    with connect() as c:
        c.execute("UPDATE alerts SET status = ?, response = ?, responded_by = ?, responded_at = ? WHERE id = ?",
                  ("closed" if close else "answered", response, teacher, audit.now(), alert_id))
    audit.log(teacher, "interface", "answer_alert", {"alert_id": alert_id, "response": response})


def add_observation(learner_id: int, author: str, text: str, source: str = "saisie") -> int:
    with connect() as c:
        cur = c.execute("INSERT INTO observations (learner_id, author, school_year, term, date, text, source)"
                        " VALUES (?,?,?,?,?,?,?)", (learner_id, author, CURRENT_YEAR, CURRENT_TERM, audit.now()[:10], text, source))
    audit.log(author, "interface", "add_observation", {"learner_id": learner_id, "text": text}, learner_id=learner_id)
    return cur.lastrowid


def register_document(filename: str, teacher: str, class_id: int) -> int:
    with connect() as c:
        cur = c.execute("INSERT INTO documents (filename, uploaded_by, class_id, uploaded_at) VALUES (?,?,?,?)",
                        (filename, teacher, class_id, audit.now()))
    audit.log(teacher, "interface", "upload_document", {"filename": filename, "class_id": class_id})
    return cur.lastrowid


def import_document_rows(alert_id: int, teacher: str) -> int:
    """L'enseignant confirme la lecture d'un document par l'agent : les lignes sont importées."""
    a = row("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    payload = json.loads(a["payload"] or "{}")
    n = 0
    with connect() as c:
        for r in payload.get("attendance", []):
            c.execute("INSERT INTO attendance (learner_id, school_year, term, days_present, days_total, source) "
                      "VALUES (?,?,?,?,?,?) ON CONFLICT (learner_id, school_year, term) DO UPDATE SET "
                      "days_present = excluded.days_present, days_total = excluded.days_total, source = excluded.source",
                      (r["learner_id"], CURRENT_YEAR, CURRENT_TERM, r["days_present"], r["days_total"],
                       f"document:{payload.get('filename')}"))
            n += 1
        for r in payload.get("observations", []):
            c.execute("INSERT INTO observations (learner_id, author, school_year, term, date, text, source) "
                      "VALUES (?,?,?,?,?,?,?)", (r["learner_id"], teacher, CURRENT_YEAR, CURRENT_TERM, audit.now()[:10],
                                                  r["text"], f"document:{payload.get('filename')}"))
            n += 1
        if payload.get("livret"):
            n += _import_livret(c, payload, teacher)
        if payload.get("document_id"):
            c.execute("UPDATE documents SET status = 'imported' WHERE id = ?", (payload["document_id"],))
    answer_alert(alert_id, teacher, tr("Lecture confirmée : {n} lignes importées.", n=n))
    audit.log(teacher, "interface", "confirm_document_import", {"alert_id": alert_id, "rows": n})
    return n


def _import_livret(c, payload: dict, teacher: str) -> int:
    """Livret confirmé par l'enseignant : notes et appréciations des années passées entrent dans le dossier.
    Un élève qui n'était pas encore dans la classe y est inscrit (avec le matricule de son livret)."""
    lv, source = payload["livret"], f"livret:{payload.get('filename')}"
    learner_id = lv.get("learner_id")
    if learner_id is None:
        if not lv.get("new_learner"):
            return 0  # élève à identifier : l'enseignant doit d'abord répondre à la question de l'agent
        cls = c.execute("SELECT * FROM classes WHERE id = ?", (payload["class_id"],)).fetchone()
        learner_id = c.execute("INSERT INTO learners (first_name, last_name, matricule) VALUES (?,?,?)",
                               (lv["first_name"], lv["last_name"], lv.get("matricule"))).lastrowid
        c.execute("INSERT INTO enrollments (learner_id, class_id, school_year, level) VALUES (?,?,?,?)",
                  (learner_id, cls["id"], cls["school_year"], cls["level"]))
        audit.log(teacher, "interface", "enroll_from_livret", {"learner_id": learner_id, "class_id": cls["id"]},
                  learner_id=learner_id)
    elif lv.get("matricule"):
        c.execute("UPDATE learners SET matricule = COALESCE(matricule, ?) WHERE id = ?", (lv["matricule"], learner_id))
    n = 0
    for g in lv.get("grades", []):
        c.execute("INSERT INTO report_cards (learner_id, school_year, level, term, subject, domain, score, max_score,"
                  " school, source) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT (learner_id, school_year, term, subject)"
                  " DO UPDATE SET score = excluded.score, max_score = excluded.max_score, source = excluded.source",
                  (learner_id, g["school_year"], g["level"], g["term"], g["subject"], g["domain"], g["score"],
                   g["max_score"], g.get("school"), source))
        n += 1
    for a in lv.get("appreciations", []):
        if not c.execute("SELECT 1 FROM observations WHERE learner_id = ? AND school_year = ? AND term = ? AND text = ?",
                         (learner_id, a["school_year"], a["term"], a["text"])).fetchone():
            c.execute("INSERT INTO observations (learner_id, author, school_year, term, date, text, source) "
                      "VALUES (?,?,?,?,?,?,?)", (learner_id, tr("Livret scolaire ({level})", level=a["level"]), a["school_year"],
                                                  a["term"], None, a["text"], source))
            n += 1
    c.execute("UPDATE alerts SET learner_id = ? WHERE json_extract(payload, '$.document_id') = ?",
              (learner_id, payload.get("document_id")))
    audit.log(teacher, "interface", "confirm_livret_import", {"learner_id": learner_id, "grades": len(lv.get("grades", [])),
                                                              "appreciations": len(lv.get("appreciations", []))},
              learner_id=learner_id)
    return n
