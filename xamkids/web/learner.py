"""Espace élève : choix de l'élève, accueil, séance guidée par la voix, bilan et ressenti.

Règles respectées ici : l'élève ne voit jamais les constats de son profil, n'est jamais comparé à ses
camarades et ne reçoit aucune suggestion d'orientation. Il voit ses propres progrès et ses efforts.
"""
from __future__ import annotations

import threading
import time

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from .. import agent
from ..config import CURRENT_YEAR
from ..i18n import tr
from ..records import db, sessions
from . import plural, voice

bp = Blueprint("learner", __name__, url_prefix="/eleve")

ACTIVITIES = [  # (sujet, icône, titre, description, classe CSS)
    ("", "", tr("Séance du jour"), tr("Un peu de tout : calcul, problèmes, lecture."), ""),
    ("maths", "+ −", tr("Mathématiques"), tr("Calculs, nombres, problèmes"), ""),
    ("francais", "Aa", tr("Français"), tr("Lecture, mots, phrases"), ""),
]
LIKED = [tr("Les calculs"), tr("Les problèmes"), tr("Les lectures"), tr("Les mots"), tr("Les phrases")]


def _learner(lid: int) -> dict:
    l = db.learner(lid)
    if not l or not l["class_id"]:
        abort(404)
    return l


def _exercise(exercise_id: str) -> dict:
    return db.decode_exercise(db.row("SELECT * FROM exercises WHERE id = ?", (exercise_id,)))


def _speak_once(key: str, text: str) -> list[str]:
    """Un texte n'est dit automatiquement qu'une fois (pas à chaque rechargement)."""
    said = session.setdefault("said", [])
    if key in said:
        return []
    said.append(key)
    session["said"] = said[-50:]
    return [voice.clip(text)]


# -- Code à 4 chiffres -----------------------------------------------------------------------
# Après avoir touché son prénom, l'élève tape son code : personne ne fait les exercices à la place d'un camarade
# (ses réponses seraient comptées pour un autre et fausseraient l'analyse de l'agent).

PIN_FREE = {"learner.choose", "learner.code", "learner.check_code"}
MAX_TRIES, LOCK_SECONDS = 5, 60


@bp.before_request
def _require_code():
    lid = (request.view_args or {}).get("lid")
    if request.endpoint in PIN_FREE or lid is None:
        return None
    if session.get("learner_ok") != lid:
        return redirect(url_for(".code", lid=lid))
    return None


@bp.get("/<int:lid>/code")
def code(lid: int):
    l = _learner(lid)
    return render_template("learner/code.html", l=l, locked=_locked(lid))


@bp.post("/<int:lid>/code")
def check_code(lid: int):
    _learner(lid)
    if _locked(lid):
        return redirect(url_for(".code", lid=lid))
    tries = session.get("pin_tries", {})
    if request.form.get("pin", "") == db.learner_pin(lid):
        session["learner_ok"] = lid
        tries.pop(str(lid), None)
        session["pin_tries"] = tries
        return redirect(url_for(".home", lid=lid))
    n, _ = tries.get(str(lid), (0, 0))
    tries[str(lid)] = (n + 1, time.time())
    session["pin_tries"] = tries
    flash(tr("Ce n'est pas le bon code. Essaie encore !"), "warn")
    return redirect(url_for(".code", lid=lid))


def _locked(lid: int) -> bool:
    n, at = session.get("pin_tries", {}).get(str(lid), (0, 0))
    return n >= MAX_TRIES and time.time() - at < LOCK_SECONDS


# -- Choix de l'élève et accueil ------------------------------------------------------------

@bp.get("/")
def choose():
    session.pop("learner_ok", None)  # revenir à la liste des prénoms ferme la session de l'élève
    cls = db.row("SELECT * FROM classes WHERE school_year = ? ORDER BY id LIMIT 1", (CURRENT_YEAR,))
    return render_template("learner/choose.html", learners=db.learners_in_class(cls["id"]), cls=cls)


@bp.get("/<int:lid>")
def home(lid: int):
    l = _learner(lid)
    voice_urls = _speak_once(f"hello-{lid}", tr("Bonjour {name} ! Que veux-tu faire aujourd'hui ? "
                                                "Choisis la séance du jour, les mathématiques ou le français.",
                                                name=l["first_name"]))
    return render_template("learner/home.html", l=l, activities=ACTIVITIES, progress=sessions.progress(lid),
                           interests=sessions.INTERESTS, mine=sessions.interests(lid),
                           voice_urls=voice_urls)


@bp.post("/<int:lid>/interets")
def save_interests(lid: int):
    _learner(lid)
    sessions.save_interests(lid, request.form.getlist("interest"))
    flash(tr("C'est noté !"))
    return redirect(url_for(".home", lid=lid))


# -- Séance ------------------------------------------------------------------------------

@bp.post("/<int:lid>/seance")
def start(lid: int):
    _learner(lid)
    kind, exercises = sessions.next_exercises(lid, subject=request.form.get("sujet") or None)
    session["seance"] = {"lid": lid, "sid": sessions.start_session(lid, kind), "kind": kind,
                         "ex": [e["id"] for e in exercises], "i": 0, "score": 0, "second": 0, "prefix": ""}
    return redirect(url_for(".question", lid=lid))


@bp.get("/<int:lid>/seance")
def question(lid: int):
    s = session.get("seance")
    if not s or s["lid"] != lid:
        return redirect(url_for(".home", lid=lid))
    if s["i"] >= len(s["ex"]):
        return _finish(lid, s)
    e = _exercise(s["ex"][s["i"]])
    q = s.get("q")
    if not q or q["i"] != s["i"]:
        q = s["q"] = {"i": s["i"], "t0": time.time(), "attempts": 0, "first": None, "seconds": None,
                      "read_aloud": e.get("probe") == "listened", "hint": False, "retry": False}
    key = f"q-{s['sid']}-{s['i']}"
    voice_urls = _speak_once(key, s.pop("prefix", "") + voice.instruction(e))
    if q["retry"]:
        voice_urls += _speak_once(f"{key}-retry", tr("Pas tout à fait. Relis bien et essaie encore une fois !"))
    feedback = s.pop("feedback", None)
    session["seance"] = s
    return render_template("learner/question.html", l=_learner(lid), e=e, s=s, q=q, voice_urls=voice_urls,
                           feedback=feedback,
                           listen_url=voice.clip(e.get("read_aloud_text") or e["prompt"]),
                           hint_url=voice.clip(e.get("hint")))


@bp.post("/<int:lid>/seance/reponse")
def answer(lid: int):
    """Premier essai faux : un deuxième essai est proposé. La première réponse et son temps sont ceux enregistrés."""
    s = session.get("seance")
    if not s or s["lid"] != lid or s["i"] >= len(s["ex"]):
        return redirect(url_for(".home", lid=lid))
    e, q = _exercise(s["ex"][s["i"]]), s["q"]
    choice = request.form.get("choice", "")
    q["read_aloud"] |= request.form.get("read_aloud") == "1"  # signal observé par l'agent
    q["hint"] |= request.form.get("hint") == "1"
    q["attempts"] += 1
    right = choice == str(e["answer"])
    if q["attempts"] == 1:
        q["first"], q["seconds"] = choice, time.time() - q["t0"]
        if not right:
            q["retry"] = True
            session["seance"] = s
            return redirect(url_for(".question", lid=lid))
    first_right = q["first"] == str(e["answer"])
    sessions.save_answer(s["sid"], lid, e["id"], q["first"], first_right, q["seconds"], q["attempts"],
                         q["read_aloud"], q["hint"], None if q["attempts"] == 1 else right)
    s["score"] += int(first_right)
    s["second"] += int(not first_right and right)
    s["i"] += 1
    if first_right:
        s["feedback"], s["prefix"] = ("ok", tr("Bravo !")), tr("Bravo ! ")
    elif right:
        s["feedback"], s["prefix"] = ("ok", tr("C'est ça, bravo ! ⭐")), tr("C'est ça, bravo ! ")
    else:
        s["feedback"] = ("info", tr("La bonne réponse était : {answer}", answer=e["answer"]))
        s["prefix"] = tr("La bonne réponse était : {answer}. On continue ! ", answer=e["answer"])
    session["seance"] = s
    return redirect(url_for(".question", lid=lid))


@bp.post("/<int:lid>/seance/arreter")
def stop(lid: int):
    """L'élève peut s'arrêter : les réponses déjà données sont gardées et analysées."""
    s = session.get("seance")
    if s and s["lid"] == lid:
        s["ex"] = s["ex"][:s["i"]]
        session["seance"] = s
    return redirect(url_for(".question", lid=lid))


def _finish(lid: int, s: dict):
    sessions.end_session(s["sid"])
    session.pop("seance", None)
    if not s["ex"]:  # arrêtée avant la première réponse
        return redirect(url_for(".home", lid=lid))
    _analyse_in_background(lid, s["sid"], s["kind"])
    session["bilan"] = {"lid": lid, "sid": s["sid"], "score": s["score"], "second": s["second"], "total": len(s["ex"])}
    return redirect(url_for(".recap", lid=lid))


def _analyse_in_background(lid: int, session_id: int, kind: str) -> None:
    """Déclencheur : après chaque séance, l'agent analyse sans faire attendre l'élève."""
    def job():
        if kind == "targeted":
            for thread_id in agent.waiting_threads(lid, "results"):
                agent.resume(thread_id, {"session_id": session_id})
        else:
            agent.run("session", learner_id=lid, session_id=session_id)
        agent.run_due_followups(lid)  # vérifications que l'agent s'était programmées pour après N séances
    threading.Thread(target=job, daemon=True).start()


# -- Bilan et ressenti ---------------------------------------------------------------------

@bp.get("/<int:lid>/bilan")
def recap(lid: int):
    b = session.get("bilan")
    if not b or b["lid"] != lid:
        return redirect(url_for(".home", lid=lid))
    l = _learner(lid)
    stars = 1 + b["second"]  # une étoile pour la séance terminée, une par réponse trouvée au deuxième essai
    message = (plural(b["score"], "Bravo {name}, séance terminée ! Tu as trouvé {n} réponse du premier coup sur {total}",
                      "Bravo {name}, séance terminée ! Tu as trouvé {n} réponses du premier coup sur {total}",
                      name=l["first_name"], total=b["total"])
               + (tr(", et {n} de plus au deuxième essai", n=b["second"]) if b["second"] else "") + ".")
    cheer = sessions.encouragement(lid)
    voice_urls = _speak_once(f"bilan-{b['sid']}", tr("{message} {cheer} Dis-moi comment c'était.", message=message,
                                                     cheer=cheer))
    return render_template("learner/recap.html", l=l, b=b, stars=stars, message=message, cheer=cheer,
                           feelings=sessions.FEELINGS,
                           liked=LIKED, voice_urls=voice_urls)


@bp.post("/<int:lid>/bilan")
def save_recap(lid: int):
    b = session.pop("bilan", None)
    if b and b["lid"] == lid and request.form.get("action") != "later":
        sessions.save_reflection(lid, b["sid"], request.form.get("feeling") or None, request.form.getlist("liked"))
        flash(tr("Merci !"))
    return redirect(url_for(".home", lid=lid))
