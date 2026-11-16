"""Chemins, modèles et paramètres de XamKids Profile."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = ROOT / "uploads"
TOOLS_DIR = ROOT / ".tools"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# Dossier scolaire des élèves : accessible uniquement via le serveur MCP xamkids-profile
# (et l'interface enseignant pour les validations humaines).
RECORDS_DB = Path(os.environ.get("XAMKIDS_RECORDS_DB", DATA_DIR / "xamkids.db"))
# Journal d'audit : appels d'outils, calculs exécutés, validations.
AUDIT_DB = Path(os.environ.get("XAMKIDS_AUDIT_DB", DATA_DIR / "audit.db"))
# État LangGraph (checkpointer) et suivi des exécutions de l'agent.
AGENT_DB = Path(os.environ.get("XAMKIDS_AGENT_DB", DATA_DIR / "agent.db"))

# Modèles open-weights servis localement par Ollama.
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
LLM_MODEL = os.environ.get("XAMKIDS_LLM", "llama3.1:8b")
VLM_MODEL = os.environ.get("XAMKIDS_VLM", "qwen2.5vl:7b")
SCENE_MODEL = os.environ.get("XAMKIDS_SCENE_LLM", LLM_MODEL)   # modèle qui conçoit les scènes 3D
# Exercices ciblés : par défaut choisis dans la banque validée. Mettre à 1 pour les faire générer par le modèle
# (expérimental : un modèle 8B produit encore trop d'exercices faux ou mal ciblés).
LLM_EXERCISES = os.environ.get("XAMKIDS_LLM_EXERCISES", "0") == "1"

CURRENT_YEAR = "2026-2027"
CURRENT_TERM = 1
SCHOOL_YEARS = ["2021-2022", "2022-2023", "2023-2024", "2024-2025", "2025-2026", "2026-2027"]  # CI → CM2

# Seuils de raisonnement (modifiables par l'équipe pédagogique).
LOW_ACCURACY = 0.5          # en dessous : trimestre considéré « en difficulté »
STRONG_ACCURACY = 0.8       # au-dessus : point fort potentiel
MIN_TERMS_FOR_PATTERN = 2   # nb de trimestres consécutifs avant de suspecter une difficulté
MIN_ANSWERS_PER_TERM = 3    # en dessous, le trimestre n'est pas interprétable
FAST_SECONDS = 5            # réponse donnée en moins de 5 s : trop rapide pour avoir lu la consigne
FAST_RATE = 0.2             # part de réponses trop rapides qui fait envisager la piste « rythme »
MAX_TARGETED_ROUNDS = 2     # tours d'exercices ciblés avant de rendre la main à l'enseignant
LOW_ATTENDANCE = 0.75       # présence sous ce seuil : l'agent relativise le trimestre


def _tool(name: str, *local: Path) -> str | None:
    for p in local:
        if p.exists():
            return str(p)
    return shutil.which(name)


DENO = _tool("deno", TOOLS_DIR / "bin" / "deno")
NPX = _tool("npx", TOOLS_DIR / "node" / "bin" / "npx")
PYTHON = sys.executable


def tool_env() -> dict[str, str]:
    """Environnement des sous-processus MCP : on y ajoute deno/node locaux."""
    env = dict(os.environ)
    extra = [str(TOOLS_DIR / "bin"), str(TOOLS_DIR / "node" / "bin"), str(Path(PYTHON).parent)]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    return env

# Code unique pour tous (enseignants et élèves) sur la version en ligne ; absent en local : chaque élève garde son code.
DEMO_PIN = os.environ.get("XAMKIDS_DEMO_PIN", "")
TEACHER_PIN = DEMO_PIN or "0000"
