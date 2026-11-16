"""Croisement des observations écrites des enseignants avec les chiffres du même trimestre.

Une phrase d'enseignant peut contredire les données (« comprend tout ce qu'il lit » face à 30 % de réussite).
Juger si une phrase est positive ou négative est le travail du modèle ; vérifier qu'elle parle bien de la
compétence (mots-clés) et que le chiffre la contredit vraiment est le travail du code. Une contradiction n'est
signalée que si les deux concordent. L'agent ne tranche pas : il pose la question.
"""
from __future__ import annotations

import json

from .. import llm
from ..i18n import pick, tr
from ..config import LOW_ACCURACY, MIN_ANSWERS_PER_TERM
from ..knowledge import SKILLS
from .reasoning import mentions, teacher_observations
from .state import State, of_skill, pct

RECENT_TERMS = 3                 # observations des trois derniers trimestres
OK_ACCURACY = LOW_ACCURACY + 0.15  # « les chiffres sont bons » : nettement au-dessus du seuil de difficulté
KINDS = pick({"positive_mais_faible": "l'enseignant décrit une réussite, les chiffres sont faibles",
              "negative_mais_bon": "l'enseignant décrit une difficulté, les chiffres sont bons"},
             {"positive_mais_faible": "the teacher describes a success, the figures are low",
              "negative_mais_bon": "the teacher describes a difficulty, the figures are good"})

PROMPT = pick(
    "Tu compares ce qu'un enseignant a écrit sur un élève de primaire avec ses résultats chiffrés du MÊME trimestre. "
    "Pour chaque observation, dis si elle contredit nettement les chiffres d'une compétence : "
    + "; ".join(f"« {k} » ({v})" for k, v in KINDS.items()) +
    ". Ne signale que les contradictions nettes. Une observation sur le comportement, la présence, l'entraide ou "
    "une matière sans chiffres n'est pas une contradiction. Il est normal de n'en trouver aucune.\n"
    'Réponds en JSON : {"contradictions": [{"observation_id": ..., "competence": clé de « chiffres », '
    '"type": ' + " | ".join(f'"{k}"' for k in KINDS) + ', "explication": une phrase}]}',
    "You compare what a teacher wrote about a primary-school learner with the learner's figures for the SAME term "
    "(\"taux\" = success rate between 0 and 1, \"reponses\" = number of answers). Skill keys in \"chiffres\": "
    + "; ".join(f'"{k}" = {v["label"]}' for k, v in SKILLS.items()) + ". "
    "For each observation, say whether it clearly contradicts the figures of one skill: "
    + "; ".join(f'"{k}" ({v})' for k, v in KINDS.items()) +
    ". A difficulty means the teacher writes the learner struggles, makes mistakes or finds it hard; a success "
    "means the teacher writes the learner masters it or does it well. Only report clear contradictions. An "
    "observation about behaviour, attendance, helping others or a subject without figures is not a contradiction. "
    "It is normal to find none.\n"
    'Answer in JSON: {"contradictions": [{"observation_id": ..., "competence": key of "chiffres", '
    '"type": ' + " | ".join(f'"{k}"' for k in KINDS) + ', "explication": one sentence}]}'
)


def _term_label(o: dict) -> str:
    return f"{o['school_year']} T{o['term']}"


def recent_observations(state: State) -> list[dict]:
    """Observations d'enseignants des derniers trimestres, chacune avec les chiffres de son trimestre."""
    terms = [f"{t['school_year']} T{t['term']}" for t in state["timeline"]["terms"]][-RECENT_TERMS:]
    out = []
    for o in teacher_observations(state["timeline"]):
        if _term_label(o) not in terms:
            continue
        figures = {}
        for skill, r in state["trends"]["skills"].items():
            x = next((x for x in r["series"] if x["term"] == _term_label(o)), None)
            if x and x["n"] >= MIN_ANSWERS_PER_TERM:
                figures[skill] = {"taux": x["acc"], "reponses": x["n"]}
        out.append({"id": o["id"], "trimestre": _term_label(o), "texte": o["text"], "chiffres": figures})
    return out


def check(observations: list[dict], c: dict) -> str | None:
    """Vérifie une contradiction proposée par le modèle ; renvoie le problème, ou None si elle tient."""
    o = next((o for o in observations if o["id"] == c.get("observation_id")), None)
    if not o:
        return tr("observation {id} introuvable", id=c.get('observation_id'))
    if c.get("type") not in KINDS:
        return tr("type « {type} » inconnu", type=c.get('type'))
    if not mentions(o["texte"], c.get("competence") or ""):
        return tr("observation {id} : elle ne parle pas de « {skill} »", id=o['id'], skill=c.get('competence'))
    fig = o["chiffres"].get(c.get("competence"))
    if not fig:
        return tr("pas de chiffres en « {skill} » au {term}", skill=c.get('competence'), term=o['trimestre'])
    if c["type"] == "positive_mais_faible" and fig["taux"] >= LOW_ACCURACY:
        return tr("observation {id} : {acc} en {skill}, ce n'est pas faible", id=o['id'], acc=pct(fig['taux']),
                  skill=c['competence'])
    if c["type"] == "negative_mais_bon" and fig["taux"] < OK_ACCURACY:
        return tr("observation {id} : {acc} en {skill}, ce n'est pas nettement bon", id=o['id'], acc=pct(fig['taux']),
                  skill=c['competence'])
    return None


def question(name: str, o: dict, c: dict) -> str:
    fig = o["chiffres"][c["competence"]]
    return tr("Votre observation du {term} dit : « {quote} » Or, ce même trimestre, {name} réussit {acc} des exercices "
              "{of} ({n} réponses). Les deux ne vont pas ensemble : je n'en tire aucune conclusion. Pouvez-vous me dire "
              "ce que vous observez ?", term=o['trimestre'], quote=o['texte'], name=name, acc=pct(fig['taux']),
              of=of_skill(c['competence']), n=fig['reponses'])


def find(state: State) -> tuple[list[dict], list[str], int]:
    """(contradictions vérifiées, propositions du modèle rejetées, nombre d'observations lues). Appel bloquant."""
    observations = [o for o in recent_observations(state) if o["chiffres"]]
    if not observations:
        return [], [], 0
    out = llm.chat_json(PROMPT, json.dumps({"observations": observations}, ensure_ascii=False))
    proposed = (out or {}).get("contradictions") or []
    confirmed, rejected, seen = [], [], set()
    name = state["timeline"]["learner"]["first_name"]
    for c in proposed if isinstance(proposed, list) else []:
        if not isinstance(c, dict):
            continue
        try:
            c["observation_id"] = int(c.get("observation_id"))
        except (TypeError, ValueError):
            pass
        if problem := check(observations, c):
            rejected.append(problem)
        elif (c["observation_id"], c["competence"]) not in seen and c["competence"] in SKILLS:
            seen.add((c["observation_id"], c["competence"]))
            o = next(o for o in observations if o["id"] == c["observation_id"])
            confirmed.append({**c, "question": question(name, o, c),
                              "accuracy": o["chiffres"][c["competence"]]["taux"], "term": o["trimestre"]})
    return confirmed, rejected, len(observations)
