"""Évaluation : que change le modèle local par rapport aux règles seules ?

Sur une copie fraîche de la classe fictive, pour chaque élève :
  1. choix de l'hypothèse (piste) : règles seules, puis modèle local + vérification, N passages ;
  2. contradictions entre observations écrites et chiffres : modèle local + vérification, N passages
     (les règles ne lisent pas le texte : elles n'en trouvent jamais).
Les réponses attendues sont écrites à la main ci-dessous (EXPECTED), à partir des profils de seed.py.

    .venv/bin/python -m evals.run_evals            # 3 passages du modèle par élève
    .venv/bin/python -m evals.run_evals --runs 5

Résultats : evals/results.json (le détail) et un tableau Markdown à recopier dans EVALS.md.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

WORK = Path(__file__).resolve().parent / ".work"
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)
# Base de données jetable : l'évaluation ne touche jamais aux données de la plateforme.
os.environ["XAMKIDS_RECORDS_DB"] = str(WORK / "xamkids.db")
os.environ["XAMKIDS_AUDIT_DB"] = str(WORK / "audit.db")

from xamkids import llm, mcp_server  # noqa: E402
from xamkids.agent import contradictions, reasoning  # noqa: E402
from xamkids.agent import trends as trend_code  # noqa: E402
from xamkids.agent.nodes import TREND_PARAMS  # noqa: E402
from xamkids.records import seed  # noqa: E402

# Pistes attendues (None = aucune nouvelle hypothèse attendue ; « *:rythme » = la piste rythme, quelle que soit la
# compétence) et contradictions attendues (compétences). Écrites à la main à partir des profils de seed.py.
EXPECTED = {
    "Awa": {"options": {"probleme_multi_etapes:locale"}},
    "Moussa": {"options": {"decodage:locale", "probleme_multi_etapes:lecture"}},
    "Aminata": {"options": {"numeration:locale", "calcul:locale"}, "contradictions": {"numeration"}},
    "Cheikh": {"options": {"*:rythme"}},
    "Fatou": {"options": None, "contradictions": {"calcul"}},
    "Ibrahima": {"options": None},
    "Khady": {"options": None},
    "Mariama": {"options": None},
    "Lamine": {"options": None},
    # Ousmane : une baisse d'un seul trimestre ; ce que les règles trouvent en plus vient du hasard (6 réponses par
    # trimestre). Le tester n'est pas une faute : les exercices ciblés doivent l'écarter.
    "Ousmane": {"options": None, "test_acceptable": True},
}
CATALOG = "\n".join(f"- {n}" for n in ("get_learner_timeline", "analyze_answers", "propose_exercises",
                                       "update_profile", "alert_teacher", "draft_guardian_summary"))


def build_state(lid: int, mode: str) -> dict:
    timeline = mcp_server.get_learner_timeline(lid, thread_id="eval")
    return {"thread_id": "eval", "trigger": "term_review", "learner_id": lid, "mode": mode,
            "plan": {"focus": "tout"}, "timeline": timeline, "rounds": 0, "hypothesis": None,
            "trends": trend_code.run_locally(timeline, TREND_PARAMS)}


def option_of(decision: dict) -> str | None:
    return decision.get("option") if decision.get("action") == "propose_exercises" else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if not llm.status()["llm"]:
        sys.exit(f"Modèle {llm.status()['llm_model']} indisponible : lancez Ollama.")
    seed.seed()
    learners = mcp_server.db.rows("SELECT id, first_name FROM learners ORDER BY id")
    for l in learners:
        mcp_server.analyze_answers(l["id"], thread_id="eval")

    results = []
    for l in learners:
        name, exp = l["first_name"], EXPECTED.get(l["first_name"], {"options": None})
        rules_state = build_state(l["id"], "rules")
        rules = reasoning.decide(rules_state, CATALOG)[0]
        row = {"learner": name, "expected_options": sorted(exp["options"] or []),
               "expected_contradictions": sorted(exp.get("contradictions", set())),
               "options_available": [o["id"] for o in reasoning.hypothesis_options(rules_state)],
               "rules": option_of(rules), "model_runs": []}
        for _ in range(args.runs):
            state = build_state(l["id"], "llm")
            t0 = time.time()
            decision, title, detail = reasoning.decide(state, CATALOG)
            t1 = time.time()
            found, rejected, n_obs = contradictions.find(state)
            t2 = time.time()
            row["model_runs"].append({
                "option": option_of(decision), "source": decision.get("source"),
                "rejected_by_verification": "rejetée" in title, "detail": detail[:400],
                "cited_observations": decision.get("observations") or [],
                "contradictions": sorted({c["competence"] for c in found}), "contradictions_rejected": rejected,
                "seconds_decision": round(t1 - t0, 1), "seconds_contradictions": round(t2 - t1, 1)})
            print(f"{name}: modèle → {row['model_runs'][-1]['option']} ({decision.get('source')}), "
                  f"contradictions {row['model_runs'][-1]['contradictions']}, rejetées {len(rejected)}", flush=True)
        results.append(row)

    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps({"model": llm.status()["llm_model"], "runs": args.runs, "results": results},
                              ensure_ascii=False, indent=2))
    print("\n" + table(results, args.runs))


def ok_option(option: str | None, expected: set | None) -> bool:
    if not expected:
        return option is None
    return option is not None and any(option == e or (e.startswith("*:") and option.endswith(e[1:])) for e in expected)


def table(results: list[dict], runs: int) -> str:
    lines = ["| Élève | Piste attendue | Règles | Agent avec modèle (bonnes / passages) | Décisions du modèle rejetées | "
             "Contradictions attendues | Questions justes | Fausses questions | Propositions bloquées par le code |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        expected = set(r["expected_options"]) or None
        good = sum(ok_option(m["option"], expected) for m in r["model_runs"])
        exp_c = set(r["expected_contradictions"])
        right = sum(len(set(m["contradictions"]) & exp_c) for m in r["model_runs"])
        wrong = sum(len(set(m["contradictions"]) - exp_c) for m in r["model_runs"])
        blocked = sum(len(m["contradictions_rejected"]) for m in r["model_runs"])
        rejected = sum(m["rejected_by_verification"] for m in r["model_runs"])
        lines.append(f"| {r['learner']} | {', '.join(r['expected_options']) or 'aucune'} | "
                     f"{r['rules'] or 'aucune'} {'✅' if ok_option(r['rules'], expected) else '❌'} | "
                     f"{good}/{runs} | {rejected}/{runs} | {', '.join(sorted(exp_c)) or 'aucune'} | "
                     f"{right}/{len(exp_c) * runs} | {wrong} | {blocked} |")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
