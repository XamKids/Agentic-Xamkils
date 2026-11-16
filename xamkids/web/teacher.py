"""Espace enseignant : classe, alertes, validations, profils, documents, raisonnement de l'agent, audit.

Les actions longues de l'agent (revue de trimestre, reprise après validation, lecture d'un document…)
tournent en arrière-plan : la page affiche leur avancement et se recharge quand elles sont finies.
"""
from __future__ import annotations

import hmac
import json
import re
import time

from flask import (Blueprint, Response, abort, flash, g, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)

from .. import agent
from ..config import CURRENT_TERM, CURRENT_YEAR, MIN_ANSWERS_PER_TERM, ROOT, TEACHER_PIN, UPLOAD_DIR
from ..knowledge import CLASSROOM_TIPS, ERROR_SHORT, ERROR_TAXONOMY, SKILLS, domain_label, short_label
from .. import wording
from ..i18n import LANG, tr
from ..records import audit, db, decisions, sessions
from . import jobs, plural

bp = Blueprint("teacher", __name__, url_prefix="/enseignant")

SAMPLES_DIR = ROOT / "samples"
TRIGGER_LABEL = {"term_review": tr("Revue de trimestre"), "session": tr("Après une séance"), "document": tr("Document"),
                 "guardian_summary": tr("Résumé famille"), "targeted_session": tr("Exercices ciblés"),
                 "followup": tr("Vérification programmée")}
KIND_LABEL = {"difficulty": (tr("Difficulté"), "difficulty"), "persistent": (tr("Suivi"), "watch"),
              "strength": (tr("Point fort"), "strength"),
              "watch": (tr("À surveiller"), "watch"), "ruled_out": (tr("Hypothèse écartée"), "test"),
              "question": (tr("Question de l'agent"), "info"), "document": (tr("Document à confirmer"), "info")}
SKILL_COLORS = ["#0F7B4F", "#2F80ED", "#E8694A", "#7B5CD6", "#D99A0B", "#0E9AA7", "#B5446E"]
QUESTION_KINDS = ("question", "document")  # alertes qui attendent une décision de l'enseignant


# -- Contexte commun ------------------------------------------------------------------------

LOGIN_FREE = ("teacher.choose", "teacher.pick", "teacher.code", "teacher.check_code", "teacher.api_jobs")


@bp.before_request
def load_teacher():
    if request.endpoint in LOGIN_FREE:
        return None
    current = [t for t in db.teachers() if db.classes_for(t["id"])]
    # Chaque enseignant se connecte avec son code : on ne tombe jamais sur la classe d'un autre.
    if session.get("teacher_ok") not in {t["id"] for t in current} or session.get("teacher_id") != session.get("teacher_ok"):
        return redirect(url_for(".choose"))
    g.teacher = next(t for t in current if t["id"] == session["teacher_id"])
    g.cls = db.classes_for(g.teacher["id"])[0]
    g.learners = db.learners_in_class(g.cls["id"])
    g.names = {l["id"]: f"{l['first_name']} {l['last_name']}" for l in g.learners}
    return None


@bp.context_processor
def layout_context():
    if "teacher" not in g:
        return {}
    for j in jobs.take_finished():
        flash(tr("{label} : {message}", label=j["label"], message=j["message"]), "warn" if j["status"] == "error" else "info")
    pending = len({e["thread_id"] for e in db.pending_exercises(g.teacher["id"])}) + len(db.pending_summaries(g.teacher["id"]))
    school = db.row("SELECT * FROM schools WHERE id = ?", (g.cls["school_id"],))
    open_alerts = db.alerts(teacher_id=g.teacher["id"], status="open")
    return {"teacher": g.teacher, "cls": g.cls, "school": school, "names": g.names, "running_jobs": jobs.running(),
            "n_alerts": sum(a["kind"] in QUESTION_KINDS for a in open_alerts),
            "n_news": len({a.get("finding_id") or f"a{a['id']}" for a in open_alerts if a["kind"] not in QUESTION_KINDS}),
            "n_pending": pending,
            "KIND_LABEL": KIND_LABEL, "TRIGGER_LABEL": TRIGGER_LABEL, "SKILLS": SKILLS, "ERROR_TAXONOMY": ERROR_TAXONOMY}


def _job(label: str, fn, total: int = 1, back: str | None = None):
    jobs.start(label, fn, total)
    return redirect(back or request.referrer or url_for(".dashboard"))


@bp.get("/choisir")
def choose():
    for k in ("teacher_ok", "teacher_id", "teacher_pending"):
        session.pop(k, None)
    return render_template("teacher/choose.html", teachers=[t for t in db.teachers() if db.classes_for(t["id"])])


@bp.post("/choisir")
def pick():
    session["teacher_pending"] = int(request.form["teacher_id"])
    return redirect(url_for(".code"))


@bp.get("/code")
def code():
    t = next((t for t in db.teachers() if t["id"] == session.get("teacher_pending")), None)
    if not t:
        return redirect(url_for(".choose"))
    return render_template("teacher/code.html", teacher=t)


@bp.post("/code")
def check_code():
    tid = session.get("teacher_pending")
    if tid is None:
        return redirect(url_for(".choose"))
    if hmac.compare_digest(request.form.get("code", ""), TEACHER_PIN):
        session.pop("teacher_pending", None)
        session["teacher_id"] = session["teacher_ok"] = tid
        audit.log(next(t["name"] for t in db.teachers() if t["id"] == tid), "interface", "teacher_login")
        return redirect(url_for(".dashboard"))
    flash(tr("Ce n'est pas le bon code. Essaie encore !"), "warn")
    return redirect(url_for(".code"))


@bp.get("/api/jobs")
def api_jobs():
    return jsonify([{k: j[k] for k in ("label", "status", "done", "total", "message")} for j in jobs.running()])


# -- Classe ------------------------------------------------------------------------------

@bp.get("/")
def dashboard():
    rows = [_class_row(l) for l in g.learners]
    n_difficulties = sum(len(r["difficulties"]) for r in rows)
    return render_template("teacher/dashboard.html", rows=rows, n_difficulties=n_difficulties)


def _class_row(l: dict) -> dict:
    stats = [s for s in db.term_skill_stats(l["id"]) if (s["school_year"], s["term"]) < (CURRENT_YEAR, CURRENT_TERM)]
    last = max(((s["school_year"], s["term"]) for s in stats), default=None)
    last_stats = [s for s in stats if (s["school_year"], s["term"]) == last]
    accuracy = sum(s["accuracy"] * s["n"] for s in last_stats) / max(1, sum(s["n"] for s in last_stats))
    findings = [f for f in db.findings(l["id"]) if f["status"] == "active"]
    in_test = db.row("SELECT COUNT(DISTINCT thread_id) AS n FROM exercises WHERE target_learner_id = ? "
                     "AND origin = 'targeted' AND status IN ('pending', 'approved')", (l["id"],))["n"]
    return {"l": l, "accuracy": accuracy, "in_test": in_test, "lines": _overview_lines(l["id"], findings),
            "strengths": [f for f in findings if f["kind"] == "strength"],
            "difficulties": [f for f in findings if f["kind"] == "difficulty"],
            "watch": [f for f in findings if f["kind"] == "watch"],
            "alerts": len(db.alerts(learner_id=l["id"], status="open"))}


def _finding_line(f: dict) -> dict:
    """Un constat en quelques mots : quoi (la compétence) et pourquoi (l'erreur, le niveau, la durée)."""
    ev = f.get("evidence") or {}
    if f["kind"] == "difficulty":
        parts = [ERROR_SHORT.get(ev.get("dominant_error"), "")]
        if ev.get("low_terms"):
            parts.append(plural(len(ev["low_terms"]), "depuis {n} trimestre", "depuis {n} trimestres"))
        label = ("difficulty", tr("Difficulté"))
    elif f["kind"] == "strength":
        m = re.search(r"(\d+) ?%" if LANG == "en" else r"(\d+) %", f["statement"] or "")
        parts = [(f"{m.group(1)}%" if LANG == "en" else f"{m.group(1)}\u00a0%") if m else ""]
        label = ("strength", tr("Point fort"))
    elif f["skill"] == "presence" and ev.get("latest_absences") is not None:
        parts = [tr("absences en hausse, {n} jours au dernier trimestre", n=ev["latest_absences"])]
        label = ("watch", tr("À surveiller"))
    else:
        head = (f["statement"] or "").split(" : ")[0]
        if LANG == "en":
            head = head.split(": ")[0]
        parts = [head.split(" (")[0].lower()]
        label = ("watch", tr("À surveiller"))
    return {"cls": label[0], "label": label[1], "what": short_label(f["skill"]),
            "detail": ", ".join(p for p in parts if p)}


def _finding_sentence(f: dict) -> tuple[str, str]:
    """(type, phrase) d'un constat pour l'enseignant. La phrase a été rédigée par le modèle et vérifiée par le
    code au moment où l'agent a enregistré le constat ; à défaut, phrase fixe construite par le code."""
    ev = f.get("evidence") or {}
    status = f["status"] if f["status"] in ("ruled_out", "resolved") else "active"
    title = wording.KIND_TITLE.get(status if status != "active" else f["kind"], "")
    stored = (ev.get("sentence") or {}).get("text")
    if stored and status == "active":
        return title, stored
    first = (g.names.get(f["learner_id"], "") or "").split(" ")[0]
    return title, f"{first} {wording.finding_template(f['kind'], f['skill'], ev, f['statement'], status)}"


def _overview_lines(lid: int, findings: list[dict]) -> list[dict]:
    """Une phrase courte par constat pour la vue d'ensemble : quoi, et en quelques mots pourquoi."""
    lines = [_finding_line(f) for f in sorted(findings, key=lambda f: ["difficulty", "watch", "strength"].index(f["kind"]))]
    for h in _hypotheses_in_test(lid):
        lines.append({"cls": "test", "label": tr("À vérifier"), "what": short_label(h["skill"]),
                      "detail": tr("exercices à valider") if h["status"] == "pending" else tr("exercices en cours")})
    # Un seul libellé par type : « Points forts · Calcul 93 %, Lecture de mots 86 % ».
    groups: dict = {}
    for x in lines:
        grp = groups.setdefault(x["cls"], {"cls": x["cls"], "label": x["label"], "entries": []})
        grp["entries"].append(x)
    plural_label = {tr("Difficulté"): tr("Difficultés"), tr("Point fort"): tr("Points forts")}
    for grp in groups.values():
        if len(grp["entries"]) > 1:
            grp["label"] = plural_label.get(grp["label"], grp["label"])
        details = {x["detail"] for x in grp["entries"]}
        grp["common"] = details.pop() if grp["cls"] == "test" and len(details) == 1 else None
    return list(groups.values())


@bp.post("/classe/revue")
def review():
    learners = dict(g.names)

    def run(progress):
        results = agent.run_many("term_review", list(learners),
                                 on_progress=lambda i, job: progress(i, learners[job["learner_id"]]))
        waiting = sum(r["status"] == "waiting" for r in results)
        errors = sum(r["status"] == "error" for r in results)
        return (tr("{n} élèves examinés, {waiting} hypothèse(s) en attente de votre validation.", n=len(learners),
                   waiting=waiting)
                + (tr(" {errors} erreur(s) : voir « Raisonnement de l'agent ».", errors=errors) if errors else ""))
    return _job(tr("Revue de fin de trimestre"), run, total=len(learners))


# -- Alertes ------------------------------------------------------------------------------

@bp.get("/alertes")
def alerts():
    items = db.alerts(teacher_id=g.teacher["id"])
    open_items = [a for a in items if a["status"] == "open"]
    found = {}
    for a in open_items:
        if a.get("finding_id") and a["learner_id"]:
            if a["learner_id"] not in found:
                found[a["learner_id"]] = {f["id"]: f for f in db.findings(a["learner_id"])}
            f = found[a["learner_id"]].get(a["finding_id"])
            a["sentence"] = _finding_sentence(f) if f else None
    news, by_finding = [], {}
    for a in open_items:  # une seule ligne par constat, même si l'agent a envoyé plusieurs alertes dessus
        if a["kind"] in QUESTION_KINDS:
            continue
        first = by_finding.get(a.get("finding_id")) if a.get("finding_id") else None
        if first:
            first["also"].append(a["id"])
            if a["kind"] == "difficulty":
                first["kind"] = "difficulty"
            continue
        a["also"] = []
        news.append(a)
        if a.get("finding_id"):
            by_finding[a["finding_id"]] = a
    return render_template("teacher/alerts.html",
                           questions=[a for a in open_items if a["kind"] in QUESTION_KINDS],
                           news=news,
                           closed=[a for a in items if a["status"] != "open"])


@bp.post("/alertes/tout-lu")
def read_all():
    """Les nouveaux constats sont des informations : on peut les marquer comme lus d'un coup.
    Les questions de l'agent, elles, demandent une réponse une par une."""
    n = 0
    for a in db.alerts(teacher_id=g.teacher["id"], status="open"):
        if a["kind"] not in QUESTION_KINDS:
            decisions.answer_alert(a["id"], g.teacher["name"], tr("Lu."))
            n += 1
    flash(plural(n, "{n} constat marqué comme lu.", "{n} constats marqués comme lus."))
    return redirect(url_for(".alerts"))


@bp.post("/alertes/<int:alert_id>/traiter")
def close_alert(alert_id: int):
    response = request.form.get("response", "").strip()
    decisions.answer_alert(alert_id, g.teacher["name"], response or tr("Vu."))
    for other in request.form.getlist("also", type=int):  # alertes en double sur le même constat
        decisions.answer_alert(other, g.teacher["name"], tr("Vu."))
    a = db.row("SELECT learner_id FROM alerts WHERE id = ?", (alert_id,))
    if a and a["learner_id"] and response:  # la réponse devient une observation que l'agent pourra citer
        decisions.add_observation(a["learner_id"], g.teacher["name"], response, source=tr("réponse à l'alerte {id}", id=alert_id))
    return redirect(url_for(".alerts"))


@bp.post("/alertes/<int:alert_id>/importer")
def import_alert(alert_id: int):
    n = decisions.import_document_rows(alert_id, g.teacher["name"])
    flash(tr("{n} lignes importées dans le dossier scolaire.", n=n))
    return redirect(url_for(".alerts"))


# -- Validations --------------------------------------------------------------------------

@bp.get("/validations")
def approvals():
    groups: dict[str, list[dict]] = {}
    for e in db.pending_exercises(g.teacher["id"]):
        groups.setdefault(e["thread_id"], []).append(e)
    approved = db.rows("SELECT * FROM summaries WHERE status = 'approved' ORDER BY reviewed_at DESC LIMIT 10")
    return render_template("teacher/approvals.html", groups=groups, summaries=db.pending_summaries(g.teacher["id"]),
                           approved=approved, plain={t: _proposal_sentences(exs) for t, exs in groups.items()})


def _proposal_sentences(exs: list[dict]) -> dict:
    """Ce que l'agent a remarqué, puis ce qu'il propose : les phrases rédigées par le modèle (vérifiées par le
    code) si l'agent les a enregistrées, sinon les phrases fixes construites à partir des mêmes faits."""
    stored = exs[0].get("teacher_text")
    if stored:
        return json.loads(stored) if isinstance(stored, str) else stored
    learner = db.learner(exs[0]["target_learner_id"]) or {}
    target = [e for e in exs if e.get("probe") in (None, "target")]
    skill = (target or exs)[0]["skill"]
    groups = [(len(target), "target")] if target else []
    for probe in ("contrast", "listened", "slowed"):
        group = [e for e in exs if e.get("probe") == probe]
        if group:
            groups.append((len(group), f"contrast:{group[0]['skill']}" if probe == "contrast" else probe))
    facts = wording.proposal_facts(learner.get("first_name", tr("L'élève")), skill, exs[0].get("hypothesis") or "", groups)
    return wording.proposal_template(facts)


@bp.post("/validations/exercices/<thread_id>")
def review_exercises(thread_id: str):
    approve = request.form.get("decision") == "approve"
    comment = request.form.get("comment", "").strip()
    ids = [e["id"] for e in db.pending_exercises(g.teacher["id"]) if e["thread_id"] == thread_id]
    decisions.review_exercises(ids, g.teacher["name"], approve, comment)
    teacher = g.teacher["name"]
    return _job(tr("Reprise de l'agent après votre décision"),
                lambda progress: agent.resume(thread_id, {"approved": approve, "teacher": teacher, "comment": comment})["outcome"])


@bp.post("/validations/resume/<int:summary_id>")
def review_summary(summary_id: int):
    approve = request.form.get("decision") == "approve"
    decisions.review_summary(summary_id, g.teacher["name"], approve, request.form.get("text") if approve else None)
    flash(tr("Résumé validé : vous pouvez le télécharger et le partager avec la famille.") if approve
          else tr("Résumé refusé."))
    return redirect(url_for(".approvals"))


@bp.get("/resumes/<int:summary_id>.txt")
def download_summary(summary_id: int):
    s = db.row("SELECT * FROM summaries WHERE id = ? AND status = 'approved'", (summary_id,))
    if not s:
        abort(404)
    return Response(s["final_text"], mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=resume_{summary_id}.txt"})


# -- Profil élève -----------------------------------------------------------------------------

@bp.get("/eleves/<int:lid>")
def profile(lid: int):
    if lid not in g.names:
        abort(404)
    findings = db.findings(lid)
    for f in findings:
        f["resolved"] = db.resolve_sources(f["sources"])
        f["facts"] = _facts(f)
    active = [f for f in findings if f["status"] == "active"]
    tab = request.args.get("vue", "constats")
    if tab not in ("constats", "parcours", "observations"):
        tab = "constats"
    return render_template(
        "teacher/profile.html", l=db.learner(lid), lid=lid, active=active, tab=tab,
        past=[f for f in findings if f["status"] != "active"], hypotheses=_hypotheses_in_test(lid),
        frise=_frise(lid, findings), minis=_minis(lid), learner_ids=list(g.names), interests=sessions.interests(lid),
        observations=db.observations(lid), schooling=db.schooling(lid), livret=_livret(lid),
        followups=db.followups(lid), pin=db.learner_pin(lid),
        summaries=[s for s in db.summaries(lid) if s["status"] == "approved"])


def _facts(f: dict) -> dict | None:
    """Lecture structurée d'un constat de difficulté, à partir des preuves enregistrées par l'agent :
    ce qui se passe, depuis quand, la réussite, le test de l'agent et une piste de classe."""
    ev = f.get("evidence") or {}
    if f["kind"] == "watch" and f["skill"] == "presence" and ev.get("latest_absences") is not None:
        rows = [(tr("Ce qui se passe"), tr("Absences en hausse")),
                (tr("Dernier trimestre"), tr("{n} jours d'absence · présence {rate} %", n=ev["latest_absences"],
                                             rate=round(ev["latest_rate"] * 100))),
                (tr("D'habitude"), tr("présence {rate} %", rate=round(ev["previous_mean"] * 100)))]
        return {"rows": rows, "tip": tr("En parler avec l'élève, et avec sa famille si vous le jugez utile."),
                "tip_label": tr("Piste")}
    if f["kind"] != "difficulty" or "low_terms" not in ev:
        return None
    err = ev.get("dominant_error")
    rows = []
    if err in ERROR_TAXONOMY:
        share = ev.get("dominant_error_share")
        rows.append((tr("Ce qui se passe"), ERROR_TAXONOMY[err]
                     + (tr(" ({pct} % de ses erreurs)", pct=round(share * 100)) if share else "")))
    n_terms = len(ev["low_terms"])
    rows.append((tr("Depuis"), tr("{since} · ", since=ev.get("since") or f.get("since"))
                 + plural(n_terms, "{n} trimestre de suite", "{n} trimestres de suite")))
    if ev.get("mean_acc_low_terms") is not None:
        rows.append((tr("Réussite"), tr("{pct} % sur cette période", pct=round(ev["mean_acc_low_terms"] * 100))
                     + (tr(" · classe : {pct} %", pct=round(ev["class_acc"] * 100)) if ev.get("class_acc") is not None
                        else "")))
    t = ev.get("targeted") or {}
    if t.get("n"):
        target = tr("{skill} : {c}/{n}", skill=short_label(f["skill"]), c=t["correct"], n=t["n"])
        if t.get("mode") == "listened":
            test = tr("Énoncés lus à voix haute : {cc}/{cn} · lus seul·e : {c}/{n}", cc=t["contrast_correct"],
                      cn=t["contrast_n"], c=t["correct"], n=t["n"])
        elif t.get("mode") == "slowed":
            test = tr("En prenant son temps : {cc}/{cn} · en répondant vite : {c}/{n}", cc=t["contrast_correct"],
                      cn=t["contrast_n"], c=t["correct"], n=t["n"])
        elif t.get("contrast_skill"):
            test = tr("{skill} : {c}/{n}", skill=short_label(t["contrast_skill"]), c=t["contrast_correct"],
                      n=t["contrast_n"]) + f" · {target}"
        else:
            test = target
        rows.append((tr("Test de l'agent"), test))
    return {"rows": rows, "tip": CLASSROOM_TIPS.get(err)}


def _livret(lid: int) -> list[dict]:
    """Notes du livret scolaire regroupées par année : une ligne par matière, une colonne par trimestre."""
    years: dict = {}
    for r in db.report_cards(lid):
        y = years.setdefault(r["school_year"], {"school_year": r["school_year"], "level": r["level"],
                                                "school": r["school"], "subjects": {}})
        y["subjects"].setdefault(r["subject"], {})[r["term"]] = r
    return list(years.values())


def _hypotheses_in_test(lid: int) -> list[dict]:
    rows = db.rows("SELECT thread_id, skill, hypothesis, status FROM exercises WHERE origin = 'targeted' "
                   "AND target_learner_id = ? AND status IN ('pending', 'approved') AND COALESCE(probe, 'target') = 'target' "
                   "GROUP BY thread_id", (lid,))
    for r in rows:
        r["state"] = (tr("exercices ciblés en attente de votre validation") if r["status"] == "pending"
                      else tr("en attente des réponses de l'élève aux exercices ciblés"))
    return rows


def _frise(lid: int, findings: list[dict]) -> list[dict]:
    """Une ligne par année du CI au CM2 : école, enseignant, et pour chaque trimestre réussite, présence,
    observations et constats qui s'appuient dessus."""
    acc: dict = {}
    for s in db.term_skill_stats(lid):
        n, c = acc.get((s["school_year"], s["term"]), (0, 0))
        acc[(s["school_year"], s["term"])] = (n + s["n"], c + s["accuracy"] * s["n"])
    presence = {(a["school_year"], a["term"]): a["days_present"] / a["days_total"] for a in db.attendance(lid)}
    notes: dict = {}
    for o in db.observations(lid):
        notes.setdefault((o["school_year"], o["term"]), []).append(f"{o['author']} : {o['text']}")
    marks: dict = {}
    for f in findings:
        if f["status"] == "active":
            ev = f["evidence"] or {}
            for t in ev.get("low_terms") or ev.get("high_terms") or ([f["since"]] if f.get("since") else []):
                marks.setdefault(t, set()).add(f["kind"])
    years, previous = [], None
    for y in db.schooling(lid):
        terms = []
        for t in (1, 2, 3):
            k = (y["school_year"], t)
            rate = acc[k][1] / acc[k][0] if k in acc else None
            terms.append({"rate": rate, "presence": presence.get(k), "notes": notes.get(k, []),
                          "marks": sorted(marks.get(f"{y['school_year']} T{t}", set())),
                          "tone": "none" if rate is None else "good" if rate >= .75 else "mid" if rate >= .5 else "low"})
        years.append({**y, "terms": terms, "new_school": y["school"] != previous})
        previous = y["school"]
    return years


def _trend(values: list[float]) -> tuple[str, str] | None:
    """Évolution d'une compétence : moyenne des 3 derniers trimestres comparée aux 3 d'avant.
    Pas de comparaison d'un trimestre à l'autre : avec peu d'exercices, ces écarts sont du hasard."""
    if len(values) < 4:
        return None
    recent, before = values[-3:], values[-6:-3]
    diff = sum(recent) / len(recent) - sum(before) / len(before)
    if diff >= 15:
        return ("up", tr("↑ en progrès"))
    if diff <= -15:
        return ("down", tr("↓ en baisse"))
    return ("flat", tr("→ stable"))


def _runs(data: list) -> list:
    """Les morceaux de courbe où la réussite baisse ou monte nettement : on lisse sur 3 trimestres (moyenne
    glissante) pour ignorer les zigzags dus au hasard, et on ne garde que les montées ou descentes d'au moins
    15 points. Renvoie, pour chaque point, la direction du segment qui part de ce point (down, up ou None)."""
    idx = [i for i, v in enumerate(data) if v is not None]
    vals = [data[i] for i in idx]
    smooth = [sum(vals[max(0, k - 1):k + 2]) / len(vals[max(0, k - 1):k + 2]) for k in range(len(vals))]
    out: list = [None] * len(data)
    k = 0
    while k < len(vals) - 1:
        sign = (smooth[k + 1] > smooth[k]) - (smooth[k + 1] < smooth[k])
        end = k + 1
        while end < len(vals) - 1 and sign and ((smooth[end + 1] > smooth[end]) - (smooth[end + 1] < smooth[end])) == sign:
            end += 1
        if sign and abs(smooth[end] - smooth[k]) >= 15:
            for j in range(k, end):
                out[idx[j]] = "up" if sign > 0 else "down"
        k = end
    return out



def _minis(lid: int) -> dict:
    """Un petit graphique par compétence, par matière, avec son évolution récente."""
    out: dict = {}
    for subject, chart in _charts(lid).items():
        out[subject] = []
        for ds in chart["datasets"]:
            values = [v for v in ds["data"] if v is not None]
            if not values:
                continue
            out[subject].append({"label": ds["label"], "last": values[-1], "trend": _trend(values),
                                 "chart": {"labels": chart["labels"],
                                           "datasets": [{"data": ds["data"], "borderColor": "#A8A29E",
                                                         "fill": False, "segments": _runs(ds["data"])}]}})
    return out


def _charts(lid: int) -> dict:
    """Réussite par compétence et par trimestre, une courbe par compétence, pour chaque matière."""
    stats = db.term_skill_stats(lid)
    term_label = lambda s: tr("{year}, trimestre {term}", year=s["school_year"], term=s["term"])
    labels = sorted({term_label(s) for s in stats})
    out = {}
    for subject in ("maths", "francais"):
        datasets = []
        for i, skill in enumerate(k for k, v in SKILLS.items() if v["subject"] == subject):
            values = {term_label(s): round(s["accuracy"] * 100)
                      for s in stats if s["skill"] == skill and s["n"] >= MIN_ANSWERS_PER_TERM}
            datasets.append({"label": short_label(skill), "skill": skill, "data": [values.get(x) for x in labels],
                             "borderColor": SKILL_COLORS[i % len(SKILL_COLORS)],
                             "backgroundColor": SKILL_COLORS[i % len(SKILL_COLORS)]})
        out[subject] = {"labels": labels, "datasets": datasets}
    return out


@bp.post("/eleves/<int:lid>/analyser")
def analyse(lid: int):
    return _job(tr("Analyse de {name}", name=g.names[lid]), lambda p: agent.run("term_review", learner_id=lid)["outcome"])


@bp.post("/eleves/<int:lid>/resume-famille")
def guardian_summary(lid: int):
    return _job(tr("Résumé pour la famille de {name}", name=g.names[lid]),
                lambda p: agent.run("guardian_summary", learner_id=lid)["outcome"])


@bp.post("/eleves/<int:lid>/observation")
def add_observation(lid: int):
    if text := request.form.get("text", "").strip():
        decisions.add_observation(lid, g.teacher["name"], text)
        flash(tr("Observation ajoutée : l'agent pourra la citer."))
    return redirect(url_for(".profile", lid=lid, vue="observations"))


@bp.post("/constats/<int:fid>/valider")
def validate(fid: int):
    decisions.validate_finding(fid, g.teacher["name"])
    return redirect(request.referrer or url_for(".dashboard"))


@bp.post("/constats/<int:fid>/contester")
def contest(fid: int):
    reason = request.form.get("reason", "").strip()
    f = db.row("SELECT learner_id FROM findings WHERE id = ?", (fid,))
    if reason and f:
        decisions.contest_finding(fid, g.teacher["name"], reason)
        decisions.add_observation(f["learner_id"], g.teacher["name"], reason, source=tr("constat {id} contesté", id=fid))
    return redirect(request.referrer or url_for(".dashboard"))


# -- Documents ---------------------------------------------------------------------------------

@bp.get("/documents")
def documents():
    return render_template("teacher/documents.html", docs=db.rows("SELECT * FROM documents ORDER BY id DESC"),
                           samples=sorted(p.name for p in SAMPLES_DIR.glob("*")))


@bp.post("/documents")
def upload():
    file = request.files.get("document")
    if not file or not file.filename:
        flash(tr("Choisissez un fichier."), "warn")
        return redirect(url_for(".documents"))
    name = f"{int(time.time())}_{file.filename.replace('/', '_')}"
    file.save(UPLOAD_DIR / name)
    kind = "livret" if request.form.get("kind") == "livret" else "registre"
    document = {"document_id": decisions.register_document(name, g.teacher["name"], g.cls["id"]),
                "filename": name, "class_id": g.cls["id"], "kind": kind}
    label = "Lecture du livret « {name} »" if kind == "livret" else "Lecture du registre « {name} »"
    see_alerts = tr(" Voir les alertes.")
    return _job(tr(label, name=file.filename),
                lambda p: agent.run("document", document=document)["outcome"] + see_alerts)


@bp.get("/documents/exemples/<name>")
def sample(name: str):
    return send_from_directory(SAMPLES_DIR, name, as_attachment=True)


# -- Raisonnement de l'agent et audit ---------------------------------------------------------

@bp.get("/agent")
def runs():
    return render_template("teacher/runs.html", runs=agent.runs(limit=60))


@bp.get("/audit")
def audit_log():
    filters = {k: request.args.get(k, "") for k in ("actor", "server", "status")}
    entries = [e for e in audit.entries(limit=800) if all(not v or e[k] == v for k, v in filters.items())]
    selected = next((e for e in entries if str(e["id"]) == request.args.get("id")), None)
    all_entries = audit.entries(limit=800)
    options = {k: sorted({e[k] for e in all_entries if e[k]}) for k in filters}
    return render_template("teacher/audit.html", entries=entries[:300], filters=filters, options=options,
                           selected=selected)
