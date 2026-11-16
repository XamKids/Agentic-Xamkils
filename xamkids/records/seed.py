"""Données de démonstration : une classe de CM2 suivie depuis le CI (cinq années d'historique, deux écoles).

Tous les élèves et enseignants sont fictifs. Chaque profil illustre un cas que l'agent doit traiter :
- Awa : réussit les calculs mais échoue aux problèmes à plusieurs étapes depuis plusieurs trimestres ;
- Moussa : difficultés persistantes de lecture de mots, meilleure compréhension avec la lecture à voix haute ;
- Aminata : erreurs persistantes sur la valeur des chiffres et la retenue ;
- Ibrahima : un seul trimestre faible, expliqué par une longue absence (une mauvaise période, pas une tendance) ;
- Cheikh : réponses très rapides et fausses, quelle que soit la matière ;
- Fatou et Khady : points forts durables ;
- Ousmane : baisse récente en inférence, sur un seul trimestre (trop tôt pour conclure) ;
- Mariama : absences en hausse depuis le CM1 (à surveiller).

Deux observations contredisent volontairement les chiffres de leur trimestre (l'agent doit poser la question) :
Aminata « maîtrise bien les grands nombres » alors qu'elle échoue en numération ; Fatou « a du mal en calcul »
alors qu'elle y réussit très bien.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

from . import db
from ..config import CURRENT_TERM, CURRENT_YEAR, SCHOOL_YEARS, UPLOAD_DIR
from ..i18n import pick, tr
from ..knowledge import SKILLS

LEVEL_BY_YEAR = dict(zip(SCHOOL_YEARS, ["CI", "CP", "CE1", "CE2", "CM1", "CM2"]))
# Deux écoles fictives : la première n'accueille que le CI et le CP, les élèves rejoignent ensuite la seconde.
SCHOOLS = [(1, "École élémentaire Les Filaos", "Dakar, Grand-Yoff", "elementaire"),
           (2, "École élémentaire Les Flamboyants", "Dakar, Parcelles Assainies", "elementaire")]
SCHOOL_BY_LEVEL = {"CI": 1, "CP": 1, "CE1": 2, "CE2": 2, "CM1": 2, "CM2": 2}
TEACHERS = [(1, "Mme Fatou Kiné Ndiaye"), (2, "M. Abdou Sarr"), (3, "M. Ibrahima Faye"), (4, "Mme Rokhaya Ndiaye"),
            (5, "M. Cheikh Sarr"), (6, "Mme Aïssatou Diop")]
BASE_TIME = {"calcul": 25, "numeration": 15, "probleme_simple": 40, "probleme_multi_etapes": 70,
             "decodage": 12, "comprehension": 60, "grammaire": 18}


def _term_index(year: str, term: int) -> int:
    return SCHOOL_YEARS.index(year) * 3 + (term - 1)


T = _term_index  # T("2025-2026", 2) : indice du 2e trimestre de CM1


# Profils : probabilité de réussite par compétence selon l'indice du trimestre (0 = CE1 T1)
def _p_default(base):
    return lambda skill, t: base


def _awa(skill, t):
    if skill == "probleme_multi_etapes":
        return 0.78 if t < T("2024-2025", 2) else 0.25
    return {"calcul": 0.88, "numeration": 0.82, "probleme_simple": 0.78}.get(skill, 0.75)


def _moussa(skill, t):
    return {"decodage": 0.35, "comprehension": 0.42, "grammaire": 0.5,
            "probleme_multi_etapes": 0.55, "probleme_simple": 0.65}.get(skill, 0.78)


def _aminata(skill, t):
    return {"numeration": 0.3, "calcul": 0.4 if t >= T("2024-2025", 1) else 0.55}.get(skill, 0.72)


def _ibrahima(skill, t):
    return 0.35 if t == T("2025-2026", 2) else 0.74  # CM1 T2 : longue absence


def _ousmane(skill, t):
    if skill == "comprehension" and t >= T("2026-2027", 1):
        return 0.3
    return 0.68


def _fatou(skill, t):
    return 0.93 if SKILLS[skill]["subject"] == "maths" else 0.8


def _khady(skill, t):
    return 0.92 if SKILLS[skill]["subject"] == "francais" else 0.66


LEARNERS = [
    # id, prénom, nom, année de naissance, responsable, profil, préférences d'erreur, comportement
    (1, "Awa", "Ndiaye", 2016, tr("Mme Ndiaye (mère)"), _awa, {"probleme_multi_etapes": "etape_incomplete"}, {}),
    (2, "Moussa", "Diallo", 2016, tr("M. Diallo (père)"), _moussa, {"decodage": "inversion_lettres", "grammaire": "homophone"},
     {"read_aloud": 0.7, "slow_reading": 1.8}),
    (3, "Fatou", "Sow", 2016, tr("Mme Sow (mère)"), _fatou, {}, {}),
    (4, "Ibrahima", "Ba", 2015, tr("M. Ba (oncle)"), _ibrahima, {}, {}),
    (5, "Aminata", "Fall", 2016, tr("Mme Fall (grand-mère)"), _aminata, {"numeration": "valeur_position", "calcul": "retenue"},
     {"hint": 0.5}),
    (6, "Cheikh", "Mbaye", 2016, tr("M. Mbaye (père)"), _p_default(0.58), {}, {"impulsive": 0.35}),
    (7, "Mariama", "Gueye", 2016, tr("Mme Gueye (mère)"), _p_default(0.72), {}, {}),
    (8, "Ousmane", "Diouf", 2016, tr("M. Diouf (père)"), _ousmane, {"comprehension": "inference"}, {}),
    (9, "Khady", "Thiam", 2016, tr("Mme Thiam (mère)"), _khady, {}, {}),
    (10, "Lamine", "Sy", 2016, tr("M. Sy (père)"), _p_default(0.7), {}, {}),
]

OBSERVATIONS = pick({
    1: [("2021-2022", 2, "Awa adore compter, elle aide ses camarades pendant les jeux de calcul."),
        ("2024-2025", 3, "Awa calcule vite et juste. Sur les problèmes, elle donne souvent le résultat du premier calcul."),
        ("2025-2026", 2, "Toujours en difficulté sur les problèmes longs, alors qu'elle maîtrise les opérations."),
        ("2025-2026", 3, "Awa demande souvent « c'est fini ? » après la première opération d'un problème.")],
    2: [("2021-2022", 3, "Moussa reconnaît encore mal certaines lettres (b, d, p) en fin de CI."),
        ("2022-2023", 2, "Moussa raconte très bien les histoires entendues, mais déchiffre lentement."),
        ("2023-2024", 2, "Lecture hésitante, confond parfois b et d."),
        ("2024-2025", 1, "Évite de lire à voix haute. Très bonne participation à l'oral."),
        ("2025-2026", 2, "Comprend bien les histoires quand on les lui lit. Écrit lentement.")],
    4: [("2025-2026", 2, "Absent environ 5 semaines (hospitalisé, paludisme). Rattrapage organisé avec la famille."),
        ("2025-2026", 3, "Ibrahima a bien rattrapé son retard, résultats revenus à son niveau habituel.")],
    5: [("2024-2025", 2, "Aminata compte encore sur ses doigts pour les additions."),
        ("2025-2026", 1, "Difficultés avec les grands nombres : écrit 3007 pour « trois cent sept »."),
        ("2025-2026", 3, "Aminata maîtrise maintenant bien les grands nombres.")],
    7: [("2025-2026", 3, "Mariama arrive souvent en retard et manque plusieurs jours ce trimestre.")],
    6: [("2024-2025", 3, "Cheikh termine toujours le premier, beaucoup d'erreurs d'étourderie."),
        ("2025-2026", 2, "Quand on lui demande de relire, il trouve souvent seul ses erreurs.")],
    3: [("2025-2026", 3, "Fatou aide volontiers ses camarades en mathématiques."),
        ("2025-2026", 3, "Fatou a du mal en calcul, elle se trompe souvent dans ses opérations.")],
    9: [("2025-2026", 3, "Khady lit avec beaucoup d'expression, excellente compréhension.")],
}, {
    1: [("2021-2022", 2, "Awa loves counting; she helps her classmates during calculation games."),
        ("2024-2025", 3, "Awa calculates quickly and accurately. On word problems, she often gives the result of the "
                         "first calculation."),
        ("2025-2026", 2, "Still struggling with long problems, even though she has mastered the operations."),
        ("2025-2026", 3, "Awa often asks 'is it finished?' after the first operation of a problem.")],
    2: [("2021-2022", 3, "At the end of CI, Moussa still has trouble recognising some letters (b, d, p)."),
        ("2022-2023", 2, "Moussa retells the stories he hears very well, but decodes words slowly."),
        ("2023-2024", 2, "Hesitant reading, sometimes mixes up b and d."),
        ("2024-2025", 1, "Avoids reading aloud. Takes part very well in oral work."),
        ("2025-2026", 2, "Understands stories well when they are read to him. Writes slowly.")],
    4: [("2025-2026", 2, "Absent for about 5 weeks (in hospital, malaria). Catch-up work arranged with the family."),
        ("2025-2026", 3, "Ibrahima has caught up well; his results are back to his usual level.")],
    5: [("2024-2025", 2, "Aminata still counts on her fingers for additions."),
        ("2025-2026", 1, "Difficulties with large numbers: writes 3007 for \"three hundred and seven\"."),
        ("2025-2026", 3, "Aminata now has a good grasp of large numbers.")],
    7: [("2025-2026", 3, "Mariama often arrives late and has missed several days this term.")],
    6: [("2024-2025", 3, "Cheikh always finishes first, with many careless mistakes."),
        ("2025-2026", 2, "When asked to check his work again, he often finds his mistakes on his own.")],
    3: [("2025-2026", 3, "Fatou willingly helps her classmates in maths."),
        ("2025-2026", 3, "Fatou struggles with calculation; she often makes mistakes in her operations.")],
    9: [("2025-2026", 3, "Khady reads with a lot of expression; excellent comprehension.")],
})


def _date_in(year: str, term: int, rng: random.Random) -> str:
    y0 = int(year[:4])
    start = {1: date(y0, 10, 7), 2: date(y0 + 1, 1, 6), 3: date(y0 + 1, 4, 6)}[term]
    return (start + timedelta(days=rng.randint(0, 70))).isoformat()


def _simulate(rng, ex, p, pref_error, behaviour):
    """Simule une réponse : première réponse, justesse, temps, essais, usage des aides."""
    error_map = json.loads(ex["error_map"])
    impulsive = rng.random() < behaviour.get("impulsive", 0)
    correct = rng.random() < (0.2 if impulsive else p)
    if correct:
        given = ex["answer"]
    else:
        options = list(error_map)
        preferred = [c for c, e in error_map.items() if e == pref_error]
        given = rng.choice(preferred) if preferred and rng.random() < 0.8 else rng.choice(options)
    reading = ex["skill"] in ("decodage", "comprehension", "probleme_multi_etapes", "probleme_simple")
    t = BASE_TIME[ex["skill"]] * rng.lognormvariate(0, 0.3)
    if reading:
        t *= behaviour.get("slow_reading", 1.0)
    if impulsive:
        t = rng.uniform(1.5, 3.8)
    read_aloud = ex["read_aloud_text"] is not None and rng.random() < behaviour.get("read_aloud", 0.08)
    if read_aloud and ex["skill"] == "comprehension" and not correct:
        correct = rng.random() < 0.55  # la lecture à voix haute aide nettement à comprendre
        given = ex["answer"] if correct else given
    hint = rng.random() < behaviour.get("hint", 0.1)
    attempts, retry = 1, None
    if not correct:
        attempts, retry = 2, rng.random() < (0.5 if not impulsive else 0.8)
    return given, correct, round(t, 1), attempts, read_aloud, hint, retry


def seed(reset: bool = True) -> None:
    db.init(reset=reset)
    rng = random.Random(21)
    with db.connect() as c:
        c.executemany("INSERT INTO schools (id, name, city, cycle) VALUES (?,?,?,?)", SCHOOLS)
        c.executemany("INSERT INTO teachers (id, name) VALUES (?, ?)", TEACHERS)
        for i, year in enumerate(SCHOOL_YEARS):
            level = LEVEL_BY_YEAR[year]
            c.execute("INSERT INTO classes (id, name, level, school_year, teacher_id, school_id) VALUES (?,?,?,?,?,?)",
                      (i + 1, f"{level} A", level, year, TEACHERS[i][0], SCHOOL_BY_LEVEL[level]))
        for lid, fn, ln, by, guardian, *_ in LEARNERS:
            c.execute("INSERT INTO learners (id, first_name, last_name, birth_year, guardian_name, matricule) "
                      "VALUES (?,?,?,?,?,?)", (lid, fn, ln, by, guardian, f"DK-{by}-{lid:04d}"))
            for i, year in enumerate(SCHOOL_YEARS):
                c.execute("INSERT INTO enrollments VALUES (?,?,?,?)", (lid, i + 1, year, LEVEL_BY_YEAR[year]))

        bank = [dict(r) for r in c.execute("SELECT * FROM exercises WHERE origin = 'bank'")]
        by_level_skill: dict = {}
        for e in bank:
            by_level_skill.setdefault((e["level"], e["skill"]), []).append(e)

        for lid, fn, ln, by, guardian, profile, prefs, behaviour in LEARNERS:
            for year in SCHOOL_YEARS:
                for term in (1, 2, 3):
                    if (year, term) > (CURRENT_YEAR, CURRENT_TERM):
                        continue
                    t = _term_index(year, term)
                    current = (year, term) == (CURRENT_YEAR, CURRENT_TERM)
                    # Présence
                    total = 55
                    present = total - rng.randint(0, 5)
                    if lid == 4 and t == T("2025-2026", 2):   # Ibrahima : hospitalisé, un trimestre
                        present = 30
                    if lid == 7:   # Mariama : absences en hausse depuis le 2e trimestre de CM1
                        present = {T("2025-2026", 2): 47, T("2025-2026", 3): 41}.get(t, present)
                    if not current:
                        c.execute("INSERT INTO attendance (learner_id, school_year, term, days_present, days_total, source)"
                                  " VALUES (?,?,?,?,?, 'registre numérisé')", (lid, year, term, present, total))
                    # Séances : 6 réponses par compétence et par trimestre (2 au trimestre en cours)
                    n_sessions = 2 if current else 6
                    for _ in range(n_sessions):
                        d = _date_in(year, term, rng)
                        cur = c.execute("INSERT INTO sessions (learner_id, school_year, term, kind, started_at, ended_at)"
                                        " VALUES (?,?,?, 'regular', ?, ?)", (lid, year, term, d, d))
                        sid = cur.lastrowid
                        for skill in SKILLS:
                            ex = rng.choice(by_level_skill[(LEVEL_BY_YEAR[year], skill)])
                            given, ok, secs, att, ra, hint, retry = _simulate(
                                rng, ex, profile(skill, t), prefs.get(skill), behaviour)
                            c.execute(
                                "INSERT INTO answers (session_id, learner_id, exercise_id, given, correct, retry_correct,"
                                " seconds, attempts, used_read_aloud, used_hint, school_year, term, answered_at)"
                                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (sid, lid, ex["id"], given, int(ok), None if retry is None else int(retry), secs, att,
                                 int(ra), int(hint), year, term, d))
            for year, term, text in OBSERVATIONS.get(lid, []):
                teacher = TEACHERS[SCHOOL_YEARS.index(year)][1]
                c.execute("INSERT INTO observations (learner_id, author, school_year, term, date, text, source)"
                          " VALUES (?,?,?,?,?,?, 'cahier de suivi')", (lid, teacher, year, term, _date_in(year, term, rng), text))
    _sample_documents()


def _sample_documents() -> None:
    """Documents d'exemple à téléverser pendant la démo (dans samples/, pas dans uploads/)."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    out = UPLOAD_DIR.parent / "samples"
    out.mkdir(exist_ok=True)
    rows = [(fn, ln, 30 - (2 if fn == "Ibrahima" else 0) - (lid % 3)) for lid, fn, ln, *_ in LEARNERS]
    with open(out / "registre_presence_CM2A_oct2026.csv", "w", encoding="utf-8") as f:
        f.write("prenom,nom,jours_presents,jours_ouvres\n")
        for fn, ln, p in rows:
            f.write(f"{fn},{ln},{p},30\n")
        f.write("Saliou,Kane,28,30\n")  # élève inconnu : l'agent doit poser la question

    def font(size):
        for path in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    img = Image.new("RGB", (900, 620), "#fbf8ef")
    d = ImageDraw.Draw(img)
    d.text((40, 30), "Registre d'appel - CM2 A - Octobre 2026", fill="#1d2a6b", font=font(30))
    d.text((40, 80), "Prénom Nom                    Présents / Jours ouvrés", fill="#333", font=font(22))
    for i, (fn, ln, p) in enumerate(rows):
        d.text((40, 120 + i * 46), f"{fn} {ln}", fill="#1d2a6b", font=font(24))
        d.text((520, 120 + i * 46), f"{p} / 30", fill="#1d2a6b", font=font(24))
        d.line((40, 152 + i * 46, 860, 152 + i * 46), fill="#c9c2ad")
    img.save(out / "registre_presence_CM2A_scan.png")
    img.filter(ImageFilter.GaussianBlur(9)).save(out / "registre_flou.png")


if __name__ == "__main__":
    seed()
    n = db.row("SELECT COUNT(*) AS n FROM answers")["n"]
    print(tr("Base créée : {learners} élèves, {n} réponses sur {years} années scolaires.", learners=len(LEARNERS), n=n,
             years=len(SCHOOL_YEARS)))
