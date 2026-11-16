"""État partagé du graphe et petits utilitaires de formulation."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from ..i18n import LANG
from ..knowledge import SKILLS
from ..records.audit import now


class State(TypedDict, total=False):
    thread_id: str
    trigger: str                 # session | targeted_session | document | term_review | guardian_summary
    learner_id: int | None
    session_id: int | None
    document: dict | None
    followup: dict | None        # vérification programmée par l'agent lui-même (déclencheur « followup »)
    mode: str                    # llm | rules
    plan: dict                   # objectif, étapes choisies, matière, justification (voir planning.py)
    done_steps: list[str]        # étapes du plan déjà faites
    timeline: dict
    analysis: dict
    trends: dict
    hypothesis: dict | None      # hypothèse en cours de test
    rounds: int                  # tours d'exercices ciblés déjà proposés
    decision: dict
    outcome: str
    steps: Annotated[list[dict], operator.add]   # trace lisible du raisonnement


def step(title: str, detail: str = "", **data) -> dict:
    """Ajoute une étape à la trace de raisonnement affichée à l'enseignant."""
    return {"steps": [{"ts": now(), "title": title, "detail": detail, "data": data or None}]}


def skill_label(skill: str) -> str:
    return SKILLS[skill]["label"].lower()


def of_skill(skill: str) -> str:
    """« de calcul », « d'orthographe grammaticale » : élision devant une voyelle (en anglais : « in calculation »)."""
    label = skill_label(skill)
    if LANG == "en":
        return f"in {label}"
    return f"d'{label}" if label[0] in "aeéèêiouh" else f"de {label}"


def pct(x: float | None) -> str:
    from ..i18n import LANG
    return "—" if x is None else (f"{round(x * 100)}%" if LANG == "en" else f"{round(x * 100)} %")
