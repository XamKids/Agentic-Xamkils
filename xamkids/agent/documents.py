"""Lecture des documents téléversés : registres CSV ou scans (Qwen2.5-VL), puis contrôle de cohérence."""
from __future__ import annotations

import csv
import io
import re
import unicodedata

from .. import llm
from ..config import VLM_MODEL
from ..i18n import tr

MIN_SHARPNESS = 800  # en dessous, l'image est jugée trop floue pour être lue de façon fiable
CSV_COLUMNS = "prenom, nom, jours_presents, jours_ouvres"
VISION_PROMPT = (
    "Tu lis un registre d'appel scolaire scanné. Recopie chaque ligne sans rien inventer. Si une valeur est "
    'illisible, mets null. JSON : {"readable": true/false, "rows": [{"first_name", "last_name", '
    '"days_present", "days_total"}]}'
)


def normalize(s: str) -> str:
    """Minuscules, sans accents : pour rapprocher les noms écrits à la main de la liste de classe."""
    return "".join(c for c in unicodedata.normalize("NFD", s.lower().strip()) if unicodedata.category(c) != "Mn")


def sharpness(img: bytes) -> float:
    """Netteté d'une image (variance des contours)."""
    from PIL import Image, ImageFilter, ImageStat
    im = Image.open(io.BytesIO(img)).convert("L")
    im.thumbnail((1200, 1200))
    return ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES)).var[0]


def parse_csv(text: str) -> tuple[list[dict], list[str]]:
    try:
        rows = [{"first_name": r.get("prenom", "").strip(), "last_name": r.get("nom", "").strip(),
                 "days_present": int(r["jours_presents"]), "days_total": int(r["jours_ouvres"])}
                for r in csv.DictReader(io.StringIO(text))]
        return rows, []
    except Exception as e:
        return [], [tr("Le fichier ne suit pas le format attendu ({columns}) : {error}.", columns=CSV_COLUMNS, error=e)]


def read_scan(img: bytes) -> tuple[list[dict], list[str]]:
    """Extraction d'un registre scanné par le modèle de vision local. Appel bloquant."""
    if sharpness(img) < MIN_SHARPNESS:
        return [], [tr("L'image est trop floue pour être lue de façon fiable.")]
    if not llm.status()["vlm"]:
        return [], [tr("Le modèle de vision ({model}) n'est pas installé : je ne peux pas lire l'image.", model=VLM_MODEL)]
    out = llm.chat_json(VISION_PROMPT, "Extrais le tableau de ce registre.", VLM_MODEL, [img])
    if not out or not out.get("readable", True) or not out.get("rows"):
        return [], [tr("Le modèle de vision n'a pas pu lire le tableau.")]
    rows, issues = [], []
    for r in out["rows"]:
        if None in (r.get("days_present"), r.get("days_total")):
            issues.append(tr("Valeur illisible pour {first} {last}.", first=r.get('first_name'), last=r.get('last_name')))
        else:
            rows.append({k: r[k] for k in ("first_name", "last_name", "days_present", "days_total")})
    return rows, issues


def match_roster(rows: list[dict], roster: list[dict]) -> tuple[list[dict], list[str]]:
    """Rapproche les lignes lues de la liste de classe ; signale ce qui ne colle pas au lieu de deviner."""
    index = {(normalize(r["first_name"]), normalize(r["last_name"])): r["id"] for r in roster}
    matched, issues = [], []
    for r in rows:
        name = f"{r['first_name']} {r['last_name']}"
        learner_id = index.get((normalize(r["first_name"]), normalize(r["last_name"])))
        if learner_id is None:
            issues.append(tr("« {name} » ne figure pas dans la classe : nouvel élève ou erreur de saisie ?", name=name))
        elif not 0 <= int(r["days_present"]) <= int(r["days_total"]):
            issues.append(tr("Valeurs incohérentes pour {name} : {present} présents sur {total} jours.", name=name,
                             present=r['days_present'], total=r['days_total']))
        else:
            matched.append({"learner_id": learner_id, "name": name,
                            "days_present": int(r["days_present"]), "days_total": int(r["days_total"])})
    return matched, issues


# ---------------------------------------------------------------------------
# Livret scolaire : il suit l'élève d'une classe à l'autre. À son arrivée, on le lit pour que son profil
# ne parte pas de zéro. Seuls les notes, les appréciations et l'identité sont repris : jamais le rang
# ni la moyenne de la classe (aucune comparaison avec les camarades).
# ---------------------------------------------------------------------------

LIVRET_COLUMNS = "prenom, nom, matricule, ecole, annee, niveau, trimestre, matiere, note, sur, appreciation"
LIVRET_PROMPT = (
    "Tu lis une page de livret scolaire d'école élémentaire sénégalaise (photo ou scan). Recopie sans rien inventer. "
    "Une ligne par matière et par trimestre. Si une valeur est illisible, mets null. N'extrais PAS le rang, ni la "
    "moyenne de la classe, ni aucune comparaison avec d'autres élèves. JSON : {\"readable\": true/false, "
    "\"first_name\", \"last_name\", \"matricule\", \"school\", \"entries\": [{\"school_year\" (ex. 2024-2025), "
    "\"level\" (CI, CP, CE1, CE2, CM1 ou CM2), \"term\" (1, 2 ou 3), \"subject\", \"score\", \"max_score\", "
    "\"appreciation\"}]}"
)
# Matières du livret → domaine suivi par XamKids (mots-clés sans accents, en minuscules).
DOMAIN_KEYWORDS = {
    "maths": ["math", "calcul", "numer", "geometr", "mesure", "probleme", "arithm"],
    "francais": ["francais", "langue", "communication", "lecture", "ecriture", "expression", "orthograph",
                 "grammaire", "conjugaison", "vocabulaire", "dictee", "redaction"],
}


def subject_domain(subject: str) -> str:
    s = normalize(subject or "")
    return next((d for d, words in DOMAIN_KEYWORDS.items() if any(w in s for w in words)), "autre")


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def parse_livret_csv(text: str) -> tuple[dict, list[str]]:
    """Livret recopié dans un tableur (une ligne par matière et par trimestre)."""
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
        first = rows[0]
        livret = {"first_name": first["prenom"].strip(), "last_name": first["nom"].strip(),
                  "matricule": (first.get("matricule") or "").strip(), "school": (first.get("ecole") or "").strip(),
                  "entries": [{"school_year": r["annee"].strip(), "level": r["niveau"].strip(), "term": r["trimestre"],
                               "subject": r["matiere"].strip(), "score": r["note"], "max_score": r["sur"],
                               "appreciation": (r.get("appreciation") or "").strip(),
                               "school": (r.get("ecole") or "").strip()} for r in rows]}
        return livret, []
    except Exception as e:
        return {}, [tr("Le livret ne suit pas le format attendu ({columns}) : {error}.", columns=LIVRET_COLUMNS, error=e)]


def read_livret_scan(img: bytes) -> tuple[dict, list[str]]:
    """Lecture d'une page de livret par le modèle de vision local. Appel bloquant."""
    if sharpness(img) < MIN_SHARPNESS:
        return {}, [tr("La photo du livret est trop floue pour être lue de façon fiable : merci d'en reprendre une.")]
    if not llm.status()["vlm"]:
        return {}, [tr("Le modèle de vision ({model}) n'est pas installé : je ne peux pas lire la photo. Vous pouvez "
                       "recopier le livret en CSV ({columns}).", model=VLM_MODEL, columns=LIVRET_COLUMNS)]
    out = llm.chat_json(LIVRET_PROMPT, "Extrais le contenu de ce livret scolaire.", VLM_MODEL, [img])
    if not out or not out.get("readable", True) or not out.get("entries"):
        return {}, [tr("Le modèle de vision n'a pas pu lire le livret.")]
    return out, []


def check_livret(livret: dict, current_year: str, levels: list[str]) -> tuple[list[dict], list[dict], list[str]]:
    """Contrôle de cohérence ligne par ligne. Renvoie les notes retenues, les appréciations et les problèmes.
    Une ligne douteuse n'est jamais corrigée en silence : elle est écartée et signalée."""
    grades, appreciations, issues = [], [], []
    seen: set = set()
    for e in livret.get("entries", []):
        year, level, subject = str(e.get("school_year") or "").strip(), str(e.get("level") or "").strip().upper(), \
            str(e.get("subject") or "").strip()
        where = f"{level or '?'} {year or '?'} T{e.get('term') or '?'} · {subject or '?'}"
        raw_score, raw_max = e.get("score"), e.get("max_score")
        if isinstance(raw_score, str) and "/" in raw_score:  # « 5,5/10 » recopié tel quel dans la case
            raw_score, written_max = raw_score.split("/", 1)
            if _num(raw_max) not in (None, _num(written_max)):
                issues.append(tr("Barème contradictoire ({where} : {score} sur {max}).", where=where, score=e.get('score'),
                                 max=raw_max))
                continue
            raw_max = written_max
        term, score, max_score = _num(e.get("term")), _num(raw_score), _num(raw_max)
        if not (len(year) == 9 and year[4] == "-" and year[:4].isdigit() and year[5:].isdigit()
                and int(year[5:]) == int(year[:4]) + 1):
            issues.append(tr("Année scolaire illisible ou mal écrite ({where}).", where=where))
            continue
        if year >= current_year:
            issues.append(tr("Le livret contient l'année en cours ou une année future ({where}) : ligne écartée.", where=where))
            continue
        if level not in levels:
            issues.append(tr("Niveau inconnu « {level} » ({where}).", level=level, where=where))
            continue
        if term not in (1, 2, 3):
            issues.append(tr("Trimestre illisible ({where}).", where=where))
            continue
        if not subject:
            issues.append(tr("Matière illisible ({where}).", where=where))
            continue
        if score is None or not max_score or not 0 <= score <= max_score:
            issues.append(tr("Note illisible ou incohérente ({where} : {score} sur {max}).", where=where,
                             score=e.get('score'), max=e.get('max_score')))
            continue
        key = (year, int(term), normalize(subject))
        if key in seen:
            issues.append(tr("Matière en double pour le même trimestre ({where}).", where=where))
            continue
        seen.add(key)
        grades.append({"school_year": year, "level": level, "term": int(term), "subject": subject,
                       "domain": subject_domain(subject), "score": score, "max_score": max_score,
                       "school": (e.get("school") or livret.get("school") or "").strip()})
        for t, text in split_by_term(str(e.get("appreciation") or ""), int(term)):
            a = {"school_year": year, "level": level, "term": t, "text": f"{subject} : {text}"}
            if a not in appreciations:
                appreciations.append(a)
    return grades, appreciations, issues


def split_by_term(text: str, default_term: int) -> list[tuple[int, str]]:
    """« T1 : … T2 : … » écrit dans une seule case du livret → une appréciation par trimestre."""
    parts = re.split(r"\bT([123])\s*:\s*", text.strip())
    if len(parts) < 3:
        return [(default_term, text.strip())] if text.strip() else []
    out = [(default_term, parts[0].strip())] if parts[0].strip() else []
    out += [(int(t), body.strip()) for t, body in zip(parts[1::2], parts[2::2]) if body.strip()]
    return out


def match_livret_learner(livret: dict, roster: list[dict]) -> tuple[int | None, list[str]]:
    """Retrouve l'élève du livret dans la classe : par matricule d'abord, sinon par prénom et nom.
    Un matricule qui désigne un autre élève que le nom est signalé, jamais tranché."""
    name = f"{livret.get('first_name', '')} {livret.get('last_name', '')}".strip()
    mat = (livret.get("matricule") or "").strip()
    by_name = next((r for r in roster if (normalize(r["first_name"]), normalize(r["last_name"]))
                    == (normalize(livret.get("first_name", "")), normalize(livret.get("last_name", "")))), None)
    by_mat = next((r for r in roster if mat and (r.get("matricule") or "") == mat), None)
    if by_mat and by_name and by_mat["id"] != by_name["id"]:
        return None, [tr("Le matricule {mat} correspond à {first} {last}, mais le livret est au nom de {name} : lequel "
                         "est le bon ?", mat=mat, first=by_mat['first_name'], last=by_mat['last_name'], name=name)]
    if by_name and not by_mat and mat and by_name.get("matricule") and by_name["matricule"] != mat:
        return None, [tr("{name} est dans la classe avec le matricule {known}, mais le livret indique {mat} : s'agit-il "
                         "du même élève ?", name=name, known=by_name['matricule'], mat=mat)]
    found = by_mat or by_name
    return (found["id"] if found else None), []
