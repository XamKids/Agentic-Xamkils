"""Câblage du graphe LangGraph.

plan ─▶ [étapes choisies dans le plan : analyze → retrieve → trends → crosscheck → monitor → reason | summarize]
  │       reason ─┬─ propose → ⏸ wait_approval → ⏸ wait_results → plan (nouveau plan avec les réponses)
  │               ├─ record
  │               ├─ ask_teacher
  │               ╰─ finish
  ╰─▶ read_document (un document est arrivé)
"""
from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..config import DATA_DIR
from .nodes import Nodes
from .state import State
from .toolkit import Toolkit


TRACE_FILE = DATA_DIR / "agent_trace.jsonl"
PLANNED = ["analyze", "retrieve", "trends", "crosscheck", "monitor", "reason", "summarize"]


def _next_planned(state: State) -> str:
    """Prochaine étape du plan pas encore faite."""
    if state["trigger"] == "document":
        return "read_document"
    done = state.get("done_steps", [])
    return next((s for s in state["plan"]["steps"] if s not in done), "finish")


def _traced(name: str, fn):
    """Écrit chaque étape de raisonnement dans la trace en direct (data/agent_trace.jsonl), au moment où
    elle se produit, pour la suivre dans un terminal : .venv/bin/python -m xamkids.live"""
    async def node(state: State) -> dict:
        update = await fn(state) or {}
        try:
            with TRACE_FILE.open("a", encoding="utf-8") as f:
                for s in update.get("steps", []):
                    f.write(json.dumps({"ts": s["ts"], "node": name, "thread_id": state.get("thread_id"),
                                        "learner_id": state.get("learner_id"), "title": s["title"],
                                        "detail": s["detail"]}, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass  # la trace en direct est un confort d'affichage : elle ne doit jamais bloquer l'agent
        return update
    return node


def _tracked(name: str, fn):
    """Marque l'étape comme faite, pour que le graphe passe à la suivante du plan."""
    async def node(state: State) -> dict:
        update = await fn(state)
        return {**update, "done_steps": state.get("done_steps", []) + [name]}
    return node


def _after_reason(state: State) -> str:
    return {"propose_exercises": "propose", "record_finding": "record", "rule_out": "record",
            "ask_teacher": "ask_teacher"}.get(state["decision"]["action"], "finish")


def _after_approval(state: State) -> str:
    return "finish" if state.get("outcome") else "wait_results"  # un refus renseigne l'issue


def build_graph(tk: Toolkit, checkpointer) -> Any:
    n = Nodes(tk)
    g = StateGraph(State)
    for name in ("plan", "read_document", "propose", "wait_approval", "wait_results", "record", "ask_teacher", "finish"):
        g.add_node(name, _traced(name, getattr(n, name)))
    for name in PLANNED:
        g.add_node(name, _tracked(name, _traced(name, getattr(n, name))))

    g.add_edge(START, "plan")
    targets = PLANNED + ["read_document", "finish"]
    for name in ["plan", "analyze", "retrieve", "trends", "crosscheck", "monitor"]:
        g.add_conditional_edges(name, _next_planned, targets)
    g.add_edge("read_document", "finish")
    g.add_conditional_edges("reason", _after_reason, ["propose", "record", "ask_teacher", "finish"])
    g.add_edge("propose", "wait_approval")
    g.add_conditional_edges("wait_approval", _after_approval, ["wait_results", "finish"])
    g.add_edge("wait_results", "plan")
    for name in ("record", "ask_teacher", "summarize"):
        g.add_edge(name, "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)
