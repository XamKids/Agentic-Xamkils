"""Scènes 3D des exercices : conçues par l'agent, vérifiées par le code.

Le modèle décrit la scène en données (des groupes d'objets) ; `verify_scene` rejette tout ce qui sort du cadre :
objets inconnus, quantités qui ne viennent pas de l'énoncé, étiquette qui donnerait la réponse.
Une scène rejetée n'est pas remplacée par des règles : l'exercice s'affiche simplement sans 3D."""
from __future__ import annotations

import json
import re
import sqlite3
import threading

from .. import llm
from ..config import RECORDS_DB, SCENE_MODEL
from ..records import audit

ITEMS = ("mango", "doughnut", "notebook", "pen", "ruler", "bread", "marble", "cube", "rod", "flat", "thousand",
         "gift", "banknote")
COLORS = ("blue", "green", "orange", "purple", "red", "yellow", "teal")
PLACE = {"cube": 1, "rod": 10, "flat": 100, "thousand": 1000}   # blocs de numération : un bloc = une valeur de position

SYSTEM = """You design a small 3D scene that helps a child of 7 to 11 understand a school exercise.
Reply with JSON only: {"groups": [{"item": ..., "count": ..., "color": ..., "tag": ...}]}
- item is one of: mango, doughnut, notebook, pen, ruler, bread, marble, cube, rod, flat, thousand, gift, banknote.
  cube = a one, rod = a ten, flat = a hundred, thousand = a thousand. Use these blocks ONLY for place-value
  questions and for additions of big numbers, never for prices, money or everyday objects.
- count is a whole number from 1 to 30, taken from the numbers written in the exercise.
  For place value, count is a digit of a number written in the exercise.
- color is one of: blue, green, orange, purple, red, yellow, teal. Use a different color for each separate group.
- tag is optional: a short label that is written in the exercise (a price like "175 F" or one of its numbers).
- Between 1 and 8 groups, in the order of the story. Use a banknote group for money handed over.
For a question about a digit or a place, show EVERY place of the number (thousand, flat, rod and cube groups,
  one group per non-zero digit), never only the place that is asked.
Show the situation only. Never show the answer, a total or a result. Never invent a number."""

_SCHEMA = "CREATE TABLE IF NOT EXISTS exercise_scenes (exercise_id TEXT PRIMARY KEY, spec TEXT, model TEXT, status TEXT)"
_busy: set[str] = set()
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(RECORDS_DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute(_SCHEMA)
    return c


def verify_scene(raw: object, prompt: str, answer: str = "") -> tuple[dict | None, list[str]]:
    """Garde les groupes valides ; renvoie (scène | None, problèmes constatés)."""
    problems: list[str] = []
    if not isinstance(raw, dict) or not isinstance(raw.get("groups"), list):
        return None, ["no groups"]
    written = {int(n) for n in re.findall(r"\d+", prompt)}
    digits = {int(d) for n in re.findall(r"\d+", prompt) for d in n}
    out = []
    for g in raw["groups"][:8]:
        if not isinstance(g, dict):
            continue
        item, count = g.get("item"), g.get("count")
        if item not in ITEMS:
            problems.append(f"unknown item {item!r}"); continue
        if isinstance(count, str) and count.isdigit():
            count = int(count)
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 30:
            problems.append(f"bad count {count!r}"); continue
        if item in PLACE and re.search(r"\d+ F\b", prompt):
            problems.append("no place-value blocks for money"); continue
        if item == "banknote":
            count = min(count, 5)
        elif count not in written and not (item in PLACE and count in digits):
            problems.append(f"count {count} is not in the exercise"); continue
        if item in PLACE and count > 9 and item != "cube":
            problems.append(f"too many {item}"); continue
        color = g.get("color") if g.get("color") in COLORS else COLORS[len(out) % len(COLORS)]
        tag = str(g.get("tag") or "").strip()[:12]
        if tag and (not re.fullmatch(r"[\d ]+ ?F?", tag) or tag.strip(" F") == str(answer).strip(" F")
                    or not any(t in prompt for t in re.findall(r"\d+", tag))):
            tag = ""
        out.append({"item": item, "count": count, "color": color, "tag": tag})
    if re.search(r"which digit", prompt):                       # question de position : toutes les positions, sinon on donne la réponse
        number = re.search(r"\d+", prompt)
        if number:
            want = {(item, int(d)) for d, item in zip(number.group().zfill(4)[-4:], ("thousand", "flat", "rod", "cube")) if d != "0"}
            have = {(g["item"], g["count"]) for g in out if g["item"] in PLACE}
            if not want <= have:
                problems.append("show every place of the number with the right block: cube = ones, rod = tens, "
                                "flat = hundreds, thousand = thousands")
    if not out:
        return None, problems or ["empty"]
    return {"groups": out}, problems


def design(exercise: dict) -> dict | None:
    """L'agent conçoit la scène (au plus deux essais, le deuxième avec les défauts du premier)."""
    user = f"Exercise: {exercise['prompt']}"
    for _ in range(2):
        out = llm.chat_json(SYSTEM, user, SCENE_MODEL, timeout=60)
        scene, problems = verify_scene(out, exercise["prompt"], str(exercise.get("answer", "")))
        if scene and not problems:
            return scene
        user += "\nYour previous answer was rejected: " + "; ".join(problems) + ". Fix it."
    return None


def cached(exercise_id: str) -> tuple[bool, dict | None]:
    """(prête ?, scène). Prête = déjà conçue, avec ou sans scène."""
    with _conn() as c:
        r = c.execute("SELECT spec FROM exercise_scenes WHERE exercise_id = ?", (exercise_id,)).fetchone()
    return (True, json.loads(r["spec"]) if r and r["spec"] else None) if r else (False, None)


def ensure(exercise: dict, learner_id: int | None = None) -> None:
    """Conçoit et enregistre la scène si elle n'existe pas encore (appel bloquant)."""
    eid = exercise["id"]
    with _lock:
        if eid in _busy or cached(eid)[0]:
            return
        _busy.add(eid)
    try:
        scene = design(exercise)
        with _conn() as c:
            c.execute("INSERT OR REPLACE INTO exercise_scenes VALUES (?,?,?,?)",
                      (eid, json.dumps(scene) if scene else None, SCENE_MODEL, "ok" if scene else "rejected"))
        audit.log("agent", "interface", "design_scene", {"exercise": eid, "model": SCENE_MODEL}, scene,
                  status="ok" if scene else "refused", learner_id=learner_id)
    finally:
        with _lock:
            _busy.discard(eid)


def prefetch(exercises: list[dict], learner_id: int | None = None) -> None:
    """Lance la conception des scènes d'une séance en arrière-plan, pour que l'élève n'attende pas."""
    def run():
        threads = [threading.Thread(target=ensure, args=(e, learner_id), daemon=True) for e in exercises
                   if e.get("subject", "maths") == "maths"]
        for t in threads:
            t.start()
    threading.Thread(target=run, daemon=True).start()
