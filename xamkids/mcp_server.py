"""Serveur MCP « xamkids-profile » : seul point d'accès de l'agent au dossier des élèves.

Outils : get_learner_timeline, analyze_answers, propose_exercises, update_profile,
alert_teacher, draft_guardian_summary.
Ressources : taxonomie des erreurs, banque d'exercices, règles de l'agent.

La validation des exercices et des résumés n'est volontairement PAS un outil :
seul un enseignant peut la faire, depuis l'interface.
Chaque appel d'outil est journalisé (entrées, sorties, horodatage).
"""
from __future__ import annotations

import functools
import json
import unicodedata
import uuid
from collections import Counter, defaultdict
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .records import audit, db
from .config import CURRENT_TERM, CURRENT_YEAR, FAST_SECONDS, LOW_ATTENDANCE
from . import trends, wording
from .i18n import pick, tr
from .knowledge import (AGENT_RULES, CONTRAST, ERROR_TAXONOMY, LEVELS, LISTENABLE, OTHER_DOMAINS, SKILLS,
                        find_forbidden_label)

mcp = FastMCP(
    "xamkids-profile",
    instructions=tr("Accès au dossier longitudinal des élèves. ") + AGENT_RULES,
    log_level="WARNING",
)
SERVER = "xamkids-profile"


# Paramètre commun à tous les outils : facultatif, il sert seulement à relier l'appel au journal d'audit.
ThreadId = Annotated[str | None, Field(description=tr("Facultatif : identifiant de l'exécution de l'agent appelant, "
                                                      "utilisé uniquement pour relier cet appel au journal d'audit."))]


# Descriptions des outils vues par les clients MCP en anglais (en français : la docstring de chaque outil).
_EN_DOCS = {
    "get_learner_timeline": (
        "A learner's history across all school years: per term and per skill, number of answers, success rate, "
        "mean time, attempts, use of read-aloud and hints, error types (with the answer IDs to cite), attendance,"
        " teachers' observations, report card grades (past years, `report_card`), findings already recorded, "
        "pending check exercises and results of check exercises (target or contrast). The class average is used "
        "to compute trends; it never appears in a finding."),
    "analyze_answers": (
        "Classifies all of a learner's not-yet-analysed errors using the taxonomy (resource "
        "xamkids://taxonomy/errors) and returns the breakdown of error types per skill, for one session "
        "(`session_id`) or for the whole history."),
    "propose_exercises": (
        "Creates 3 to 6 check exercises to confirm or rule out a hypothesis. They are saved as PENDING: the "
        "learner only sees them after the teacher approves them. Target exercises: either `exercises` (each one: "
        "prompt, answer, choices, error_map {wrong_choice: error_type}, optional hint) or `bank_exercise_ids`. "
        '`contrast_exercise_ids`: bank exercises for the contrast test. `contrast_mode`: "voisine" (default) = a '
        "neighbouring skill, to find out whether the difficulty is specific (contrast passed) or broader "
        '(contrast failed); "ecoute" = the SAME skill, but the text is read to the learner, to find out whether '
        'the difficulty comes from reading the text (passed when listening, failed alone); "temps" = the SAME '
        "skill, but the learner is asked to read again and the answers only appear after a few seconds, to find "
        "out whether the difficulty comes from going too fast (passed when taking time, failed otherwise). "
        "`teacher_text`: the two sentences shown to the teacher ({noticed, proposal, source}), written by the "
        "model and checked by the agent; the server refuses them if they contain a label."),
    "update_profile": (
        'Records in the profile a difficulty, a lasting strength or a point "to watch" (watch, for example rising'
        " absences), citing its sources (answer:ID, observation:ID, attendance:ID, report:ID for a report card "
        "grade, exercise:ID) and the term since which it has been observed (`since`). The server refuses any "
        "finding without a source, any diagnostic term or label, any comparison with the class, and any active "
        "difficulty not confirmed by completed check exercises. A finding already validated by the teacher and "
        'then changed goes back to "confirmed by the agent": the teacher must validate it again.'),
    "check_finding": (
        "Checks a finding BEFORE recording it, without writing anything: same rules as update_profile (sources "
        "that exist and belong to the learner, no diagnostic label, no comparison with the class, difficulty "
        "confirmed by completed check exercises, sentence for the teacher faithful to the facts). Returns {ok, "
        "problems}."),
    "compute_trends": (
        "A learner's exact trends, computed by the server over the whole history: for each skill, series per "
        "term, consecutive weak terms (`pattern`, `low_terms`), consecutive strong terms (`high_terms`), recent "
        "slope, dominant error and the answer IDs to cite; attendance (`attendance`: drop, starting term, days "
        'absent); general dips (`global_dips`). A weak term marked by many absences is "explained" and does not '
        "count in the trend. Use these numbers rather than estimating them."),
    "find_learner": (
        "Finds a learner by first name and/or last name (accents and case ignored), or by student ID (matricule)."
        " Returns the matching learners with their identifier (learner_id), class and level. With an empty name, "
        "returns the whole class for the current year."),
    "alert_teacher": (
        "Notifies the teacher of the learner's current class (or of class `class_id` for a document): new or "
        "persistent difficulty, strength, ruled-out hypothesis, or a QUESTION when a document is unreadable or "
        "data contradict each other (the agent asks instead of guessing). `document`: a reading of a document "
        "that the teacher must confirm before import."),
    "schedule_followup": (
        "Schedules the agent's next check on a learner: it is triggered automatically after `after_sessions` "
        "completed sessions or at the start of the next term, whichever comes first. Use it after a finding "
        "(difficulty, point to watch) to check whether it persists, resolves or gets worse. Only one pending "
        "check per finding."),
    "draft_guardian_summary": (
        "Drafts a family summary in plain language. It stays PENDING: the teacher reads it, edits it if needed "
        "and decides whether to share it. The agent never contacts the family."),
}


def _en_doc(tool: str) -> str | None:
    """Description anglaise d'un outil ; None en français (FastMCP reprend alors la docstring)."""
    return pick(None, _EN_DOCS[tool])


class Refused(Exception):
    """Demande refusée par une règle du serveur (garde-fou)."""


def logged(fn):
    """Journalise chaque appel ; transforme un refus en réponse explicite pour l'agent."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        learner_id = kwargs.get("learner_id")
        thread_id = kwargs.get("thread_id")
        try:
            out = fn(*args, **kwargs)
            audit.log("agent", SERVER, fn.__name__, kwargs, out, "ok", thread_id, learner_id)
            return out
        except Refused as e:
            out = {"ok": False, "refused": str(e)}
            audit.log("agent", SERVER, fn.__name__, kwargs, out, "refused", thread_id, learner_id)
            return out
        except Exception as e:  # erreur inattendue : journalisée puis remontée à l'agent
            audit.log("agent", SERVER, fn.__name__, kwargs, repr(e), "error", thread_id, learner_id)
            raise

    return wrapper


def _require_learner(learner_id: int) -> dict:
    l = db.learner(learner_id)
    if not l:
        raise Refused(tr("Élève {learner_id} inconnu.", learner_id=learner_id))
    return l


def _classify(answer: dict, error_map: dict) -> str | None:
    if answer["correct"]:
        return None
    if not answer["given"]:
        return "sans_reponse"
    if answer["seconds"] is not None and answer["seconds"] < 4:
        return "reponse_impulsive"
    return error_map.get(str(answer["given"]), "non_classee")


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

@mcp.tool(description=_en_doc("get_learner_timeline"))
@logged
def get_learner_timeline(learner_id: int, skill: str | None = None, thread_id: ThreadId = None) -> dict:
    """Historique d'un élève sur toutes les années : par trimestre et par compétence, nombre de réponses,
    taux de réussite, temps moyen, essais, usage de la lecture à voix haute et des indices, types d'erreurs
    (avec les identifiants des réponses à citer), présence, observations des enseignants, notes du livret
    scolaire (années passées, `report_card`), constats déjà
    enregistrés, exercices ciblés en attente et résultats des exercices ciblés (cible ou contraste).
    La moyenne de la classe sert au calcul des tendances ; elle n'apparaît jamais dans un constat."""
    return _timeline(learner_id, skill)


def _timeline(learner_id: int, skill: str | None = None) -> dict:
    """Historique complet (partagé par get_learner_timeline et compute_trends)."""
    l = _require_learner(learner_id)
    answers = db.rows(
        "SELECT a.*, x.skill, x.subject, x.origin, x.hypothesis, x.probe, s.kind AS session_kind FROM answers a "
        "JOIN exercises x ON x.id = a.exercise_id JOIN sessions s ON s.id = a.session_id "
        "WHERE a.learner_id = ? ORDER BY a.school_year, a.term, a.id", (learner_id,))
    attendance = {(r["school_year"], r["term"]): r for r in db.attendance(learner_id)}
    terms: dict = {}
    targeted = []
    for a in answers:
        if skill and a["skill"] != skill:
            continue
        if a["origin"] == "targeted":
            targeted.append({k: a[k] for k in ("id", "exercise_id", "skill", "probe", "hypothesis", "given", "correct",
                                                 "error_type", "seconds", "attempts", "answered_at")})
            continue
        key = (a["school_year"], a["term"])
        t = terms.setdefault(key, defaultdict(list))
        t[a["skill"]].append(a)

    class_means = {
        (r["school_year"], r["term"], r["skill"]): round(r["acc"], 2)
        for r in db.rows(
            "SELECT a.school_year, a.term, x.skill, AVG(a.correct) AS acc FROM answers a "
            "JOIN exercises x ON x.id = a.exercise_id WHERE x.origin = 'bank' GROUP BY 1, 2, 3")
    }
    schooling = {r["school_year"]: r for r in db.schooling(learner_id)}
    timeline = []
    for (year, term), by_skill in sorted(terms.items()):
        att = attendance.get((year, term))
        rate = round(att["days_present"] / att["days_total"], 2) if att else None
        entry = {
            "school_year": year, "term": term, "level": schooling.get(year, {}).get("level"),
            "school": schooling.get(year, {}).get("school"),
            "attendance": {"id": att["id"], "rate": rate, "days_present": att["days_present"],
                           "days_total": att["days_total"], "low": rate is not None and rate < LOW_ATTENDANCE} if att else None,
            "skills": {},
        }
        for sk, items in by_skill.items():
            n = len(items)
            wrong = [a for a in items if not a["correct"]]
            errors: dict[str, list[int]] = defaultdict(list)
            for a in wrong:
                errors[a["error_type"] or "non_analysee"].append(a["id"])
            entry["skills"][sk] = {
                "n": n,
                "accuracy": round(sum(a["correct"] for a in items) / n, 2),
                "class_accuracy": class_means.get((year, term, sk)),
                "mean_seconds": round(sum(a["seconds"] or 0 for a in items) / n, 1),
                "retry_success": round(sum(1 for a in wrong if a["retry_correct"]) / len(wrong), 2) if wrong else None,
                "read_aloud_rate": round(sum(a["used_read_aloud"] for a in items) / n, 2),
                "accuracy_with_read_aloud": (
                    round(sum(a["correct"] for a in items if a["used_read_aloud"]) / max(1, sum(a["used_read_aloud"] for a in items)), 2)
                    if any(a["used_read_aloud"] for a in items) else None),
                "hint_rate": round(sum(a["used_hint"] for a in items) / n, 2),
                "fast_rate": round(sum(1 for a in items if (a["seconds"] or 0) < FAST_SECONDS) / n, 2),
                "errors": {k: {"count": len(v), "answer_ids": v} for k, v in errors.items()},
                "answer_ids": [a["id"] for a in items],
            }
        timeline.append(entry)

    obs = [{"id": o["id"], "school_year": o["school_year"], "term": o["term"], "author": o["author"],
            "text": o["text"], "source": o["source"]} for o in db.observations(learner_id)]
    pending = db.rows("SELECT id, skill, probe, hypothesis, status, thread_id FROM exercises WHERE origin = 'targeted' "
                      "AND target_learner_id = ? AND status IN ('pending', 'approved')", (learner_id,))
    return {
        "learner": {"id": l["id"], "first_name": l["first_name"], "last_name": l["last_name"], "level": l["level"],
                    "class": l["class_name"], "school": l["school_name"], "matricule": l["matricule"]},
        "current_year": CURRENT_YEAR,
        "terms": timeline,
        "observations": obs,
        # Notes recopiées du livret scolaire papier (années passées, autre école possible) : une tendance par
        # matière, pas le détail des erreurs. Citer « report:ID ». Ni rang ni moyenne de classe.
        "report_card": [{k: r[k] for k in ("id", "school_year", "level", "term", "subject", "domain", "score",
                                           "max_score", "school")} for r in db.report_cards(learner_id)],
        "findings": [{k: f[k] for k in ("id", "kind", "skill", "statement", "status", "since", "sources", "validated_by",
                                        "updated_at")}
                     for f in db.findings(learner_id)],
        "pending_targeted_exercises": pending,
        "targeted_results": targeted,
    }


@mcp.tool(description=_en_doc("analyze_answers"))
@logged
def analyze_answers(learner_id: int, session_id: int | None = None, thread_id: ThreadId = None) -> dict:
    """Classe toutes les erreurs pas encore analysées d'un élève selon la taxonomie (ressource
    xamkids://taxonomy/errors) et renvoie la répartition des types d'erreurs par compétence,
    pour une séance (`session_id`) ou pour tout l'historique."""
    _require_learner(learner_id)
    todo = db.rows("SELECT a.*, x.error_map, x.skill FROM answers a JOIN exercises x ON x.id = a.exercise_id "
                   "WHERE a.learner_id = ? AND a.correct = 0 AND a.error_type IS NULL", (learner_id,))
    with db.connect() as c:
        for a in todo:
            a["error_type"] = _classify(a, json.loads(a["error_map"] or "{}"))
            c.execute("UPDATE answers SET error_type = ? WHERE id = ?", (a["error_type"], a["id"]))

    scope = "a.session_id = ?" if session_id is not None else "1=1"
    rows = db.rows(
        f"SELECT a.id, a.correct, a.error_type, a.seconds, x.skill FROM answers a JOIN exercises x ON x.id = a.exercise_id "
        f"WHERE a.learner_id = ? AND {scope}", (learner_id, session_id) if session_id is not None else (learner_id,))
    by_skill: dict = {}
    for r in rows:
        s = by_skill.setdefault(r["skill"], {"n": 0, "wrong": 0, "errors": Counter()})
        s["n"] += 1
        if not r["correct"]:
            s["wrong"] += 1
            s["errors"][r["error_type"]] += 1
    summary = {
        sk: {"n": v["n"], "wrong": v["wrong"],
             "dominant_error": v["errors"].most_common(1)[0][0] if v["errors"] else None,
             "dominant_share": round(v["errors"].most_common(1)[0][1] / v["wrong"], 2) if v["wrong"] else None,
             "errors": dict(v["errors"])}
        for sk, v in by_skill.items()
    }
    return {"ok": True, "newly_classified": len(todo), "scope": tr("séance {session_id}", session_id=session_id) if session_id else tr("tout l'historique"),
            "by_skill": summary,
            "session_errors": [{"answer_id": a["id"], "skill": a["skill"], "error_type": a["error_type"]}
                               for a in todo if a["session_id"] == session_id] if session_id is not None else []}


@mcp.tool(description=_en_doc("propose_exercises"))
@logged
def propose_exercises(learner_id: int, skill: str, hypothesis: str, exercises: list[dict] | None = None,
                      bank_exercise_ids: list[str] | None = None, contrast_exercise_ids: list[str] | None = None,
                      contrast_mode: Literal["voisine", "ecoute", "temps"] = "voisine",
                      teacher_text: dict | None = None, thread_id: ThreadId = None) -> dict:
    """Crée 3 à 6 exercices ciblés pour confirmer ou écarter une hypothèse. Ils sont enregistrés EN ATTENTE :
    l'élève ne les verra qu'après validation par l'enseignant. Exercices cibles : soit `exercises` (chacun :
    prompt, answer, choices, error_map {choix_faux: type_erreur}, hint optionnel), soit `bank_exercise_ids`.
    `contrast_exercise_ids` : exercices de la banque pour le test par contraste. `contrast_mode` :
    « voisine » (défaut) = une compétence voisine, pour savoir si la difficulté est bien localisée (contraste
    réussi) ou plus large (contraste échoué) ; « ecoute » = la MÊME compétence, mais le texte est lu à l'élève,
    pour savoir si la difficulté vient de la lecture du texte (réussi à l'écoute, échoué seul) ; « temps » = la
    MÊME compétence, mais l'élève est invité à relire et les réponses n'apparaissent qu'après quelques secondes,
    pour savoir si la difficulté vient d'un rythme trop rapide (réussi en prenant son temps, échoué sinon).
    `teacher_text` : les deux phrases montrées à l'enseignant ({noticed, proposal, source}), rédigées par le
    modèle et vérifiées par l'agent ; le serveur les refuse si elles contiennent une étiquette."""
    l = _require_learner(learner_id)
    for value in (teacher_text or {}).values():
        if label := find_forbidden_label(str(value)):
            raise Refused(tr("Phrase pour l'enseignant refusée : terme diagnostique ou étiquette interdit (« {label} »).", label=label))
    if skill not in SKILLS:
        raise Refused(tr("Compétence inconnue : {skill}.", skill=skill))
    if label := find_forbidden_label(hypothesis):
        raise Refused(tr("Hypothèse refusée : terme diagnostique ou étiquette interdit (« {label} »). Décrire l'erreur observable.",
                             label=label))
    items: list[dict] = []
    for ex_id in bank_exercise_ids or []:
        e = db.row("SELECT * FROM exercises WHERE id = ? AND origin = 'bank'", (ex_id,))
        if not e:
            raise Refused(tr("Exercice de banque inconnu : {ex_id}.", ex_id=ex_id))
        items.append(db.decode_exercise(e))
    for e in exercises or []:
        missing = {"prompt", "answer", "choices", "error_map"} - set(e)
        if missing:
            raise Refused(tr("Exercice incomplet, champs manquants : {missing}.", missing=sorted(missing)))
        choices = [str(c) for c in e["choices"]]
        if str(e["answer"]) not in choices or len(choices) < 3:
            raise Refused(tr("La bonne réponse doit figurer parmi au moins trois choix."))
        if len(set(choices)) != len(choices):
            raise Refused(tr("Exercice refusé : choix en double."))
        unmapped = [c for c in choices if c != str(e["answer"]) and c not in {str(k) for k in e["error_map"]}]
        if unmapped:
            raise Refused(tr("Exercice refusé : chaque mauvais choix doit correspondre à un type d'erreur ({unmapped}).",
                             unmapped=unmapped))
        if l["first_name"].lower() in e["prompt"].lower() and pick("a écrit", "wrote") in e["prompt"].lower():
            raise Refused(tr("Exercice refusé : l'énoncé parle de l'élève au lieu de s'adresser à lui."))
        bad = {v for v in e["error_map"].values() if v not in ERROR_TAXONOMY}
        if bad:
            raise Refused(tr("Types d'erreur hors taxonomie : {bad}.", bad=sorted(bad)))
        if label := find_forbidden_label(e["prompt"]):
            raise Refused(tr("Énoncé refusé (« {label} »).", label=label))
        items.append({"prompt": e["prompt"], "answer": str(e["answer"]), "choices": choices,
                      "error_map": {str(k): v for k, v in e["error_map"].items()}, "hint": e.get("hint"),
                      "read_aloud_text": e.get("read_aloud_text")})
    for e in items:
        e.update(skill=skill, probe="target")
    contrast = []
    if contrast_mode == "ecoute" and skill not in LISTENABLE:
        raise Refused(tr("Contraste à l'écoute impossible en {skill} : il n'y a pas de texte à lire à l'élève.", skill=skill))
    for ex_id in contrast_exercise_ids or []:
        e = db.row("SELECT * FROM exercises WHERE id = ? AND origin = 'bank'", (ex_id,))
        if contrast_mode == "voisine" and (not e or e["skill"] == skill):
            raise Refused(tr("Exercice de contraste invalide : {ex_id} (il doit venir de la banque, d'une autre compétence).",
                             ex_id=ex_id))
        if contrast_mode != "voisine" and (not e or e["skill"] != skill or ex_id in (bank_exercise_ids or [])):
            raise Refused(tr("Exercice de contraste invalide : {ex_id} (même compétence, différent des exercices cibles).",
                             ex_id=ex_id))
        contrast.append(db.decode_exercise(e) | {"probe": PROBES[contrast_mode]})
    if not 3 <= len(items) + len(contrast) <= 6 or len(items) < 2:
        raise Refused(tr("Il faut 3 à 6 exercices ciblés dont au moins 2 cibles (reçu {targets} + {contrasts}).",
                         targets=len(items), contrasts=len(contrast)))
    # Contraste intercalé (2e, 4e position…) pour que l'élève ne voie pas deux séries distinctes.
    ordered = []
    for i, e in enumerate(items):
        ordered.append(e)
        if i < len(contrast):
            ordered.append(contrast[i])
    ids = []
    with db.connect() as c:
        for e in ordered:
            new_id = f"T-{learner_id}-{uuid.uuid4().hex[:8]}"
            c.execute(
                "INSERT INTO exercises (id, subject, skill, level, prompt, answer, choices, error_map, hint, read_aloud_text,"
                " origin, status, target_learner_id, hypothesis, thread_id, created_at, probe, teacher_text)"
                " VALUES (?,?,?,?,?,?,?,?,?,?, 'targeted', 'pending', ?,?,?,?,?,?)",
                (new_id, SKILLS[e["skill"]]["subject"], e["skill"], l["level"], e["prompt"], e["answer"],
                 json.dumps(e["choices"], ensure_ascii=False), json.dumps(e["error_map"], ensure_ascii=False),
                 e.get("hint"), e.get("read_aloud_text"), learner_id, hypothesis, thread_id, audit.now(), e["probe"],
                 json.dumps(teacher_text, ensure_ascii=False) if teacher_text else None))
            ids.append(new_id)
    return {"ok": True, "status": "pending_teacher_approval", "exercise_ids": ids,
            "contrast": len(contrast), "contrast_mode": contrast_mode,
            "contrast_skill_suggested": CONTRAST.get(skill, (None,))[0],
            "note": tr("Exercices en attente : seul l'enseignant peut les valider depuis l'interface.")}


PROBES = {"voisine": "contrast", "ecoute": "listened", "temps": "slowed"}


def _check_sources(learner_id: int, sources: list[str]) -> dict[str, int]:
    if not sources:
        raise Refused(tr("Constat refusé : aucune source citée. Chaque constat doit citer les réponses, observations, "
                         "exercices ciblés ou relevés de présence dont il provient."))
    kinds: Counter = Counter()
    table = {"answer": ("answers", "learner_id"), "observation": ("observations", "learner_id"),
             "attendance": ("attendance", "learner_id"), "exercise": ("exercises", "target_learner_id"),
             "report": ("report_cards", "learner_id")}
    for ref in sources:
        kind, _, rid = str(ref).partition(":")
        if kind not in table or not rid:
            raise Refused(tr("Source mal formée : « {ref} » (attendu answer:ID, observation:ID, attendance:ID, report:ID ou "
                             "exercise:ID).", ref=ref))
        tbl, col = table[kind]
        r = db.row(f"SELECT {col} AS owner FROM {tbl} WHERE id = ?", (rid,))
        if not r or r["owner"] != learner_id:
            raise Refused(tr("Source introuvable ou appartenant à un autre élève : {ref}.", ref=ref))
        kinds[kind] += 1
    return dict(kinds)


@mcp.tool(description=_en_doc("update_profile"))
@logged
def update_profile(learner_id: int, kind: Literal["difficulty", "strength", "watch"], skill: str, statement: str,
                   sources: list[str], status: Literal["active", "ruled_out", "resolved"] = "active",
                   since: str | None = None, evidence: dict | None = None, thread_id: ThreadId = None) -> dict:
    """Enregistre dans le profil une difficulté, un point fort durable ou un point « à surveiller » (watch,
    par exemple des absences en hausse), en citant ses sources (answer:ID, observation:ID, attendance:ID,
    report:ID pour une note du livret scolaire, exercise:ID) et le trimestre depuis lequel c'est observé (`since`). Le serveur refuse tout constat sans
    source, tout terme diagnostique ou étiquette, toute comparaison avec la classe, et toute difficulté active
    non confirmée par des exercices ciblés réalisés. Un constat déjà validé par l'enseignant et modifié
    redevient « confirmé par l'agent » : l'enseignant doit le revalider."""
    problems, kinds = _finding_problems(learner_id, kind, skill, statement, sources, status, evidence)
    if problems:
        raise Refused(problems[0])
    existing = db.row("SELECT * FROM findings WHERE learner_id = ? AND skill = ? AND kind = ? AND status = 'active'",
                      (learner_id, skill, kind))
    subject = (SKILLS.get(skill) or OTHER_DOMAINS[skill])["subject"]
    with db.connect() as c:
        if existing:
            keep_validation = existing["statement"] == statement and status == "active"
            c.execute("UPDATE findings SET statement = ?, status = ?, since = COALESCE(?, since), sources = ?, evidence = ?,"
                      " thread_id = ?, updated_at = ?, validated_by = ?, validated_at = ? WHERE id = ?",
                      (statement, status, since, json.dumps(sources), json.dumps(evidence or {}, ensure_ascii=False),
                       thread_id, audit.now(), existing["validated_by"] if keep_validation else None,
                       existing["validated_at"] if keep_validation else None, existing["id"]))
            fid, action = existing["id"], "updated"
        else:
            cur = c.execute(
                "INSERT INTO findings (learner_id, kind, subject, skill, statement, status, since, sources, evidence,"
                " thread_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (learner_id, kind, subject, skill, statement, status, since, json.dumps(sources),
                 json.dumps(evidence or {}, ensure_ascii=False), thread_id, audit.now(), audit.now()))
            fid, action = cur.lastrowid, "created"
    return {"ok": True, "finding_id": fid, "action": action, "sources_by_kind": kinds}


def _finding_problems(learner_id: int, kind: str, skill: str, statement: str, sources: list[str], status: str,
                      evidence: dict | None) -> tuple[list[str], dict]:
    """Toutes les règles d'un constat, en un seul endroit : utilisées par update_profile (qui refuse) et par
    check_finding (qui vérifie sans rien écrire). Renvoie (problèmes, sources par type)."""
    l = _require_learner(learner_id)
    problems: list[str] = []
    if skill not in SKILLS and not (kind == "watch" and skill in OTHER_DOMAINS):
        return [tr("Compétence inconnue : {skill}.", skill=skill)], {}
    if pick("classe", "class") in statement.lower() and "%" in statement:
        problems.append(tr("Constat refusé : un profil ne compare jamais l'élève à ses camarades (retirer la moyenne de classe)."))
    sentence = ((evidence or {}).get("sentence") or {})
    if label := find_forbidden_label(statement + " " + str(sentence.get("text", ""))):
        problems.append(tr("Constat refusé : terme diagnostique ou étiquette interdit (« {label} »). "
                           "Décrire ce que l'élève réussit et ce qu'il ne réussit pas encore.", label=label))
    if sentence.get("source") == "modèle":
        if reason := wording.check_finding_sentence(sentence.get("text", ""), l["first_name"], kind, skill,
                                                    evidence or {}, status):
            problems.append(tr("Phrase pour l'enseignant refusée ({reason}) : envoyer la phrase fixe à la place.", reason=reason))
    try:
        kinds = _check_sources(learner_id, sources)
    except Refused as e:
        return problems + [str(e)], {}
    if kind == "difficulty" and status == "active":
        done = [x for x in sources if x.startswith("exercise:")]
        answered = db.rows(
            f"SELECT DISTINCT exercise_id FROM answers WHERE exercise_id IN ({','.join('?' * len(done))})",
            tuple(x.split(':', 1)[1] for x in done)) if done else []
        if not answered:
            problems.append(tr("Difficulté non enregistrée : elle doit être confirmée par des exercices ciblés, validés par "
                               "l'enseignant et réalisés par l'élève (citer exercise:ID)."))
        elif kinds.get("answer", 0) + kinds.get("observation", 0) < 2:
            problems.append(tr("Difficulté non enregistrée : citer aussi les réponses ou observations des trimestres concernés."))
    return problems, kinds


@mcp.tool(description=_en_doc("check_finding"))
@logged
def check_finding(learner_id: int, kind: Literal["difficulty", "strength", "watch"], skill: str, statement: str,
                  sources: list[str], status: Literal["active", "ruled_out", "resolved"] = "active",
                  evidence: dict | None = None, thread_id: ThreadId = None) -> dict:
    """Vérifie un constat AVANT de l'enregistrer, sans rien écrire : mêmes règles que update_profile (sources
    existantes et appartenant à l'élève, aucune étiquette de diagnostic, aucune comparaison avec la classe,
    difficulté confirmée par des exercices ciblés réalisés, phrase pour l'enseignant fidèle aux faits).
    Renvoie {ok, problems}."""
    problems, kinds = _finding_problems(learner_id, kind, skill, statement, sources, status, evidence)
    return {"ok": not problems, "problems": problems, "sources_by_kind": kinds}


@mcp.tool(description=_en_doc("compute_trends"))
@logged
def compute_trends(learner_id: int, thread_id: ThreadId = None) -> dict:
    """Tendances exactes d'un élève, calculées par le serveur sur tout son historique : pour chaque compétence,
    série par trimestre, trimestres faibles consécutifs (`pattern`, `low_terms`), trimestres forts consécutifs
    (`high_terms`), pente récente, erreur dominante et identifiants des réponses à citer ; présence
    (`attendance` : baisse, trimestre de départ, jours d'absence) ; baisses généralisées (`global_dips`).
    Un trimestre faible marqué par de fortes absences est « expliqué » et n'entre pas dans la tendance.
    Utiliser ces chiffres plutôt que de les estimer."""
    _require_learner(learner_id)
    return trends.compute(_timeline(learner_id))


@mcp.tool(description=_en_doc("find_learner"))
@logged
def find_learner(name: str, thread_id: ThreadId = None) -> dict:
    """Trouve un élève par son prénom et/ou son nom (accents et majuscules ignorés), ou par son matricule.
    Renvoie les élèves correspondants avec leur identifiant (learner_id), classe et niveau. Avec un nom vide,
    renvoie toute la classe de l'année en cours."""
    def plain(text: str) -> str:
        return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower().strip()
    words = plain(name).split()
    rows = db.rows("SELECT l.id, l.first_name, l.last_name, l.matricule, e.level, c.name AS class_name FROM learners l "
                   "LEFT JOIN enrollments e ON e.learner_id = l.id AND e.school_year = ? "
                   "LEFT JOIN classes c ON c.id = e.class_id ORDER BY l.last_name, l.first_name", (CURRENT_YEAR,))
    found = [r for r in rows if all(w in plain(f"{r['first_name']} {r['last_name']} {r['matricule'] or ''}") for w in words)]
    return {"count": len(found), "learners": [{"learner_id": r["id"], "name": f"{r['first_name']} {r['last_name']}",
                                               "matricule": r["matricule"], "level": r["level"], "class": r["class_name"]}
                                              for r in found]}


@mcp.tool(description=_en_doc("alert_teacher"))
@logged
def alert_teacher(kind: Literal["difficulty", "persistent", "strength", "watch", "ruled_out", "question", "document"],
                  message: str, learner_id: int | None = None, class_id: int | None = None,
                  finding_id: int | None = None, payload: dict | None = None, thread_id: ThreadId = None) -> dict:
    """Prévient l'enseignant de la classe actuelle de l'élève (ou de la classe `class_id` pour un document) :
    difficulté nouvelle ou persistante, point fort, hypothèse écartée, ou QUESTION quand un document est illisible
    ou que des données se contredisent (l'agent demande au lieu de deviner). `document` : lecture d'un document
    à faire confirmer par l'enseignant avant import."""
    if learner_id is not None:
        teacher_id = _require_learner(learner_id)["teacher_id"]
    elif class_id is not None:
        c = db.row("SELECT teacher_id FROM classes WHERE id = ?", (class_id,))
        if not c:
            raise Refused(tr("Classe {class_id} inconnue.", class_id=class_id))
        teacher_id = c["teacher_id"]
    else:
        raise Refused(tr("Indiquer l'élève (learner_id) ou la classe (class_id) concernée."))
    if label := find_forbidden_label(message):
        raise Refused(tr("Message refusé : terme diagnostique ou étiquette (« {label} »).", label=label))
    dup = None
    if learner_id is not None and kind not in ("question", "document"):
        dup = db.row("SELECT id FROM alerts WHERE learner_id = ? AND kind = ? AND status = 'open' AND "
                     "COALESCE(finding_id, -1) = COALESCE(?, -1)", (learner_id, kind, finding_id))
    elif kind == "question" and (payload or {}).get("request"):  # une demande d'information n'est faite qu'une fois
        dup = db.row("SELECT id FROM alerts WHERE learner_id = ? AND kind = 'question' AND "
                     "json_extract(payload, '$.request') = ?", (learner_id, payload["request"]))
        if dup:
            return {"ok": True, "alert_id": dup["id"], "action": "already_asked", "teacher_id": teacher_id}
    elif kind == "question" and (payload or {}).get("observation_id"):  # une contradiction n'est posée qu'une fois
        dup = db.row("SELECT id FROM alerts WHERE learner_id = ? AND kind = 'question' AND "
                     "json_extract(payload, '$.observation_id') = ?", (learner_id, payload["observation_id"]))
        if dup:
            return {"ok": True, "alert_id": dup["id"], "action": "already_asked", "teacher_id": teacher_id}
    with db.connect() as c:
        if dup:
            c.execute("UPDATE alerts SET message = ?, payload = ?, thread_id = ?, created_at = ? WHERE id = ?",
                      (message, json.dumps(payload, ensure_ascii=False), thread_id, audit.now(), dup["id"]))
            return {"ok": True, "alert_id": dup["id"], "action": "updated", "teacher_id": teacher_id}
        cur = c.execute(
            "INSERT INTO alerts (learner_id, teacher_id, kind, message, finding_id, payload, thread_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (learner_id, teacher_id, kind, message, finding_id, json.dumps(payload, ensure_ascii=False),
             thread_id, audit.now()))
    return {"ok": True, "alert_id": cur.lastrowid, "action": "created", "teacher_id": teacher_id}


def _next_term(year: str, term: int) -> tuple[str, int]:
    if term < 3:
        return year, term + 1
    start = int(year[:4]) + 1
    return f"{start}-{start + 1}", 1


@mcp.tool(description=_en_doc("schedule_followup"))
@logged
def schedule_followup(learner_id: int, reason: str, after_sessions: Annotated[int, Field(ge=1, le=10)] = 3,
                      finding_id: int | None = None, thread_id: ThreadId = None) -> dict:
    """Programme une prochaine vérification de l'élève par l'agent : il sera relancé automatiquement après
    `after_sessions` séances terminées ou au début du trimestre suivant, selon ce qui arrive en premier.
    À utiliser après un constat (difficulté, point à surveiller) pour vérifier qu'il persiste, se résout ou
    s'aggrave. Une seule vérification en attente par constat."""
    _require_learner(learner_id)
    if label := find_forbidden_label(reason):
        raise Refused(tr("Motif refusé : terme diagnostique ou étiquette (« {label} »).", label=label))
    dup = db.row("SELECT id FROM followups WHERE learner_id = ? AND status = 'pending' AND "
                 "COALESCE(finding_id, -1) = COALESCE(?, -1) AND (finding_id IS NOT NULL OR reason = ?)",
                 (learner_id, finding_id, reason))
    if dup:
        return {"ok": True, "followup_id": dup["id"], "action": "already_scheduled"}
    due_year, due_term = _next_term(CURRENT_YEAR, CURRENT_TERM)
    with db.connect() as c:
        cur = c.execute("INSERT INTO followups (learner_id, finding_id, reason, after_sessions, sessions_at_creation,"
                        " due_year, due_term, created_at, thread_id) VALUES (?,?,?,?,?,?,?,?,?)",
                        (learner_id, finding_id, reason, after_sessions, db.completed_sessions(learner_id),
                         due_year, due_term, audit.now(), thread_id))
    return {"ok": True, "followup_id": cur.lastrowid, "action": "scheduled",
            "when": tr("après {n} séances ou au {year} T{term}", n=after_sessions, year=due_year, term=due_term)}


@mcp.tool(description=_en_doc("draft_guardian_summary"))
@logged
def draft_guardian_summary(learner_id: int, text: str, sources: list[str], thread_id: ThreadId = None) -> dict:
    """Rédige un résumé en langage simple pour la famille. Il reste EN ATTENTE : l'enseignant le relit,
    le modifie si besoin et décide de le partager. L'agent ne contacte jamais la famille."""
    _require_learner(learner_id)
    if label := find_forbidden_label(text):
        raise Refused(tr("Résumé refusé : terme diagnostique ou étiquette (« {label} »).", label=label))
    _check_sources(learner_id, sources)
    with db.connect() as c:
        cur = c.execute("INSERT INTO summaries (learner_id, text, status, sources, thread_id, created_at)"
                        " VALUES (?,?, 'pending', ?,?,?)", (learner_id, text, json.dumps(sources), thread_id, audit.now()))
    return {"ok": True, "summary_id": cur.lastrowid, "status": "pending_teacher_approval"}


# ---------------------------------------------------------------------------
# Ressources (lecture seule)
# ---------------------------------------------------------------------------

@mcp.resource("xamkids://taxonomy/errors", name=tr("Taxonomie des erreurs"), mime_type="application/json")
def taxonomy() -> str:
    return json.dumps({"error_types": ERROR_TAXONOMY, "skills": SKILLS}, ensure_ascii=False)


@mcp.resource("xamkids://rules", name=tr("Règles de l'agent"), mime_type="text/plain")
def rules() -> str:
    return AGENT_RULES


@mcp.resource("xamkids://exercises/bank/{level}/{skill}", name=tr("Banque d'exercices"), mime_type="application/json")
def exercise_bank(level: str, skill: str) -> str:
    if level not in LEVELS or skill not in SKILLS:
        return json.dumps({"error": tr("niveau ou compétence inconnu"), "levels": LEVELS, "skills": list(SKILLS)})
    items = [db.decode_exercise(e) for e in db.rows(
        "SELECT id, skill, level, prompt, answer, choices, error_map, hint FROM exercises "
        "WHERE origin = 'bank' AND level = ? AND skill = ?", (level, skill))]
    return json.dumps(items, ensure_ascii=False)


@mcp.resource("xamkids://classes/{class_id}/roster", name=tr("Liste de classe"), mime_type="application/json",
              description=pick(None, "Learners enrolled in a class (identifier, first name, last name, student ID), to match "
                                     "uploaded documents."))
def class_roster(class_id: str) -> str:
    """Élèves inscrits dans une classe (identifiant, prénom, nom), pour rapprocher les documents téléversés."""
    return json.dumps([{k: l[k] for k in ("id", "first_name", "last_name", "matricule")}
                       for l in db.learners_in_class(int(class_id))],
                      ensure_ascii=False)


@mcp.resource("xamkids://learners/{learner_id}/situation", name=tr("Situation d'un élève"), mime_type="application/json",
              description=pick(None, "Short view for planning: active findings, hypotheses being tested, last session "
                                     "(without the answers)."))
def learner_situation(learner_id: str) -> str:
    """Vue courte pour planifier : constats actifs, hypothèses en test, dernière séance (sans les réponses)."""
    lid = int(learner_id)
    l = db.learner(lid)
    if not l:
        return json.dumps({"error": tr("élève inconnu")})
    last = db.row("SELECT * FROM sessions WHERE learner_id = ? AND ended_at IS NOT NULL ORDER BY id DESC LIMIT 1", (lid,))
    last_session = None
    if last:
        rows = db.rows("SELECT x.subject, a.correct FROM answers a JOIN exercises x ON x.id = a.exercise_id "
                       "WHERE a.session_id = ?", (last["id"],))
        last_session = {"id": last["id"], "kind": last["kind"], "date": last["ended_at"][:10], "answers": len(rows),
                        "subjects": sorted({r["subject"] for r in rows}),
                        "first_try_correct": sum(r["correct"] for r in rows)}
    return json.dumps({
        "learner": {"first_name": l["first_name"], "level": l["level"], "school": l["school_name"]},
        "active_findings": [{"kind": f["kind"], "skill": f["skill"], "validated": bool(f["validated_by"])}
                            for f in db.findings(lid, status="active")],
        "hypotheses_in_test": db.rows("SELECT DISTINCT skill, hypothesis, status FROM exercises WHERE origin = 'targeted' "
                                      "AND target_learner_id = ? AND status IN ('pending', 'approved') "
                                      "AND COALESCE(probe, 'target') = 'target'", (lid,)),
        "last_session": last_session,
        "scheduled_followups": [{k: f[k] for k in ("id", "reason", "sessions_left", "due_year", "due_term")}
                                for f in db.followups(lid)],
    }, ensure_ascii=False)


def main() -> None:
    db.init()
    mcp.run()


if __name__ == "__main__":
    main()
