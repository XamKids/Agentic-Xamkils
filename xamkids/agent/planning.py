"""Planification : avant d'agir, l'agent lit la situation de l'élève et écrit son plan.

Le modèle local choisit l'objectif, les étapes et la matière sur laquelle se concentrer ; le plan est
ensuite vérifié comme une décision : étapes inconnues retirées, prérequis ajoutés, étapes obligatoires
selon le déclencheur imposées, ordre rétabli. Chaque correction est expliquée à l'enseignant.
Sans modèle (ou si sa sortie est invalide), un plan par règles prend le relais.
"""
from __future__ import annotations

import json

from .. import llm
from ..i18n import pick, tr
from .state import State

# Étapes que l'agent peut planifier (nom du nœud → rôle), dans l'ordre où elles s'exécutent.
STEPS = pick({
    "analyze": "classer les erreurs des nouvelles réponses (outil analyze_answers)",
    "retrieve": "relire tout l'historique de l'élève depuis le CI (outil get_learner_timeline)",
    "trends": "obtenir les tendances exactes du serveur (outil compute_trends), vérifiées dans le bac à sable Run Python",
    "crosscheck": "relire les observations écrites des enseignants avec les chiffres et poser une question en cas de "
                  "contradiction (utile en revue de trimestre ou si une observation récente existe)",
    "monitor": "repérer les forces durables, les absences en hausse et les difficultés résolues (update_profile)",
    "reason": "former ou évaluer une hypothèse et décider de l'action (exercices ciblés, constat, question)",
    "summarize": "rédiger un résumé pour la famille à partir des constats validés (draft_guardian_summary)",
}, {
    "analyze": "classify the errors in the new answers (tool analyze_answers)",
    "retrieve": "reread the learner's whole history since CI (tool get_learner_timeline)",
    "trends": "get the exact trends from the server (tool compute_trends), checked in the Run Python sandbox",
    "crosscheck": "reread the teachers' written observations against the figures and ask a question if they "
                  "contradict each other (useful in a term review or if there is a recent observation)",
    "monitor": "spot lasting strengths, rising absences and resolved difficulties (update_profile)",
    "reason": "form or evaluate a hypothesis and decide on the action (check exercises, finding, question)",
    "summarize": "write a family summary from the validated findings (draft_guardian_summary)",
})
ORDER = list(STEPS)
PREREQUISITES = {"trends": ["retrieve"], "crosscheck": ["trends"], "monitor": ["trends"], "reason": ["trends"],
                 "summarize": ["trends"]}
REQUIRED = {  # étapes imposées selon le déclencheur
    "term_review": ["analyze", "crosscheck", "monitor", "reason"],
    "session": ["analyze", "reason"],
    "targeted_session": ["analyze", "reason"],
    "guardian_summary": ["summarize"],
    "followup": ["analyze", "monitor", "reason"],
}
FORBIDDEN = {  # un résumé n'est rédigé que si l'enseignant le demande ; il ne déclenche ni exercices ni constats
    "guardian_summary": ["reason", "crosscheck"],
    "term_review": ["summarize"], "session": ["summarize"], "targeted_session": ["summarize"], "followup": ["summarize"],
}
SHORT = pick({"analyze": "classer les erreurs", "retrieve": "relire l'historique", "trends": "calculer les tendances",
              "crosscheck": "croiser observations et chiffres",
              "monitor": "forces et suivi", "reason": "raisonner", "summarize": "résumé pour la famille"},
             {"analyze": "classify errors", "retrieve": "reread the history", "trends": "compute trends",
              "crosscheck": "cross-check observations and figures",
              "monitor": "strengths and follow-up", "reason": "reason", "summarize": "family summary"})
SUBJECTS = {"maths", "francais"}
FOCUS_LABEL = pick({}, {"maths": "maths", "francais": "French", "tout": "all subjects"})  # codes du plan, à l'affichage

PLAN_PROMPT = pick(
    "Tu es XamKids Profile, un agent qui suit un élève de primaire sur plusieurs années. Avant d'agir, écris ton plan.\n"
    "Étapes disponibles (choisis celles qui sont utiles, sans en inventer) :\n"
    + "\n".join(f"- {k} : {v}" for k, v in STEPS.items()) +
    "\nRègles : une revue de trimestre examine tout (focus « tout ») ; après une séance, concentre-toi sur ce que la séance "
    "a apporté ; « summarize » uniquement si le déclencheur est guardian_summary (jamais autrement : un résumé pour "
    "la famille n'est rédigé qu'à la demande de l'enseignant) ; si une hypothèse est en test et que l'élève vient de faire les exercices ciblés, ton objectif est de "
    "l'évaluer ; « monitor » coûte du temps et n'est utile qu'en revue de trimestre ou si la situation a changé.\n"
    'Réponds en JSON : {"objectif": une phrase, "etapes": [noms d\'étapes], "focus": "maths" | "francais" | "tout", '
    '"justification": deux phrases simples}.',
    "You are XamKids Profile, an agent that follows a primary-school learner over several years. Before acting, "
    "write your plan.\n"
    "Available steps (choose the useful ones, do not invent any):\n"
    + "\n".join(f"- {k}: {v}" for k, v in STEPS.items()) +
    "\nRules: a term review examines everything (focus \"tout\"); after a session, focus on what the session "
    "brought; \"summarize\" only if the trigger is guardian_summary (never otherwise: a family summary is only "
    "written when the teacher asks for it); if a hypothesis is being tested and the learner has just done the check "
    "exercises, your objective is to evaluate it; \"monitor\" takes time and is only useful in a term review or if "
    "the situation has changed.\n"
    'Answer in JSON: {"objectif": one sentence, "etapes": [step names], "focus": "maths" | "francais" | "tout", '
    '"justification": two simple sentences}. Write in English.'
)


def rules_plan(trigger: str, situation: dict) -> dict:
    """Plan par défaut, sans modèle."""
    last = situation.get("last_session") or {}
    subjects = set(last.get("subjects") or [])
    focus = subjects.pop() if trigger == "session" and len(subjects) == 1 else "tout"
    steps = {
        "term_review": ["analyze", "retrieve", "trends", "crosscheck", "monitor", "reason"],
        "session": ["analyze", "retrieve", "trends", "reason"],
        "targeted_session": ["analyze", "retrieve", "trends", "reason"],
        "guardian_summary": ["retrieve", "trends", "summarize"],
        "followup": ["analyze", "retrieve", "trends", "monitor", "reason"],
    }.get(trigger, ["analyze", "retrieve", "trends", "reason"])
    objective = {
        "term_review": "Faire le point complet de fin de trimestre.",
        "session": "Voir ce que la séance apporte au profil.",
        "targeted_session": "Évaluer l'hypothèse avec les réponses aux exercices ciblés.",
        "guardian_summary": "Préparer un résumé pour la famille à partir des constats validés.",
        "followup": "Vérifier si le constat suivi persiste, se résout ou s'aggrave.",
    }.get(trigger, "Analyser la situation de l'élève.")
    return {"objective": tr(objective), "steps": steps, "focus": focus, "why": tr("Plan par défaut pour ce déclencheur.")}


def llm_plan(trigger: str, situation: dict) -> dict | None:
    out = llm.chat_json(PLAN_PROMPT, json.dumps({"declencheur": trigger, "situation": situation},
                                                ensure_ascii=False, default=str))
    if not out or not isinstance(out.get("etapes"), list):
        return None
    return {"objective": str(out.get("objectif", "")), "steps": [str(s) for s in out["etapes"]],
            "focus": str(out.get("focus", "tout")), "why": str(out.get("justification", ""))}


def verify_plan(trigger: str, plan: dict) -> tuple[dict, list[str]]:
    """Corrige le plan pour qu'il respecte les dépendances et les règles ; renvoie les corrections faites."""
    fixes = []
    steps = []
    for s in plan["steps"]:
        if s not in STEPS:
            fixes.append(tr("étape inconnue « {s} » retirée", s=s))
        elif s in FORBIDDEN.get(trigger, []):
            fixes.append(tr("« {s} » retiré : interdit pour ce déclencheur", s=s))
        elif s not in steps:
            steps.append(s)
    for s in REQUIRED.get(trigger, []):
        if s not in steps:
            steps.append(s)
            fixes.append(tr("« {s} » ajouté : obligatoire pour ce déclencheur", s=s))
    changed = True
    while changed:  # prérequis (par exemple : pas de raisonnement sans tendances calculées)
        changed = False
        for s in list(steps):
            for p in PREREQUISITES.get(s, []):
                if p not in steps:
                    steps.append(p)
                    fixes.append(tr("« {p} » ajouté : nécessaire avant « {s} »", p=p, s=s))
                    changed = True
    ordered = [s for s in ORDER if s in steps]
    if ordered != steps:
        fixes.append(tr("ordre des étapes rétabli"))
    focus = plan.get("focus") if plan.get("focus") in SUBJECTS else "tout"
    if trigger == "term_review" and focus != "tout":
        fixes.append(tr("focus élargi à toutes les matières : une revue de trimestre examine tout"))
        focus = "tout"
    return {**plan, "steps": ordered, "focus": focus}, fixes


def make_plan(state: State, situation: dict, use_model: bool) -> tuple[dict, str, str]:
    """Plan final : (plan, titre de l'étape, détail lisible). Appel bloquant (modèle local)."""
    trigger = state["trigger"]
    plan = llm_plan(trigger, situation) if use_model else None
    source = tr("modèle local")
    if plan is None:
        plan, source = rules_plan(trigger, situation), tr("règles") + (tr(" (sortie du modèle invalide)") if use_model else "")
    plan, fixes = verify_plan(trigger, plan)
    plan["source"] = source
    labels = " → ".join(SHORT[s] for s in plan["steps"])
    detail = (tr("Objectif : {objective} Plan : {labels}. Matière : {focus}. Pourquoi : {why} Vérification du plan : ",
                  objective=plan['objective'], labels=labels, focus=FOCUS_LABEL.get(plan['focus'], plan['focus']),
                  why=plan['why'])
              + ("; ".join(fixes) + "." if fixes else tr("conforme.")))
    return plan, tr("Planification ({source})", source=source), detail
