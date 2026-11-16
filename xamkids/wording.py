"""Phrases destinées à l'enseignant : le modèle rédige, le code vérifie.

Pour chaque constat et chaque proposition d'exercices, l'agent donne au modèle local les faits calculés
(prénom, compétence, pourcentages, durée, erreur fréquente…). Le modèle rédige une phrase simple. Le code la
vérifie avant de l'enregistrer :
- chaque nombre de la phrase figure dans les faits (aucun chiffre inventé) ;
- aucune étiquette de diagnostic (dyslexie, TDAH…) et aucune comparaison avec la classe ;
- le prénom de l'élève est cité, la phrase reste courte.
Si la phrase ne passe pas, ou si le modèle est indisponible, on garde la phrase fixe construite par le code.
"""
from __future__ import annotations

import json
import re

from . import llm
from .i18n import LANG, pick, tr
from .knowledge import ERROR_SHORT, find_forbidden_label, short_label

# « en calcul », « dans les problèmes à étapes » : la compétence telle qu'on la dit dans une phrase.
SKILL_IN = pick(
    {"calcul": "en calcul", "numeration": "en numération", "probleme_simple": "dans les problèmes simples",
     "probleme_multi_etapes": "dans les problèmes à étapes", "decodage": "en lecture",
     "comprehension": "en compréhension de texte", "grammaire": "en orthographe"},
    {"calcul": "in arithmetic", "numeration": "in place value", "probleme_simple": "in one-step problems",
     "probleme_multi_etapes": "in multi-step problems", "decodage": "in reading",
     "comprehension": "in reading comprehension", "grammaire": "in grammar"})
# FR : « 3 exercices de calcul » ; EN : « 3 arithmetic exercises » (mot placé avant « exercises »).
SKILL_OF = pick(
    {"calcul": "de calcul", "numeration": "de numération", "probleme_simple": "de problèmes simples",
     "probleme_multi_etapes": "de problèmes à étapes", "decodage": "de lecture",
     "comprehension": "de compréhension de texte", "grammaire": "d'orthographe"},
    {"calcul": "arithmetic", "numeration": "place value", "probleme_simple": "one-step problem",
     "probleme_multi_etapes": "multi-step problem", "decodage": "reading",
     "comprehension": "reading comprehension", "grammaire": "grammar"})
KIND_TITLE = pick({"difficulty": "Difficulté", "strength": "Point fort", "watch": "À surveiller",
                   "ruled_out": "Écarté", "resolved": "Bonne nouvelle"},
                  {"difficulty": "Difficulty", "strength": "Strength", "watch": "To watch",
                   "ruled_out": "Ruled out", "resolved": "Good news"})
# Clés des faits donnés au modèle (dans la langue de la plateforme).
K = pick({k: k for k in ("prénom", "compétence", "en", "réussite", "erreur fréquente", "exercices proposés", "constat",
                         "preuve", "durée", "dernier trimestre", "d'habitude")},
         {"prénom": "first name", "compétence": "skill", "en": "in", "réussite": "success",
          "erreur fréquente": "frequent error", "exercices proposés": "proposed exercises", "constat": "finding",
          "preuve": "evidence", "durée": "duration", "dernier trimestre": "last term", "d'habitude": "usually"})

SENTENCE_PROMPT = (
    "Tu écris pour un enseignant d'école primaire au Sénégal. Écris UNE phrase simple et claire en français "
    "(25 mots maximum), avec tes propres mots, qui dit ce qu'on a observé chez l'élève. Cite le prénom et la "
    "compétence. Varie les tournures : ne commence pas toujours par le prénom, et n'emploie pas « car ». Si tu "
    "cites un chiffre, garde-le avec son unité exacte (« 97 % de réussite », « 15 trimestres ») ; n'ajoute aucun "
    "chiffre, aucune explication ni aucun conseil. N'utilise jamais « il » ou « elle » : répète le prénom si "
    "besoin. Aucun terme de diagnostic (dyslexie, TDAH, trouble…), aucune comparaison avec les camarades. "
    "Réponds en JSON : {\"text\": \"...\"}")
PROPOSAL_PROMPT = (
    "Tu es l'agent XamKids et tu t'adresses à un enseignant d'école primaire au Sénégal, à la première personne. "
    "Écris deux phrases simples en français, avec tes propres mots. « remarque » : ce que tu as observé chez "
    "l'élève ; commence par ce qui est le plus parlant pour l'enseignant (souvent l'erreur fréquente ou la "
    "compétence), pas par « a des difficultés », et cite le prénom et la compétence. « proposition » : quels "
    "exercices tu proposes, et que c'est pour vérifier ce que tu as observé. Varie les tournures. Si tu cites un "
    "chiffre, garde-le avec son unité exacte (« 33 % de réussite », « 15 trimestres ») ; n'ajoute aucun chiffre "
    "ni aucun autre but. N'utilise jamais « il » ou « elle » : répète le prénom si besoin. Aucun terme de "
    "diagnostic (dyslexie, TDAH, trouble…), aucune comparaison avec les camarades. Réponds en JSON : "
    "{\"remarque\": \"...\", \"proposition\": \"...\"}")
if LANG == "en":
    SENTENCE_PROMPT = (
        "You are writing for a primary school teacher in Senegal. Write ONE simple, clear sentence in English (25 words "
        "maximum), in your own words, saying what was observed in the learner's work. Mention the first name and the "
        "skill (as written in the facts). Vary the wording: do not always start with the first name, and do not use \"because\". If you quote "
        "a number, keep it with its exact unit (\"97% success\", \"for 15 terms\"); do not add any number, "
        "explanation or advice. Never use \"he\", \"she\", \"him\", \"her\" or \"his\": repeat the first name "
        "instead. No diagnostic term (dyslexia, ADHD, disorder…), no comparison with classmates. Do not address the "
        "learner. Answer in JSON: {\"text\": \"...\"}")
    PROPOSAL_PROMPT = (
        "You are the XamKids agent, speaking to a primary school teacher in Senegal, in the first person. "
        "Write two simple "
        "sentences in English, in your own words. \"remarque\": what you noticed in the learner's work; start with "
        "what is most telling for the teacher (often the frequent error or the skill), not with \"has difficulties\", "
        "and mention the first name and the skill, written exactly as in \"skill\". \"proposition\": which "
        "exercises you propose, and that they are to check what you noticed; start it with \"I propose\" or \"To "
        "check\". Vary the wording. If you quote a number, keep it with its exact unit (\"33% success\", \"over 3 "
        "terms\"); do not add any number or any other purpose (no practice, no help, no improvement, nothing to "
        "correct). Never use \"he\", \"she\", \"him\", \"her\" or "
        "\"his\": repeat the first name instead. No diagnostic term (dyslexia, ADHD, disorder…), no comparison with "
        "classmates. Answer in JSON: {\"remarque\": \"...\", \"proposition\": \"...\"}")


# -- Vérification ----------------------------------------------------------------------------

def _numbers(text: str) -> set[str]:
    return {n.lstrip("0") or "0" for n in re.findall(r"\d+", text or "")}


def check(text: str, facts: dict, first_name: str | None, max_len: int = 320, must: str | None = None) -> str | None:
    """Renvoie la raison du refus, ou None si la phrase est acceptable. `must` : mot qui doit figurer
    (le nom de la compétence, bien orthographié)."""
    text = (text or "").strip()
    if not text:
        return tr("phrase vide")
    if must and must.lower() not in text.lower():
        return tr("compétence absente ou mal écrite (« {must} » attendu)", must=must)
    if len(text) > max_len:
        return tr("phrase trop longue")
    if first_name and first_name.lower() not in text.lower():
        return tr("prénom absent")
    if label := find_forbidden_label(text):
        return tr("étiquette interdite (« {label} »)", label=label)
    if (re.search(r"\bclass|classmate|\bpeers?\b|other (?:children|pupils|learners)", text, re.I) if LANG == "en" else
            "classe" in text.lower() or "camarade" in text.lower()):
        return tr("comparaison avec la classe")
    if re.search(pick(r"\b(tu|te|ton|ta|tes)\b|\bt'", r"\b(you|your|yours|yourself)\b"), text, re.I):
        return tr("s'adresse à l'élève au lieu de l'enseignant")
    if re.search(pick(r"entraîn|pratiqu|amélior|travaill|\baider\b|corrig|\bdevra|appren|propose à|révis|renforc|"
                      r"soutien|soutenir|faudrait|suggère|j'offre|maîtris|\blui\b",
                      r"\btrain|practi[sc]|improv|\bwork on\b|\bhelp|\bcorrect(?!ly)|\bensure|\bshould\b|\bwill need\b|\bneeds? to\b|"
                      r"\blearn|revis|reinforc|support|\bought\b|suggest|\bI offer\b|\bmaster|\bboost|"
                      r"\bhim\b|\bher\b|\bhis\b"), text, re.I):
        return tr("change le but (vérifier, pas entraîner)")
    invented = _numbers(text) - _numbers(json.dumps(facts, ensure_ascii=False))
    if invented:
        return tr("chiffre absent des faits ({numbers})", numbers=", ".join(sorted(invented)))
    # Le modèle peut omettre un chiffre, mais chaque chiffre qu'il écrit garde son sens : « 15 trimestres » ne
    # devient pas « 15 points », « 3 des 6 derniers trimestres » ne devient pas « les 3 derniers trimestres ».
    allowed = {u for value in _phrases(facts) for u in re.findall(r"\d+ ?(?:%|[a-zéèêû]+)", _norm(value))}
    allowed |= {f"{x['nombre']} exercice" for x in facts.get("exercices proposés", []) if isinstance(x, dict)}
    if LANG == "en":  # l'adjectif précède le nom : « 3 arithmetic exercises » → « 3 exercises », « 3 consecutive
        # terms » → « 3 terms » ; mais « 3 of the last 6 terms » ne devient pas « 3 terms ».
        allowed |= {f"{n} {noun}" for value in _phrases(facts) for n, noun in
                    re.findall(r"(\d+) (?:(?!of\b|out\b)[a-z-]+ ){0,3}?(exercises?|terms?|days?)\b", _norm(value))}
    for unit in re.findall(r"\d+ ?(?:%|[a-zéèêû]+)", _norm(text)):
        if unit not in allowed and unit.rstrip("s") not in {a.rstrip("s") for a in allowed}:
            return tr("chiffre détourné de son sens (« {unit} »)", unit=unit)
    return None


def neutral(text: str, first_name: str) -> str:
    """Le modèle devine souvent « il » ou « elle » d'après le prénom : on remplace par le prénom."""
    if LANG == "en":
        return _neutral_en(text, first_name)
    text = re.sub(r"\b(?:il|elle|Il|Elle)\b", first_name, text or "")
    # élision : « que Aminata » → « qu'Aminata », « qu'Moussa » → « que Moussa »
    text = re.sub(r"\b([Qq]u)e ([AEIOUYÉÈÊH])", r"\1'\2", text)
    text = re.sub(r"\b([Qq]u)'([^AEIOUYÉÈÊHaeiouyéèêh\s])", r"\1e \2", text)
    text = text.strip()
    return text + "." if text and text[-1] not in ".!?" else text


# Après « her » : mots qui montrent un complément (« help her to », « ask her again ») et non un possessif.
_AFTER_OBJECT = ("to", "in", "on", "at", "with", "and", "or", "a", "an", "the", "again", "when", "if", "before", "after",
                 "for", "from", "by", "about", "more", "some", "time", "that", "this", "these", "those", "as", "so", "but",
                 "is", "was", "has", "had")


def _neutral_en(text: str, name: str) -> str:
    """« he / she / him / her / his » → le prénom (« his work » → « Awa's work »)."""
    text = re.sub(r"\b(?:him|her)sel(?:f|ves)\b", name, text or "", flags=re.I)
    text = re.sub(r"\b(?:his|hers)\b", f"{name}'s", text, flags=re.I)
    after = "|".join(_AFTER_OBJECT)
    text = re.sub(rf"\b(?:her)\b(?=\s*(?:[.,;:!?)]|$|(?:{after})\b))", name, text, flags=re.I)
    text = re.sub(r"\bher\b", f"{name}'s", text, flags=re.I)
    text = re.sub(r"\b(?:he|she|him)\b", name, text, flags=re.I)
    text = re.sub(rf"\b{re.escape(name)}'s's\b", f"{name}'s", text)
    text = text.strip()
    return text + "." if text and text[-1] not in ".!?" else text


def _phrases(facts: dict) -> list[str]:
    return [v for v in facts.values() if isinstance(v, str)]


def _norm(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).lower()
    return re.sub(r"(\d)\s*%", r"\1 %", text)  # « 33% » et « 33 % » sont la même expression


# -- Constats ------------------------------------------------------------------------------

def finding_facts(kind: str, skill: str, evidence: dict, status: str = "active") -> dict:
    """Les faits d'un constat, sous forme d'expressions toutes faites, donnés au modèle et vérifiés ensuite."""
    if LANG == "en":
        return _finding_facts_en(kind, skill, evidence, status)
    ev = evidence or {}
    where = SKILL_IN.get(skill, f"en {short_label(skill).lower()}")
    if status == "ruled_out":
        facts = {"constat": f"n'a finalement pas de difficulté {where}"}
        t = ev.get("targeted") or {}
        if t.get("n"):
            facts["preuve"] = f"{t['correct']} exercices de vérification réussis sur {t['n']}"
        return facts
    if status == "resolved":
        return {"constat": f"n'a plus de difficultés {where}", "preuve": "nets progrès sur les derniers trimestres"}
    if kind == "difficulty":
        facts = {"constat": f"a des difficultés {where}"}
        if ev.get("low_terms"):
            n = len(ev["low_terms"])
            facts["durée"] = f"depuis {n} trimestre{'s' if n > 1 else ''}"
        if ev.get("mean_acc_low_terms") is not None:
            facts["réussite"] = f"{round(ev['mean_acc_low_terms'] * 100)} % de réussite sur cette période"
        if ERROR_SHORT.get(ev.get("dominant_error")):
            facts["erreur fréquente"] = ERROR_SHORT[ev["dominant_error"]]
        return facts
    if kind == "strength":
        facts = {"constat": f"est très à l'aise {where}"}
        n = len(ev.get("high_terms") or [])
        if ev.get("rate") is not None:
            facts["preuve"] = f"{round(ev['rate'] * 100)} % de réussite" + (f" depuis {n} trimestres" if n > 1 else "")
        return facts
    if skill == "presence" and ev.get("latest_absences") is not None:
        return {"constat": "manque plus souvent l'école",
                "dernier trimestre": f"{ev['latest_absences']} jours d'absence au dernier trimestre",
                "d'habitude": f"{round(ev['previous_mean'] * 100)} % de présence d'habitude"}
    return {"constat": "est à surveiller"}


def _where(skill: str) -> str:
    return SKILL_IN.get(skill, f"in {short_label(skill).lower()}")


def _finding_facts_en(kind: str, skill: str, evidence: dict, status: str = "active") -> dict:
    ev, where = evidence or {}, _where(skill)
    if status == "ruled_out":
        facts = {K["constat"]: f"has no difficulty {where} after all"}
        t = ev.get("targeted") or {}
        if t.get("n"):
            facts[K["preuve"]] = f"passed {t['correct']} of {t['n']} check exercises"
        return facts
    if status == "resolved":
        return {K["constat"]: f"no longer has difficulties {where}", K["preuve"]: "clear progress over the last terms"}
    if kind == "difficulty":
        facts = {K["constat"]: f"has difficulties {where}"}
        if ev.get("low_terms"):
            n = len(ev["low_terms"])
            facts[K["durée"]] = f"for {n} term{'s' if n > 1 else ''}"
        if ev.get("mean_acc_low_terms") is not None:
            facts[K["réussite"]] = f"{round(ev['mean_acc_low_terms'] * 100)}% success over this period"
        if ERROR_SHORT.get(ev.get("dominant_error")):
            facts[K["erreur fréquente"]] = ERROR_SHORT[ev["dominant_error"]]
        return facts
    if kind == "strength":
        facts = {K["constat"]: f"is very confident {where}"}
        n = len(ev.get("high_terms") or [])
        if ev.get("rate") is not None:
            facts[K["preuve"]] = f"{round(ev['rate'] * 100)}% success" + (f" for {n} terms" if n > 1 else "")
        return facts
    if skill == "presence" and ev.get("latest_absences") is not None:
        return {K["constat"]: "is missing school more often",
                K["dernier trimestre"]: f"{ev['latest_absences']} days absent last term",
                K["d'habitude"]: f"{round(ev['previous_mean'] * 100)}% attendance usually"}
    return {K["constat"]: "needs watching"}


def _finding_template_en(kind: str, skill: str, evidence: dict, statement: str = "", status: str = "active") -> str:
    ev, where = evidence or {}, _where(skill)
    if status == "resolved" and kind == "difficulty":
        return f"no longer has difficulties {where} (clear progress over the last terms)."
    if status == "resolved" and skill == "presence":
        return "is attending class as usual again."
    if status == "ruled_out":
        return f"has no difficulty {where} after all (check exercises passed)."
    if kind == "difficulty":
        n = len(ev.get("low_terms") or [])
        err = ERROR_SHORT.get(ev.get("dominant_error"))
        head = f"has had difficulties {where} for {n} term{'s' if n > 1 else ''}" if n else f"has difficulties {where}"
        return head + (f" (frequent error: {err})." if err else ".")
    if kind == "strength":
        m = re.search(r"(\d+) ?%", statement or "")
        rate = round(ev["rate"] * 100) if ev.get("rate") is not None else (int(m.group(1)) if m else None)
        n = len(ev.get("high_terms") or [])
        proof = ", ".join(x for x in [f"{rate}% success" if rate is not None else "",
                                      f"for {n} terms" if n > 1 else ""] if x)
        return f"is very confident {where}" + (f" ({proof})." if proof else ".")
    if skill == "presence" and ev.get("latest_absences") is not None:
        return (f"is missing school more often ({ev['latest_absences']} days absent last term, "
                f"compared with {round(ev['previous_mean'] * 100)}% attendance usually).")
    head = re.split(r" ?: ", statement or "", maxsplit=1)[0]
    return (head[:1].lower() + head[1:]) + "."


def finding_template(kind: str, skill: str, evidence: dict, statement: str = "", status: str = "active") -> str:
    """Phrase fixe (sans le prénom, qui la précède) : utilisée si le modèle est indisponible ou refusé."""
    if LANG == "en":
        return _finding_template_en(kind, skill, evidence, statement, status)
    ev = evidence or {}
    where = SKILL_IN.get(skill, f"en {short_label(skill).lower()}")
    if status == "resolved" and kind == "difficulty":
        return f"n'a plus de difficultés {where} (nets progrès sur les derniers trimestres)."
    if status == "resolved" and skill == "presence":
        return "est de nouveau présent·e en classe comme d'habitude."
    if status == "ruled_out":
        return f"n'a finalement pas de difficulté {where} (exercices de vérification réussis)."
    if kind == "difficulty":
        n = len(ev.get("low_terms") or [])
        since = f" depuis {n} trimestre{'s' if n > 1 else ''}" if n else ""
        err = ERROR_SHORT.get(ev.get("dominant_error"))
        return f"a des difficultés {where}{since}" + (f" (erreur fréquente : {err})." if err else ".")
    if kind == "strength":
        m = re.search(r"(\d+) %", statement or "")
        rate = round(ev["rate"] * 100) if ev.get("rate") is not None else (int(m.group(1)) if m else None)
        n = len(ev.get("high_terms") or [])
        proof = ", ".join(x for x in [f"{rate} % de réussite" if rate is not None else "",
                                      f"depuis {n} trimestres" if n > 1 else ""] if x)
        return f"est très à l'aise {where}" + (f" ({proof})." if proof else ".")
    if skill == "presence" and ev.get("latest_absences") is not None:
        return (f"manque plus souvent l'école ({ev['latest_absences']} jours d'absence au dernier trimestre, "
                f"contre {round(ev['previous_mean'] * 100)} % de présence d'habitude).")
    return (statement or "").split(" : ")[0].lower() + "."


def check_finding_sentence(text: str, first_name: str, kind: str, skill: str, evidence: dict,
                           status: str = "active") -> str | None:
    """Vérifie la phrase d'un constat par rapport aux faits du constat (utilisé par l'agent ET le serveur MCP)."""
    facts = {K["prénom"]: first_name, **finding_facts(kind, skill, evidence, status)}
    must = None if skill == "presence" else short_label(skill).lower().split(" ")[0].rstrip("s")
    return check(text, facts, first_name, must=must)


def finding_sentence(first_name: str, kind: str, skill: str, evidence: dict, statement: str = "",
                     status: str = "active", use_model: bool = True) -> dict:
    """Phrase d'un constat pour l'enseignant : {text, source, refused?}. Le modèle rédige, le code vérifie."""
    fallback = f"{first_name} {finding_template(kind, skill, evidence, statement, status)}"
    if not use_model:
        return {"text": fallback, "source": "règles"}
    facts = {K["prénom"]: first_name, **finding_facts(kind, skill, evidence, status)}
    out = llm.chat_json(SENTENCE_PROMPT, json.dumps(facts, ensure_ascii=False), timeout=60, temperature=0.6) or {}
    text = neutral((out.get("text") or "").strip(), first_name)
    reason = check_finding_sentence(text, first_name, kind, skill, evidence, status) if out else tr("modèle indisponible")
    if reason:
        return {"text": fallback, "source": "règles", "refused": reason}
    return {"text": text, "source": "modèle"}


# -- Propositions d'exercices ciblés --------------------------------------------------------

def proposal_facts(first_name: str, skill: str, hypothesis: str, groups: list[tuple[int, str]]) -> dict:
    """groups : [(nombre, rôle)] où rôle ∈ target | contrast:<compétence> | listened | slowed."""
    from .knowledge import ERROR_TAXONOMY
    if LANG == "en":
        return _proposal_facts_en(first_name, skill, hypothesis, groups, ERROR_TAXONOMY)
    text = hypothesis or ""
    m = re.search(r"(\d+) %", text)
    period = re.search(r"sur ([^;.]*?trimestres)", text)
    err = next((ERROR_SHORT[k] for k, v in ERROR_TAXONOMY.items() if v.lower() in text.lower() and k in ERROR_SHORT), None)
    facts: dict = {"prénom": first_name, "compétence": short_label(skill).lower(),
                   "en": SKILL_IN.get(skill, "en " + short_label(skill).lower())}
    if m:
        facts["réussite"] = f"{m.group(1)} % de réussite" + (f" sur {period.group(1)}" if period else "")
    if err:
        facts["erreur fréquente"] = err
    parts = [_role_text(n, role, skill, first_name) for n, role in groups]
    facts["exercices proposés"] = ", ".join(parts[:-1]) + " et " + parts[-1] if len(parts) > 1 else (parts[0] if parts else "")
    return facts


def _proposal_facts_en(first_name: str, skill: str, hypothesis: str, groups: list[tuple[int, str]],
                       taxonomy: dict) -> dict:
    text = hypothesis or ""
    m = re.search(r"(\d+) ?%", text)
    period = re.search(r"\b(?:over|for) ([^;.]*?terms)", text)
    err = next((ERROR_SHORT[k] for k, v in taxonomy.items() if v.lower() in text.lower() and k in ERROR_SHORT), None)
    facts: dict = {K["prénom"]: first_name, K["compétence"]: short_label(skill).lower(), K["en"]: _where(skill)}
    if m:
        facts[K["réussite"]] = f"{m.group(1)}% success" + (f" over {period.group(1)}" if period else "")
    if err:
        facts[K["erreur fréquente"]] = err
    parts = [_role_text(n, role, skill, first_name) for n, role in groups]
    facts[K["exercices proposés"]] = (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1
                                     else (parts[0] if parts else ""))
    return facts


def _role_text_en(n: int, role: str, skill: str, first_name: str) -> str:
    ex = f"exercise{'s' if n > 1 else ''}"
    if role == "target":
        return " ".join(x for x in (str(n), SKILL_OF.get(skill, ""), ex) if x)
    if role.startswith("contrast:"):
        return " ".join(x for x in (str(n), SKILL_OF.get(role.split(':', 1)[1], ""), ex) if x) + " to compare"
    if role == "listened":
        return f"{n} {ex} read aloud, to see whether reading the text gets in {first_name}'s way"
    return f"{n} {ex} where {first_name} has to take time before answering"


def _role_text(n: int, role: str, skill: str, first_name: str) -> str:
    if LANG == "en":
        return _role_text_en(n, role, skill, first_name)
    ex = f"{n} exercice{'s' if n > 1 else ''}"
    if role == "target":
        return f"{ex} {SKILL_OF.get(skill, '')}".strip()
    if role.startswith("contrast:"):
        return f"{ex} {SKILL_OF.get(role.split(':', 1)[1], '')} pour comparer".strip()
    if role == "listened":
        return f"{ex} lu{'s' if n > 1 else ''} à voix haute, pour voir si la lecture du texte gêne {first_name}"
    return f"{ex} où {first_name} doit prendre son temps avant de répondre"


def proposal_template(facts: dict) -> dict:
    if LANG == "en":
        first, rate = facts[K["prénom"]], facts.get(K["réussite"], "")
        where = facts[K["en"]][0].upper() + facts[K["en"]][1:]
        err = facts.get(K["erreur fréquente"])
        noticed = f"{where}, {first} {err or 'still finds it hard'}" + (f" ({rate})." if rate else ".")
        return {"noticed": noticed, "proposal": f"To check this, I propose {facts[K['exercices proposés']]}."}
    first = facts["prénom"]
    where = facts["en"][0].upper() + facts["en"][1:]
    rate = facts.get("réussite", "")
    if facts.get("erreur fréquente"):
        noticed = f"{where}, {first} {facts['erreur fréquente']}" + (f" ({rate})." if rate else ".")
    else:
        noticed = f"{where}, {first} a encore du mal" + (f" ({rate})." if rate else ".")
    return {"noticed": noticed, "proposal": f"Pour le vérifier, je propose {facts['exercices proposés']}."}


def proposal_sentences(facts: dict, use_model: bool = True) -> dict:
    """Les deux phrases de la page « À valider » : {noticed, proposal, source, refused?}."""
    fallback = proposal_template(facts) | {"source": "règles"}
    if not use_model:
        return fallback
    out = llm.chat_json(PROPOSAL_PROMPT, json.dumps(facts, ensure_ascii=False), timeout=60, temperature=0.4) or {}
    first, offered = facts[K["prénom"]], K["exercices proposés"]
    noticed = neutral((out.get("remarque") or "").strip(), first)
    proposal = neutral((out.get("proposition") or "").strip(), first)
    if proposal and not re.match(pick(r"(je propose|pour (le )?vérifier)", r"(I propose|to (check|verify))"),
                                 proposal, re.I):
        out = out and {**out, "_bad_start": True}
    checks = re.search(r"check|verif", proposal, re.I) if LANG == "en" else "vérifi" in proposal.lower()
    reason = (tr("modèle indisponible") if not out else
              tr("la proposition doit commencer par « Je propose » ou « Pour vérifier »") if out.get("_bad_start") else
              tr("la proposition doit dire qu'il s'agit de vérifier") if not checks else
              check(noticed, {k: v for k, v in facts.items() if k != offered}, first,
                    must=facts[K["compétence"]].split(" ")[0].rstrip("s"))
              or check(proposal, {offered: facts[offered]}, None))
    if reason:
        return fallback | {"refused": reason}
    return {"noticed": noticed, "proposal": proposal, "source": "modèle"}
