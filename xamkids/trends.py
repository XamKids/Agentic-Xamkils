"""Calcul des tendances d'un élève : partagé par le serveur MCP (outil compute_trends) et l'agent.

Le serveur xamkids-profile calcule les tendances lui-même (n'importe quel client MCP obtient donc les mêmes
chiffres exacts) ; l'agent XamKids refait ensuite le même calcul dans le bac à sable MCP Run Python
(Pyodide/WebAssembly) pour le vérifier de façon indépendante. Le code exécuté est journalisé.
"""
from __future__ import annotations

import json

from .config import LOW_ACCURACY, MIN_ANSWERS_PER_TERM, MIN_TERMS_FOR_PATTERN, STRONG_ACCURACY

TREND_PARAMS = {"low": LOW_ACCURACY, "strong": STRONG_ACCURACY, "min_n": MIN_ANSWERS_PER_TERM,
                "min_terms": MIN_TERMS_FOR_PATTERN}

TREND_FUNCTION = r'''
def analyse(data, p):
    """Pour chaque compétence : série par trimestre, trimestres faibles consécutifs, pente, erreur dominante."""
    terms = data["terms"]
    skills = sorted({s for t in terms for s in t["skills"]})
    result = {}
    for skill in skills:
        series = []
        for t in terms:
            s = t["skills"].get(skill)
            if not s:
                continue
            att = t.get("attendance") or {}
            wrong_ids = {i for e in s["errors"].values() for i in e["answer_ids"]}
            series.append({
                "term": f'{t["school_year"]} T{t["term"]}', "level": t.get("level"), "n": s["n"],
                "acc": s["accuracy"], "class_acc": s["class_accuracy"], "seconds": s["mean_seconds"],
                "read_aloud": s["read_aloud_rate"], "acc_read_aloud": s["accuracy_with_read_aloud"],
                "fast": s.get("fast_rate", 0), "retry_success": s["retry_success"],
                "low_attendance": bool(att.get("low")), "attendance_id": att.get("id"),
                "errors": {k: v["answer_ids"] for k, v in s["errors"].items()},
                "correct_ids": [i for i in s["answer_ids"] if i not in wrong_ids],
            })
        usable = [x for x in series if x["n"] >= p["min_n"]]
        for x in usable:
            gap = (x["class_acc"] - x["acc"]) if x["class_acc"] is not None else 0.0
            x["low"] = x["acc"] <= p["low"] and gap >= 0.15
            x["high"] = x["acc"] >= p["strong"] and (x["class_acc"] is None or x["acc"] >= x["class_acc"] + 0.05)
        # Trimestres faibles consécutifs, en partant du plus récent. Un trimestre faible marqué par de fortes
        # absences est « expliqué » : il n'entre pas dans la tendance mais ne l'interrompt pas non plus.
        consecutive, explained, run = 0, [], []
        for x in reversed(usable):
            if x["low"] and x["low_attendance"]:
                explained.append(x["term"])
                continue
            if not x["low"]:
                break
            consecutive += 1
            run.append(x)
        last6 = usable[-6:]
        low6 = [x for x in last6 if x["low"] and not x["low_attendance"]]
        high_run = []
        for x in reversed(usable):
            if not x["high"]:
                break
            high_run.append(x)
        errors = {}
        for x in (run or low6):
            for k, ids in x["errors"].items():
                errors.setdefault(k, []).extend(ids)
        n_err = sum(len(v) for v in errors.values())
        dominant = max(errors, key=lambda k: len(errors[k])) if errors else None
        ys = [x["acc"] for x in last6]
        if len(ys) >= 2:
            mx, my = (len(ys) - 1) / 2, sum(ys) / len(ys)
            slope = sum((i - mx) * (y - my) for i, y in enumerate(ys)) / sum((i - mx) ** 2 for i in range(len(ys)))
        else:
            slope = 0.0
        ra = [x for x in last6 if x["acc_read_aloud"] is not None]
        result[skill] = {
            "series": [{k: x[k] for k in ("term", "level", "n", "acc", "class_acc", "seconds", "read_aloud",
                                          "low_attendance")} | {"low": x.get("low"), "high": x.get("high")} for x in series],
            "consecutive_low_terms": consecutive,
            "low_terms": [x["term"] for x in reversed(run)],
            "low_terms_last6": len(low6),
            "explained_by_absence": sorted(set(explained) | {x["term"] for x in usable if x["low"] and x["low_attendance"]}),
            "pattern": consecutive >= p["min_terms"] or len(low6) >= 3,
            "latest_low": bool(usable and usable[-1]["low"]),
            "mean_acc_low_terms": round(sum(x["acc"] for x in (run or low6)) / len(run or low6), 2) if (run or low6) else None,
            "mean_class_acc_low_terms": round(sum(x["class_acc"] or 0 for x in (run or low6)) / len(run or low6), 2) if (run or low6) else None,
            "slope_last6": round(slope, 3),
            "dominant_error": dominant,
            "dominant_error_share": round(len(errors[dominant]) / n_err, 2) if dominant else None,
            "dominant_error_answer_ids": errors.get(dominant, [])[:15] if dominant else [],
            "consecutive_high_terms": len(high_run),
            "high_terms": [x["term"] for x in reversed(high_run)],
            "high_correct_ids": [i for x in high_run[:3] for i in x["correct_ids"]][:12],
            "mean_acc_high_terms": round(sum(x["acc"] for x in high_run) / len(high_run), 2) if high_run else None,
            "read_aloud_effect": round(sum(x["acc_read_aloud"] - x["acc"] for x in ra) / len(ra), 2) if ra else None,
            "fast_rate_last6": round(sum(x["fast"] for x in last6) / len(last6), 2) if last6 else 0,
            "retry_success_last6": (round(sum(x["retry_success"] for x in rs) / len(rs), 2)
                                    if (rs := [x for x in last6 if x["retry_success"] is not None]) else None),
            "low_attendance_ids": [x["attendance_id"] for x in usable if x["low"] and x["low_attendance"] and x["attendance_id"]],
        }
    dips = {}
    for skill, r in result.items():
        for x in r["series"]:
            if x.get("low"):
                dips.setdefault(x["term"], []).append(skill)
    global_dips = [{"term": t, "skills": s} for t, s in dips.items() if len(s) >= max(3, len(skills) // 2)]
    return {"skills": result, "global_dips": global_dips, "attendance": attendance_trend(terms)}


def attendance_trend(terms):
    """Présence : le dernier trimestre connu comparé à la moyenne des trois précédents."""
    rows = [(f'{t["school_year"]} T{t["term"]}', t["attendance"]) for t in terms if t.get("attendance")]
    if len(rows) < 2:
        return {"drop": False, "series": [{"term": k, "rate": a["rate"]} for k, a in rows]}
    (term, last), previous = rows[-1], [a for _, a in rows[-4:-1]]
    previous_mean = sum(a["rate"] for a in previous) / len(previous)
    since = term
    for k, a in reversed(rows[:-1]):  # début de la hausse des absences
        if a["rate"] >= previous_mean - 0.05:
            break
        since = k
    return {
        "since_term": since,
        "series": [{"term": k, "rate": a["rate"]} for k, a in rows],
        "latest_term": term, "latest_rate": last["rate"], "latest_absences": last["days_total"] - last["days_present"],
        "previous_mean": round(previous_mean, 2),
        "drop": last["rate"] < previous_mean - 0.10 and last["rate"] < 0.9,
        "recovered": last["rate"] >= previous_mean - 0.05,
        "attendance_ids": [last["id"]] + [a["id"] for a in previous],
    }
'''


def build_code(timeline: dict, params: dict) -> str:
    """Programme autonome envoyé au bac à sable : la fonction + les données + l'appel final."""
    data = {"terms": timeline["terms"]}
    return (TREND_FUNCTION + "\n\nimport json\n"
            f"DATA = json.loads({json.dumps(json.dumps(data, ensure_ascii=False))})\n"
            f"PARAMS = {json.dumps(params)}\n"
            "analyse(DATA, PARAMS)\n")


def run_locally(timeline: dict, params: dict) -> dict:
    """Repli si le bac à sable est indisponible (même code, exécuté dans le processus ; signalé dans l'audit)."""
    ns: dict = {}
    exec(TREND_FUNCTION, ns)
    return ns["analyse"]({"terms": timeline["terms"]}, params)


def compute(timeline: dict, params: dict | None = None) -> dict:
    """Calcul exact des tendances, dans le processus (utilisé par le serveur MCP)."""
    return run_locally(timeline, params or TREND_PARAMS)
