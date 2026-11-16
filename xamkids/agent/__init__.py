"""Agent XamKids Profile (LangGraph), client MCP de trois serveurs locaux.

Il planifie son analyse, classe les erreurs, récupère l'historique, calcule les tendances dans un bac à sable,
forme une hypothèse, la teste par des exercices ciblés validés par l'enseignant, puis enregistre un constat
sourcé ou pose une question. Il s'interrompt chaque fois qu'une décision humaine est requise.
"""
from .runner import resume, run, run_due_followups, run_many, runs, waiting_threads

__all__ = ["run", "run_many", "resume", "runs", "waiting_threads", "run_due_followups"]
