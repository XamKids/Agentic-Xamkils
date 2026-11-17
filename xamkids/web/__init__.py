"""Interface web (Flask) : espace élève et espace enseignant."""
from __future__ import annotations

import hmac
import html
import os
import re
import secrets
import shutil
from pathlib import Path

from flask import Flask, redirect, render_template, request, session, url_for
from markupsafe import Markup

from ..config import AUDIT_DB, CURRENT_TERM, CURRENT_YEAR, DATA_DIR, RECORDS_DB
from ..i18n import LANG, tr
from ..knowledge import domain_label, short_label
from ..records import audit, db


def _split_hypothesis(text: str) -> dict:
    """Hypothèse de l'agent en trois morceaux lisibles : le constat, l'erreur la plus fréquente, l'avis du modèle."""
    text = (text or "").strip()
    for marker in dict.fromkeys(("Lecture du modèle :", tr("Lecture du modèle :"))):
        main, _, model = text.partition(marker)
        if model:
            break
    for marker in dict.fromkeys(("; erreur la plus fréquente :", tr("; erreur la plus fréquente :"))):
        main, _, error = main.partition(marker)
        if error:
            break
    clean = lambda s: s.strip().rstrip(".;").strip()
    return {"main": clean(main) + ".", "error": clean(error), "model": clean(model)}


def _start_followup_clock(every_seconds: int = 600) -> None:
    """Horloge de l'agent : toutes les 10 minutes, relance les vérifications arrivées à échéance
    (par exemple au début d'un nouveau trimestre), sans que personne n'ait à cliquer."""
    import threading
    import time

    def loop():
        from .. import agent
        while True:
            time.sleep(every_seconds)
            try:
                agent.run_due_followups()
            except Exception:  # l'horloge ne doit jamais faire tomber la plateforme
                pass
    threading.Thread(target=loop, daemon=True, name="xamkids-followups").start()


def _secret_key() -> str:
    path = DATA_DIR / "secret.key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


def _prompt_html(text: str) -> Markup:
    """Énoncé d'exercice : **titre** en gras, retours à la ligne conservés."""
    out = html.escape(text or "")
    out = re.sub(r"\*\*(.+?)\*\*", r"<span class='title'>\1</span>", out)
    out = re.sub(r"(</span>)\s*\n+", r"\1", out)  # le titre est déjà un bloc
    return Markup(out.replace("\n\n", "<br><br>").replace("\n", "<br>"))


_TERM = re.compile(r"\b(\d{4}-\d{4}) T([123])\b")
_TERM_SPELLED = r"\1, term \2" if LANG == "en" else r"\1, trimestre \2"


def _spell_terms(value):
    """Écrit les trimestres en toutes lettres dans tout ce qu'affichent les pages, y compris les textes de l'agent."""
    if isinstance(value, Markup):
        return Markup(_TERM.sub(_TERM_SPELLED, str(value)))
    if isinstance(value, str):
        return _TERM.sub(_TERM_SPELLED, value)
    return value


def plural(n, one: str, many: str, /, **fields) -> str:
    """Phrase au singulier ou au pluriel selon n (français : pluriel au-delà de 1 ; anglais : pluriel sauf pour 1),
    traduite, avec {n} et les autres {champs} remplacés."""
    many_ = n != 1 if LANG == "en" else n > 1
    return tr(many if many_ else one, n=n, **fields)


def _t(text: str, /, **fields) -> Markup:
    """Texte d'une page (Jinja : {{ _("...") }}) : le texte du gabarit est sûr, seules les valeurs sont échappées.
    Ainsi la page française reste identique à un texte écrit directement dans le gabarit."""
    out = Markup(tr(text))
    return out.format(**fields) if fields else out


def _tn(n, one: str, many: str, /, **fields) -> Markup:
    """Pluriel dans un gabarit : {{ _n(x, "{n} séance", "{n} séances") }}."""
    many_ = n != 1 if LANG == "en" else n > 1
    return _t(many if many_ else one, n=n, **fields)


def _bold_name(text: str, full_name: str) -> Markup:
    """Met en gras le nom (ou à défaut le prénom) de l'élève dans une phrase, le reste étant échappé."""
    text = text or ""
    for name in (full_name, (full_name or "").split(" ")[0]):
        if name and name in text:
            before, _, after = text.partition(name)
            return Markup(f"{html.escape(before)}<b>{html.escape(name)}</b>{html.escape(after)}")
    return Markup(html.escape(text))


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = _secret_key()
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
    if not RECORDS_DB.exists():
        # Mise en ligne : on repart des dossiers et du journal déjà constitués (classe fictive, historique, analyses, tests)
        snap = Path(__file__).resolve().parents[2] / "demo_data"
        if (snap / "xamkids.db").exists():
            RECORDS_DB.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(snap / "xamkids.db", RECORDS_DB)
            if (snap / "audit.db").exists() and not AUDIT_DB.exists():
                shutil.copy(snap / "audit.db", AUDIT_DB)
        else:
            from ..records import seed
            seed.seed()
    db.init()  # migrations éventuelles
    _start_followup_clock()

    from . import learner, teacher, voice
    app.register_blueprint(learner.bp)
    app.register_blueprint(teacher.bp)
    app.register_blueprint(voice.bp)
    from . import terminal
    terminal.register(app)

    app.jinja_env.finalize = _spell_terms  # « 2024-2025 T3 » → « 2024-2025, trimestre 3 » partout dans l'interface
    app.jinja_env.filters.update(
        pct=lambda x: "—" if x is None else f"{round(x * 100)}%" if LANG == "en" else f"{round(x * 100)} %",
        day=lambda iso: f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else "",
        domain=short_label,
        prompt=_prompt_html,
        hypothesis=_split_hypothesis,
        bold_name=_bold_name,
        initials=lambda l: ((l['first_name'] or ' ')[0] + (l['last_name'] or ' ')[0]).strip().upper(),
    )

    app.jinja_env.globals.update(_=_t, _n=_tn, tr=tr, LANG=LANG)

    @app.context_processor
    def globals_():
        return {"CURRENT_YEAR": CURRENT_YEAR, "CURRENT_TERM": CURRENT_TERM}

    @app.get("/")
    def landing():
        return redirect(url_for("teacher.dashboard"))

    # Mise en ligne : un code d'accès protège toute la plateforme (variable XAMKIDS_ACCESS_CODE).
    # Sans cette variable (installation dans une école, sur un poste local), rien ne change.
    access_code = os.environ.get("XAMKIDS_ACCESS_CODE", "")
    access_user = os.environ.get("XAMKIDS_ACCESS_USER", "xamkids").strip().lower()
    if access_code:
        @app.before_request
        def require_access():
            if session.get("access_ok") or request.endpoint in ("access", "static"):
                return None
            # Le terminal déployé à part lit le flux de l'agent avec un jeton de lecture.
            want = os.environ.get("XAMKIDS_TERMINAL_TOKEN", "")
            if want and request.endpoint == "terminal_feed" and hmac.compare_digest(
                    request.headers.get("X-Terminal-Token", "").encode(), want.encode()):
                return None
            return redirect(url_for("access"))

        @app.route("/acces", methods=["GET", "POST"])
        def access():
            wrong = False
            if request.method == "POST":
                who = request.form.get("user", "").strip().lower()
                ok_user = who == access_user or ("@" in who and who.split("@")[0] == access_user)
                ok_pass = hmac.compare_digest(request.form.get("code", "").strip().encode(), access_code.encode())
                if ok_user and ok_pass:
                    session["access_ok"] = True
                    # La connexion identifie l'enseignant : plus de page « Qui êtes-vous ? ».
                    me = next((t for t in db.teachers() if db.classes_for(t["id"])), None)
                    if me:
                        session["teacher_id"] = session["teacher_ok"] = me["id"]
                        audit.log(me["name"], "interface", "teacher_login")
                    return redirect(url_for("landing"))
                wrong = True
            return render_template("access.html", wrong=wrong), (401 if wrong else 200)

    return app
