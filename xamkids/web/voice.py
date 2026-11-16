"""Guidage vocal de l'élève, dans la langue de la plateforme (français par défaut, anglais en option).

Lu automatiquement : accueil, consigne de chaque exercice, encouragements, fin de séance, et les énoncés
qui ne mesurent pas la lecture (calcul, numération). Les textes à lire (compréhension, problèmes, phrases)
restent lus seulement si l'élève appuie sur « Écouter » : ce choix est un signal observé par l'agent.

L'audio est produit sur la machine (voix système, sans connexion), mis en cache, et servi à la page
qui le joue automatiquement.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess

from flask import Blueprint, abort, request, send_from_directory, url_for

from ..config import DATA_DIR
from ..i18n import LANG, pick, tr

VOICE = os.environ.get("XAMKIDS_VOICE", pick("Flo (Français (France))", "Samantha"))
CACHE_DIR = DATA_DIR / "voice"

INSTRUCTIONS = {
    "probleme_simple": tr("Lis le problème, puis choisis la bonne réponse."),
    "probleme_multi_etapes": tr("Lis bien tout le problème, puis choisis la bonne réponse."),
    "comprehension": tr("Lis le texte, puis réponds à la question."),
    "grammaire": tr("Choisis le mot qui complète la phrase."),
}
LISTEN_TIP = tr(" Si tu veux, appuie sur Écouter pour l'entendre.")
# Mots dits à voix haute pour les opérations et la monnaie.
_SAY = pick({"plus": "plus", "minus": "moins", "times": "fois", "divided": "divisé par", "francs": "francs"},
            {"plus": "plus", "minus": "minus", "times": "times", "divided": "divided by", "francs": "CFA francs"})


def _spoken(text: str) -> str:
    """Adapte un énoncé écrit à la lecture orale (opérations, monnaie, mise en forme)."""
    text = re.sub(r"[\U0001F000-\U0001FFFF\u2600-\u27BF]", "", text)  # émojis
    text = text.replace("**", "").replace("= ?", "").replace("___", "…")
    text = re.sub(r"(\d)\s*\+\s*(\d)", rf"\1 {_SAY['plus']} \2", text)
    text = re.sub(r"(\d)\s*[-−]\s*(\d)", rf"\1 {_SAY['minus']} \2", text)
    text = re.sub(r"(\d)\s*[x×]\s*(\d)", rf"\1 {_SAY['times']} \2", text)
    if LANG == "en":
        text = re.sub(r"(\d)\s*÷\s*(\d)", rf"\1 {_SAY['divided']} \2", text)
        text = re.sub(r"(\d+)\s*FCFA\b", rf"\1 {_SAY['francs']}", text)
    return re.sub(r"(\d+) F\b", rf"\1 {_SAY['francs']}", text)


def instruction(e: dict) -> str:
    """Ce que la voix dit automatiquement à l'apparition d'un exercice."""
    skill = e["skill"]
    if skill in ("calcul", "numeration"):
        return _spoken(e["prompt"])
    if e.get("probe") == "listened":  # exercice écouté : le texte est lu à l'élève, il ne le lit pas
        return tr("Écoute bien. {text} Choisis la bonne réponse.",
                  text=_spoken(e.get("read_aloud_text") or e["prompt"]))
    if e.get("probe") == "slowed":
        return tr("Prends ton temps. Relis bien avant de répondre. ") + instruction(e | {"probe": None})
    if skill == "decodage":
        return tr("Écoute bien le mot : {word}. Choisis comment il s'écrit.", word=e.get("read_aloud_text") or "")
    return INSTRUCTIONS.get(skill, tr("Lis la consigne, puis choisis la bonne réponse.")) + LISTEN_TIP


def _synthesize(text: str) -> str | None:
    """Produit (ou retrouve en cache) le fichier audio ; renvoie son nom."""
    CACHE_DIR.mkdir(exist_ok=True)
    name = f"{hashlib.sha1(f'{VOICE}|{text}'.encode()).hexdigest()}.wav"
    path = CACHE_DIR / name
    if not path.exists():
        if shutil.which("say"):  # macOS
            cmd = ["say", "-v", VOICE, "-r", "165", "-o", str(path), "--data-format=LEI16@22050", text]
        elif shutil.which("espeak-ng"):  # Linux
            cmd = ["espeak-ng", "-v", pick("fr", "en"), "-s", "140", "-w", str(path), text]
        else:
            return None
        if subprocess.run(cmd, capture_output=True).returncode != 0:
            return None
    return name


def clip(text: str | None) -> str | None:
    """URL qui fait dire ce texte (l'audio est produit à la première demande, puis mis en cache)."""
    return url_for("voice.say", t=text[:1500]) if text else None


bp = Blueprint("voice", __name__)


@bp.get("/voix")
def say():
    name = _synthesize(_spoken(request.args.get("t", "")[:1500]))
    if not name:
        abort(404)
    return send_from_directory(CACHE_DIR, name, mimetype="audio/wav", max_age=86400)
