"""Raisonnement de l'agent : règles explicites, appel au modèle local et auto-vérification.

Les règles produisent toujours une décision ; le modèle peut en proposer une autre, qui n'est
retenue que si elle passe l'auto-vérification (cohérence avec les calculs et les règles).

Pour une nouvelle hypothèse, le choix se fait parmi des « pistes » : une difficulté candidate (calculée)
et une explication possible (catalogue fermé, voir knowledge.EXPLANATIONS). Les règles ne regardent que
les chiffres ; le modèle croise les chiffres de toutes les compétences ET les observations écrites des
enseignants, qu'il doit citer. Ce qu'il cite est vérifié.
"""
from __future__ import annotations

import json
import re

from .. import llm
from ..config import FAST_RATE, MAX_TARGETED_ROUNDS
from ..i18n import pick, tr
from ..knowledge import (AGENT_RULES, CONTRAST, ERROR_TAXONOMY, EXPLANATIONS, SKILLS, explanations_for,
                         find_forbidden_label)
from .state import State, of_skill, pct, skill_label

ACTIONS = {"propose_exercises", "record_finding", "rule_out", "ask_teacher", "nothing"}
READ_ALOUD_EFFECT = 0.2  # écart de réussite (avec / sans lecture à voix haute) qui oriente les règles vers « lecture »
LEARNER_SOURCES = {"auto-évaluation élève", "intérêts (élève)"}
NUMBER_WORDS = pick({"deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9},
                    {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9})
# Ce qui suit un nombre de trimestres dans un constat (« 3 trimestres », « 3 consecutive terms »).
TERMS_PATTERN = pick(r"\s+trimestres", r"\s+(?:consecutive\s+|weak\s+|low\s+|school\s+)?terms")
# Mots qui rattachent une observation écrite à une compétence (vérification par le code, sans modèle).
SKILL_KEYWORDS = pick({
    "probleme_multi_etapes": ["problème"], "probleme_simple": ["problème"],
    "calcul": ["calcul", "addition", "soustraction", "multiplication", "doigts", "opération"],
    "numeration": ["nombre", "chiffre"],
    "decodage": ["lecture", "lire", "déchiffr", "lettre", "b et d"], "comprehension": ["compren", "histoire"],
    "grammaire": ["orthograph", "accord", "conjug", "grammaire"],
}, {
    "probleme_multi_etapes": ["problem"], "probleme_simple": ["problem"],
    "calcul": ["calculat", "arithmetic", "addition", "subtraction", "multiplication", "finger", "operation", "sums"],
    "numeration": ["number", "digit", "numeral"],
    "decodage": ["reading", "read ", "reads ", "decod", "letter", "b and d"], "comprehension": ["understand", "story",
                                                                                          "stories", "comprehension"],
    "grammaire": ["spelling", "spell", "agreement", "conjugat", "grammar"],
})


def mentions(text: str, skill: str) -> bool:
    return any(k in text.lower() for k in SKILL_KEYWORDS.get(skill, []))


# ---------------------------------------------------------------------------
# Faits calculés
# ---------------------------------------------------------------------------

def difficulty_candidates(state: State) -> list[dict]:
    """Compétences avec une tendance durable, pas encore suivies ni en cours de test, de la plus à la moins grave."""
    tl, trends = state["timeline"], state["trends"]["skills"]
    followed = {f["skill"] for f in tl["findings"]
                if f["kind"] == "difficulty" and f["status"] in ("active", "ruled_out", "contested")}
    in_test = {e["skill"] for e in tl["pending_targeted_exercises"]}
    focus = (state.get("plan") or {}).get("focus", "tout")  # matière choisie dans le plan
    out = []
    for skill, r in trends.items():
        if not r["pattern"] or r["dominant_error"] not in ERROR_TAXONOMY or skill in followed | in_test:
            continue
        if focus in ("maths", "francais") and SKILLS[skill]["subject"] != focus:
            continue
        gap = (r["mean_class_acc_low_terms"] or 0) - (r["mean_acc_low_terms"] or 0)
        out.append({"skill": skill, "error_type": r["dominant_error"],
                    "severity": round(r["consecutive_low_terms"] + r["low_terms_last6"] + gap, 2),
                    **{k: r[k] for k in ("consecutive_low_terms", "low_terms", "low_terms_last6", "mean_acc_low_terms",
                                         "mean_class_acc_low_terms", "dominant_error_share", "read_aloud_effect",
                                         "fast_rate_last6", "retry_success_last6", "explained_by_absence")}})
    return sorted(out, key=lambda c: -c["severity"])


def teacher_observations(timeline: dict) -> list[dict]:
    """Observations écrites par des enseignants. Ce que l'élève dit de lui-même n'est pas une preuve."""
    return [o for o in timeline["observations"] if o["source"] not in LEARNER_SOURCES]


def hypothesis_options(state: State) -> list[dict]:
    """Pistes à départager : pour les difficultés candidates, chaque explication possible et le test qui la vérifie."""
    out = []
    for c in difficulty_candidates(state)[:3]:
        for exp in explanations_for(c["skill"], c["fast_rate_last6"], FAST_RATE):
            test = (tr("mêmes exercices, texte lu à l'élève") if exp == "lecture"
                    else tr("mêmes exercices, en invitant l'élève à prendre son temps") if exp == "rythme"
                    else tr("contraste en {skill}", skill=skill_label(CONTRAST[c['skill']][0])) if c["skill"] in CONTRAST
                    else tr("exercices ciblés seuls"))
            out.append({"id": f"{c['skill']}:{exp}", "skill": c["skill"], "explanation": exp,
                        "error_type": c["error_type"], "sens": EXPLANATIONS[exp], "test": test, "faits": c})
    return out


def rules_option(options: list[dict]) -> dict:
    """Choix des règles : la difficulté la plus grave ; « rythme » ou « lecture » seulement si les chiffres le
    montrent (réponses trop rapides, effet de la lecture à voix haute). Les règles ne lisent pas les observations."""
    first, facts = options[0]["skill"], options[0]["faits"]
    wanted = ("rythme" if facts["fast_rate_last6"] >= FAST_RATE
              else "lecture" if (facts["read_aloud_effect"] or 0) >= READ_ALOUD_EFFECT else "locale")
    return next((o for o in options if o["skill"] == first and o["explanation"] == wanted), options[0])


def skills_overview(state: State) -> dict:
    """Dernier taux de réussite et tendance de chaque compétence, pour que le modèle relie les compétences entre elles."""
    out = {}
    for skill, r in state["trends"]["skills"].items():
        usable = [x for x in r["series"] if x["n"] >= 3]
        out[skill] = {"dernier_taux": usable[-1]["acc"] if usable else None, "tendance_faible_durable": r["pattern"],
                      "effet_lecture_voix_haute": r["read_aloud_effect"], "reponses_trop_rapides": r["fast_rate_last6"],
                      "reussite_au_2e_essai": r["retry_success_last6"]}
    return out


def evaluate_targeted(state: State) -> dict | None:
    """Verdict sur l'hypothèse en cours, d'après les exercices ciblés (cibles) et le test par contraste.

    confirmed   : cibles échouées avec l'erreur attendue, contraste réussi (difficulté bien localisée) ;
    broader     : cibles ET contraste échoués (la difficulté est peut-être ailleurs : on demande à l'enseignant) ;
    ruled_out   : cibles réussies ;
    inconclusive: entre les deux.
    """
    h = state.get("hypothesis")
    if not h:
        return None
    results = [r for r in state["timeline"]["targeted_results"] if r["exercise_id"] in set(h["exercise_ids"])]
    target = [r for r in results if r.get("probe") in (None, "target")]
    contrast = [r for r in results if r.get("probe") in ("contrast", "listened", "slowed")]  # voisine, écouté, en prenant son temps
    if not target:
        return None
    accuracy = sum(r["correct"] for r in target) / len(target)
    wrong = [r for r in target if not r["correct"]]
    same = [r for r in wrong if r["error_type"] == h["error_type"]]
    contrast_acc = sum(r["correct"] for r in contrast) / len(contrast) if contrast else None
    if accuracy <= 0.5 and len(same) >= max(1, len(wrong) / 2):
        verdict = "broader" if contrast_acc is not None and contrast_acc < 0.5 else "confirmed"
    elif accuracy >= 0.75:
        verdict = "ruled_out"
    else:
        verdict = "inconclusive"
    return {"n": len(target), "correct": sum(r["correct"] for r in target), "accuracy": round(accuracy, 2),
            "same_error": len(same), "verdict": verdict,
            "contrast_skill": contrast[0]["skill"] if contrast else None, "contrast_n": len(contrast),
            "mode": contrast[0]["probe"] if contrast else None,
            "contrast_correct": sum(r["correct"] for r in contrast),
            "contrast_accuracy": None if contrast_acc is None else round(contrast_acc, 2),
            "answer_ids": [r["id"] for r in results]}


# ---------------------------------------------------------------------------
# Décision par les règles
# ---------------------------------------------------------------------------

def rules_decision(state: State) -> dict:
    h = state.get("hypothesis")
    if h:
        return _decide_on_hypothesis(state, h)
    options = hypothesis_options(state)
    if options:
        o = rules_option(options)
        c = o["faits"]
        span = (tr("{n} trimestres faibles consécutifs", n=c['consecutive_low_terms']) if c["consecutive_low_terms"] >= 2
                else tr("{n} trimestres faibles sur les 6 derniers", n=c['low_terms_last6']))
        return {"action": "propose_exercises", "option": o["id"], "skill": o["skill"], "error_type": o["error_type"],
                "explanation": o["explanation"], "observations": related_observations(state["timeline"], o["skill"]),
                "hypothesis": hypothesis_text(state, c, o["explanation"]),
                "rationale": tr("{span} en {skill}, erreur dominante « {error} » ({share} des erreurs). Piste : {sens} "
                                "(test : {test}). Une hypothèse, pas un constat : je la teste.",
                                span=span, skill=skill_label(c['skill']), error=ERROR_TAXONOMY[c['error_type']],
                                share=pct(c['dominant_error_share']), sens=o['sens'], test=o['test'])}
    in_test = [e["skill"] for e in state["timeline"]["pending_targeted_exercises"]]
    if in_test:
        return {"action": "nothing", "rationale": tr("Hypothèse déjà en cours de test ({skill}) : j'attends la validation "
                                                     "de l'enseignant ou les réponses de l'élève.",
                                                     skill=skill_label(in_test[0]))}
    return {"action": "nothing", "rationale": tr("Aucune difficulté durable non expliquée et non déjà suivie.")}


def _decide_on_hypothesis(state: State, h: dict) -> dict:
    ev = evaluate_targeted(state)
    if ev is None:
        return {"action": "nothing", "rationale": tr("Les exercices ciblés n'ont pas encore été réalisés.")}
    base = {"skill": h["skill"], "error_type": h["error_type"], "explanation": h.get("explanation", "locale")}
    if ev["verdict"] == "confirmed":
        return base | {"action": "record_finding",
                       "rationale": tr("Exercices ciblés : {acc} de réussite, {same} erreur(s) du type attendu. "
                                       "L'hypothèse est confirmée.", acc=pct(ev['accuracy']), same=ev['same_error'])}
    if ev["verdict"] == "broader" and (switch := next_explanation(state, h)):
        # Le contraste n'a pas localisé la difficulté : plutôt que de rendre la main tout de suite, l'agent
        # choisit lui-même le test suivant (une autre explication), tant qu'il lui reste un tour.
        tried = h.get("tried") or [h.get("explanation", "locale")]
        base_text = h.get("base_text") or h["text"]
        return base | {"action": "propose_exercises", "explanation": switch, "switch": True,
                       "hypothesis": tr("{base} Nouvelle piste testée : {exp}.", base=base_text, exp=EXPLANATIONS[switch]),
                       "rationale": tr("Le contraste a échoué aussi ({c}/{n}) : la piste « {old} » ne suffit pas. Avant de "
                                       "vous solliciter, je teste une autre explication : {new}.",
                                       c=ev['contrast_correct'], n=ev['contrast_n'], old=EXPLANATIONS[tried[-1]],
                                       new=EXPLANATIONS[switch])}
    if ev["verdict"] == "broader":
        name = state["timeline"]["learner"]["first_name"]
        tried = h.get("tried") or [h.get("explanation", "locale")]
        before = ("" if len(tried) < 2 else
                  tr("J'ai testé plusieurs explications ({tried}) : aucune ne localise la difficulté. ",
                     tried=tr(", puis ").join(EXPLANATIONS[t] for t in tried)))
        counts = dict(name=name, of=of_skill(h['skill']), correct=ev['correct'], n=ev['n'],
                      c=ev['contrast_correct'], cn=ev['contrast_n'])
        if ev["mode"] == "listened":
            question = tr("{name} échoue aux exercices {of} lus seul ({correct}/{n}) et aussi quand le texte est lu à voix "
                          "haute ({c}/{cn}) : la difficulté ne vient donc pas seulement de la lecture du texte. Je "
                          "n'enregistre rien. Qu'observez-vous en classe ?", **counts)
        elif ev["mode"] == "slowed":
            question = tr("{name} échoue aux exercices {of} ({correct}/{n}) et aussi quand on l'invite à prendre son temps "
                          "({c}/{cn}) : la difficulté ne vient donc pas seulement du rythme. Je n'enregistre rien. "
                          "Qu'observez-vous en classe ?", **counts)
        else:
            why = CONTRAST.get(h["skill"], (None, tr("la difficulté semble plus large que prévu")))[1]
            question = tr("{name} échoue aux exercices ciblés ({correct}/{n}) mais aussi aux exercices de contraste en "
                          "{skill} ({c}/{cn}) : {why}. Je n'enregistre rien. Qu'observez-vous en classe ?",
                          skill=skill_label(ev['contrast_skill']), why=why, **counts)
        return base | {"action": "ask_teacher", "question": before + question,
                       "rationale": tr("Le test par contraste ne localise pas la difficulté et je n'ai plus d'autre piste "
                                       "à tester : je demande à l'enseignant au lieu de conclure.")}
    if ev["verdict"] == "ruled_out":
        return base | {"action": "rule_out",
                       "rationale": tr("Exercices ciblés réussis à {acc} : l'hypothèse est écartée.",
                                       acc=pct(ev['accuracy']))}
    if state.get("rounds", 0) < MAX_TARGETED_ROUNDS:
        return base | {"action": "propose_exercises", "hypothesis": h["text"],
                       "rationale": tr("Résultat ambigu ({acc}) : nouveau tour d'exercices.", acc=pct(ev['accuracy']))}
    return {"action": "ask_teacher", "skill": h["skill"],
            "question": tr("Après {rounds} tours d'exercices ciblés, les résultats restent ambigus ({acc} de réussite). "
                           "Qu'observez-vous en classe ?", rounds=state.get('rounds', 0), acc=pct(ev['accuracy'])),
            "rationale": tr("Résultats ambigus après le nombre maximal de tours : je rends la main à l'enseignant.")}


# Quand un test échoue, l'explication à essayer ensuite (dans l'ordre), si elle s'applique à la compétence.
NEXT_EXPLANATION = {"locale": ["lecture", "rythme"], "lecture": ["rythme", "locale"], "rythme": ["lecture", "locale"]}


def next_explanation(state: State, h: dict) -> str | None:
    """Explication pas encore testée et plausible pour cette compétence, s'il reste un tour d'exercices ciblés."""
    if state.get("rounds", 0) >= MAX_TARGETED_ROUNDS:
        return None
    tried = h.get("tried") or [h.get("explanation", "locale")]
    fast = (state["trends"]["skills"].get(h["skill"]) or {}).get("fast_rate_last6") or 0
    plausible = explanations_for(h["skill"], fast, FAST_RATE / 2)
    return next((e for e in NEXT_EXPLANATION[tried[-1]] if e in plausible and e not in tried), None)


# ---------------------------------------------------------------------------
# Décision par le modèle local
# ---------------------------------------------------------------------------

def llm_decision(state: State, tools_catalog: str) -> dict | None:
    tl = state["timeline"]
    facts = {
        "eleve": tl["learner"],
        "declencheur": state["trigger"],
        "pistes": [{k: o[k] for k in ("id", "sens", "test", "faits")} for o in hypothesis_options(state)],
        "competences": skills_overview(state),
        "hypothese_en_cours": state.get("hypothesis"),
        "resultats_exercices_cibles": evaluate_targeted(state),
        "tours_exercices_cibles": state.get("rounds", 0),
        "constats_existants": [{k: f[k] for k in ("kind", "skill", "statement", "status")} for f in tl["findings"]],
        "observations_enseignants": [{"id": o["id"], "annee": o["school_year"], "trimestre": o["term"], "texte": o["text"]}
                                     for o in teacher_observations(tl)[-12:]],
        "baisses_generalisees": state["trends"]["global_dips"],
    }
    system = pick(
        "Tu es XamKids Profile, un agent qui aide les enseignants à repérer tôt les difficultés durables "
        "d'apprentissage d'un élève. Règles :\n" + AGENT_RULES +
        "\nOutils disponibles (via MCP) :\n" + tools_catalog +
        "\n\nChoisis UNE prochaine action parmi : propose_exercises (tester une hypothèse), record_finding "
        "(seulement si des exercices ciblés réalisés confirment l'hypothèse), rule_out (si les exercices ciblés "
        "réussissent), ask_teacher (données contradictoires ou ambiguës), nothing.\n"
        "Pour une NOUVELLE hypothèse, choisis la piste la plus probable parmi « pistes » comme le ferait une "
        "conseillère pédagogique : ne prends pas forcément la compétence la plus faible ; relie les compétences entre "
        "elles (« competences ») et lis ce que les enseignants ont écrit. Une difficulté dans une compétence peut "
        "avoir sa cause dans une autre. "
        "Cite les identifiants des observations qui soutiennent ta piste.\n"
        'Réponds en JSON : {"action": ..., "piste": id d\'une piste (si nouvelle hypothèse), "observations_citees": '
        '[ids], "hypothesis": phrase courte et observable, "statement": constat factuel chiffré (si record_finding), '
        '"question": (si ask_teacher), "rationale": ton raisonnement en 2 phrases}. Écris en français simple.',
        "You are XamKids Profile, an agent that helps teachers spot a learner's lasting learning difficulties early. "
        "Rules:\n" + AGENT_RULES +
        "\nAvailable tools (via MCP):\n" + tools_catalog +
        "\n\nChoose ONE next action among: propose_exercises (test a hypothesis), record_finding "
        "(only if completed check exercises confirm the hypothesis), rule_out (if the check exercises are "
        "passed), ask_teacher (contradictory or ambiguous data), nothing.\n"
        "For a NEW hypothesis, choose the most likely explanation among \"pistes\" as a pedagogical advisor would: "
        "do not necessarily take the weakest skill; link the skills together (\"competences\") and read what the "
        "teachers wrote. A difficulty in one skill can have its cause in another. "
        "Cite the ids of the observations that support your choice.\n"
        'Answer in JSON: {"action": ..., "piste": id of a piste (if new hypothesis), "observations_citees": '
        '[ids], "hypothesis": short, observable sentence, "statement": factual finding with figures (if record_finding), '
        '"question": (if ask_teacher), "rationale": your reasoning in 2 sentences}. Write in plain English.'
    )
    return llm.chat_json(system, json.dumps(facts, ensure_ascii=False, default=str))


def verify_decision(state: State, d: dict) -> list[str]:
    """Auto-vérification : liste des incohérences entre une décision et les calculs ou les règles."""
    action = d.get("action")
    if action not in ACTIONS:
        return [tr("action inconnue « {action} »", action=action)]
    problems = [tr("terme interdit « {label} » dans {field}", label=label, field=field)
                for field in ("hypothesis", "statement", "question", "rationale")
                if (label := find_forbidden_label(d.get(field) or ""))]
    h, ev = state.get("hypothesis"), evaluate_targeted(state)
    candidates = difficulty_candidates(state)
    if action == "propose_exercises" and not h:
        if d.get("option") not in {o["id"] for o in hypothesis_options(state)}:
            problems.append(tr("piste « {option} » inconnue : aucune tendance durable calculée ne la justifie",
                               option=d.get('option')))
        known = {o["id"] for o in teacher_observations(state["timeline"])}
        if unknown := [i for i in d.get("observations") or [] if i not in known]:
            problems.append(tr("observations citées introuvables : {ids}", ids=unknown))
        if not d.get("observations") and d.get("option") != rules_decision(state).get("option"):
            problems.append(tr("le modèle s'écarte du choix des règles sans citer d'observation qui le justifie"))
    expected = ({"confirmed": "record_finding", "ruled_out": "rule_out"}.get(ev["verdict"])
                or (rules_decision(state)["action"] if ev["verdict"] == "broader" else None)) if ev else None
    if expected and action != expected:
        problems.append(tr("les exercices ciblés sont nets ({acc} de réussite, {same} erreur(s) du type attendu) : la "
                           "décision doit être « {expected} », pas « {action} »", acc=pct(ev['accuracy']),
                           same=ev['same_error'], expected=expected, action=action))
    if action == "record_finding" and not (ev and ev["verdict"] == "confirmed"):
        problems.append(tr("constat sans confirmation par des exercices ciblés réalisés"))
    if action == "rule_out" and not (ev and ev["verdict"] == "ruled_out"):
        problems.append(tr("hypothèse écartée sans résultats ciblés suffisants"))
    if action == "nothing" and not h and candidates:
        problems.append(tr("une tendance durable a été calculée mais ignorée"))
    if d.get("statement") and d.get("skill") in state["trends"]["skills"]:
        problems += _check_claimed_terms(state, d)
    return problems


def _check_claimed_terms(state: State, d: dict) -> list[str]:
    text = d["statement"]
    claimed = [int(n) for n in re.findall(rf"(\d+){TERMS_PATTERN}", text)]
    claimed += [v for w, v in NUMBER_WORDS.items() if re.search(rf"\b{w}{TERMS_PATTERN}", text)]
    r = state["trends"]["skills"][d["skill"]]
    real = max(r["consecutive_low_terms"], r["low_terms_last6"])
    return ([tr("le constat annonce {claimed} trimestres, les calculs en trouvent {real}", claimed=max(claimed), real=real)]
            if any(n > real for n in claimed) else [])


def decide(state: State, tools_catalog: str) -> tuple[dict, str, str]:
    """Décision finale : (décision, titre de l'étape, détail). Appel bloquant (modèle local)."""
    rules = rules_decision(state)
    nothing_to_weigh = not state.get("hypothesis") and not hypothesis_options(state)
    if state["mode"] != "llm" or nothing_to_weigh:  # sans piste à départager, le modèle n'a rien à décider
        problems = verify_decision(state, rules)
        detail = rules["rationale"] + (tr(" Problèmes : {problems}", problems='; '.join(problems)) if problems
                                       else tr(" Vérification : cohérent avec les calculs."))
        return rules | {"source": "règles"}, tr("Raisonnement (règles) et auto-vérification"), detail
    d = _normalize(state, llm_decision(state, tools_catalog))
    if d is None:
        return (rules | {"source": "règles"}, tr("Raisonnement"),
                tr("Sortie du modèle invalide : décision par les règles. ") + rules["rationale"])
    problems = verify_decision(state, d)
    if problems:
        return (rules | {"source": "règles"}, tr("Auto-vérification : décision du modèle rejetée"),
                "; ".join(problems) + tr(". Décision retenue : {action} — {rationale}", action=rules['action'],
                                         rationale=rules['rationale']))
    if d["action"] == "propose_exercises" and rules.get("switch"):
        # Changement de piste : l'explication et le texte viennent du calcul, pas du texte libre du modèle.
        d.update(explanation=rules["explanation"], hypothesis=rules["hypothesis"], switch=True)
    elif d["action"] == "propose_exercises" and not state.get("hypothesis"):
        # Hypothèse chiffrée calculée pour la piste choisie, enrichie de la lecture du modèle.
        o = next(o for o in hypothesis_options(state) if o["id"] == d["option"])
        d["hypothesis"] = (hypothesis_text(state, o["faits"], o["explanation"])
                           + (" " + tr("Lecture du modèle :") + f" {d['hypothesis']}" if d.get("hypothesis") else ""))
    else:
        d.setdefault("hypothesis", rules.get("hypothesis"))
    detail = d.get("rationale", "")
    if d.get("option") and d.get("option") != rules.get("option"):
        detail += tr(" (Les règles, qui ne lisent que les chiffres, auraient choisi la piste « {option} ».)",
                     option=rules.get('option'))
    return d | {"source": "modèle"}, tr("Raisonnement (modèle local) et auto-vérification réussie"), detail


def _normalize(state: State, d: dict | None) -> dict | None:
    """Complète la sortie du modèle : compétence, erreur et explication viennent de la piste (ou de l'hypothèse
    en cours), jamais du texte libre du modèle."""
    if not isinstance(d, dict):
        return None
    d = dict(d)
    d["observations"] = [int(i) for i in d.pop("observations_citees", None) or [] if str(i).isdigit()]
    h = state.get("hypothesis")
    if h:
        d.update(skill=h["skill"], error_type=h["error_type"], explanation=h.get("explanation", "locale"))
    elif d.get("action") == "propose_exercises":
        d["option"] = d.pop("piste", None)
        o = next((o for o in hypothesis_options(state) if o["id"] == d["option"]), None)
        if o:
            d.update(skill=o["skill"], error_type=o["error_type"], explanation=o["explanation"])
    return d


# ---------------------------------------------------------------------------
# Formulations
# ---------------------------------------------------------------------------

def hypothesis_text(state: State, c: dict, explanation: str = "locale") -> str:
    name = state["timeline"]["learner"]["first_name"]
    terms = c["low_terms"] or []
    span = (tr("sur {n} trimestres consécutifs ({first} → {last})", n=len(terms), first=terms[0], last=terms[-1])
            if len(terms) >= 2 else tr("sur {n} des 6 derniers trimestres", n=c['low_terms_last6']))
    # « ; erreur la plus fréquente : » et « Lecture du modèle : » servent de repères à l'interface (web/__init__.py).
    text = (tr("{name} réussit {acc} des exercices {of} {span} ", name=name, acc=pct(c['mean_acc_low_terms']),
               of=of_skill(c['skill']), span=span)
            + tr("; erreur la plus fréquente :") + f" {ERROR_TAXONOMY[c['error_type']].lower()}.")
    if explanation == "rythme":
        text += tr(" Piste testée : {fast} des réponses sont données en moins de 5 secondes ; la difficulté viendrait "
                   "d'un rythme trop rapide. On compare les mêmes exercices avec et sans invitation à prendre son temps.",
                   fast=pct(c.get('fast_rate_last6')))
    if explanation == "lecture":
        effect = c.get("read_aloud_effect")
        text += (tr(" Piste testée : la difficulté viendrait de la lecture du texte écrit")
                 + (tr(" (avec la lecture à voix haute, {pts:+d} points de réussite)", pts=round(effect * 100))
                    if effect else "")
                 + tr(" ; on compare les mêmes exercices lus seul et écoutés."))
    return text


def finding_statement(state: State, h: dict, ev: dict) -> str:
    """Constat chiffré, sans comparaison avec la classe, avec le résultat du test par contraste."""
    name = state["timeline"]["learner"]["first_name"]
    r = state["trends"]["skills"][h["skill"]]
    span = (tr("depuis {n} trimestres consécutifs", n=r['consecutive_low_terms']) if r["consecutive_low_terms"] >= 2
            else tr("sur {n} des 6 derniers trimestres", n=r['low_terms_last6']))
    counts = dict(name=name, of=of_skill(h['skill']), skill=skill_label(h['skill']), correct=ev['correct'], n=ev['n'],
                  c=ev['contrast_correct'], cn=ev['contrast_n'])
    if ev.get("mode") == "slowed":
        lead = tr("{name} réussit les exercices {of} quand on l'invite à prendre son temps ({c}/{cn}) mais échoue en "
                  "répondant vite ({correct}/{n}) : la difficulté vient plutôt du rythme que de la compétence elle-même",
                  **counts)
    elif ev.get("mode") == "listened":
        lead = tr("{name} réussit les exercices {of} quand le texte lui est lu ({c}/{cn}) mais échoue quand il le lit "
                  "seul ({correct}/{n}) : la difficulté vient plutôt de la lecture du texte que de la compétence "
                  "elle-même", **counts)
    elif ev.get("contrast_skill"):
        lead = tr("{name} réussit les exercices {contrast_of} ({c}/{cn}) mais échoue en {skill} ({correct}/{n} aux "
                  "exercices ciblés)", contrast_of=of_skill(ev['contrast_skill']), **counts)
    else:
        lead = tr("{name} échoue en {skill} ({correct}/{n} aux exercices ciblés)", **counts)
    return tr("{lead}, une difficulté présente {span} ({acc} de réussite sur cette période). Erreur la plus "
              "fréquente : {error}.", lead=lead, span=span, acc=pct(r['mean_acc_low_terms']),
              error=ERROR_TAXONOMY[h['error_type']].lower())


def since_term(r: dict) -> str | None:
    """Premier trimestre de la période observée (faible ou forte)."""
    terms = r.get("low_terms") or r.get("high_terms") or []
    return terms[0] if terms else None


def strength_statement(first_name: str, skill: str, r: dict) -> str:
    return tr("{name} réussit {acc} des exercices {of} depuis {n} trimestres ({first} → {last}).",
              name=first_name, acc=pct(r['mean_acc_high_terms']), of=of_skill(skill), n=r['consecutive_high_terms'],
              first=r['high_terms'][0], last=r['high_terms'][-1])


def guardian_summary_template(name: str, strengths: list[dict], difficulties: list[dict], trends: dict) -> str:
    """Résumé pour la famille sans modèle (ou si le texte du modèle est refusé)."""
    parts = [tr("Bonjour, voici quelques nouvelles du travail de {name} ce trimestre.", name=name)]
    if strengths:
        parts.append(tr("Ce qui marche bien : ") + " ".join(f["statement"] for f in strengths))
    else:
        best = max(trends, key=lambda k: trends[k]["series"][-1]["acc"] if trends[k]["series"] else 0)
        parts.append(tr("Ce qui marche bien : {name} réussit bien en {skill}.", name=name, skill=skill_label(best)))
    if difficulties:
        parts.append(tr("Ce qui est encore difficile : {name} a besoin de plus d'entraînement en {skills}. En classe, "
                        "nous lui proposons des exercices adaptés et nous suivons ses progrès.",
                        name=name, skills=", ".join(skill_label(f["skill"]) for f in difficulties)))
        parts.append(tr("À la maison, vous pouvez demander à {name} de vous expliquer à voix haute comment résoudre "
                        "un exercice : c'est un très bon entraînement.", name=name))
    else:
        parts.append(tr("{name} progresse régulièrement. Continuez à l'encourager !", name=name))
    parts.append(tr("N'hésitez pas à venir en parler avec l'enseignant·e."))
    return "\n\n".join(parts)


def related_observations(timeline: dict, skill: str) -> list[int]:
    """Observations d'enseignants liées à une compétence, par mots-clés (utilisé sans modèle)."""
    return [o["id"] for o in teacher_observations(timeline) if mentions(o["text"], skill)]
