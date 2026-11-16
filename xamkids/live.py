"""Suivre l'agent en direct dans un terminal, pendant qu'on utilise la plateforme.

    .venv/bin/python -m xamkids.live              # tout, en direct
    .venv/bin/python -m xamkids.live --details    # avec les entrées et sorties des outils
    .venv/bin/python -m xamkids.live --eleve 1    # un seul élève

Trois sources, toutes locales et en lecture seule :
- data/agent_trace.jsonl : chaque étape de raisonnement (plan, tendances, hypothèse, décision) ;
- data/audit.db          : chaque appel d'outil MCP, calcul exécuté et décision humaine ;
- data/agent.db          : début, pause (en attente de l'enseignant ou de l'élève) et fin des exécutions.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time

from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.markup import escape

from .config import AGENT_DB, AUDIT_DB, DATA_DIR, RECORDS_DB
from .i18n import LANG, pick, tr
from .knowledge import ERROR_SHORT, ERROR_TAXONOMY, SKILLS, short_label

TRACE_FILE = DATA_DIR / "agent_trace.jsonl"
TRIGGERS = pick({"term_review": "revue de trimestre", "session": "après une séance", "document": "document",
                 "guardian_summary": "résumé pour la famille", "targeted_session": "exercices ciblés",
                 "followup": "vérification programmée par l'agent"},
                {"term_review": "term review", "session": "after a session", "document": "document",
                 "guardian_summary": "family summary", "targeted_session": "check exercises",
                 "followup": "check scheduled by the agent"})
SERVER_STYLE = {"xamkids-profile": "bright_green", "run-python": "bright_magenta", "filesystem": "bright_blue", "interface": "yellow"}
RUN_STATUS = pick({"running": ("DÉBUT", "bold white", "l'agent démarre"),
                   "waiting": ("PAUSE", "bold yellow", "l'agent attend"),
                   "done": ("FIN", "bold white", "terminé"),
                   "error": ("ERREUR", "bold red", "erreur")},
                  {"running": ("START", "bold white", "the agent is starting"),
                   "waiting": ("PAUSE", "bold yellow", "the agent is waiting"),
                   "done": ("END", "bold white", "done"),
                   "error": ("ERROR", "bold red", "error")})
TAGS = pick({"agent": "AGENT", "tool": "OUTIL", "teacher": "ENSEIGNANT", "learner": "ÉLÈVE", "refused": "REFUSÉ",
             "error": "ERREUR"},
            {"agent": "AGENT", "tool": "TOOL", "teacher": "TEACHER", "learner": "LEARNER", "refused": "REFUSED",
             "error": "ERROR"})
# Actions enregistrées par la plateforme pour l'élève (libellés internes en français).
LEARNER_ACTIONS = pick({}, {"intérêts (élève)": "interests chosen", "auto-évaluation élève": "self-assessment"})
TAG_WIDTH = 11  # colonne des étiquettes (AGENT, OUTIL, ENSEIGNANT…) : tout reste aligné
INDENT = " " * (10 + TAG_WIDTH)

# Titre en grandes lettres, affiché au lancement.
_GLYPHS = {
    "X": ["█   █", " █ █ ", "  █  ", " █ █ ", "█   █"],
    "A": [" ███ ", "█   █", "█████", "█   █", "█   █"],
    "M": ["█   █", "██ ██", "█ █ █", "█   █", "█   █"],
    "K": ["█  █ ", "█ █  ", "██   ", "█ █  ", "█  █ "],
    "I": ["███", " █ ", " █ ", " █ ", "███"],
    "D": ["████ ", "█   █", "█   █", "█   █", "████ "],
    "S": [" ████", "█    ", " ███ ", "    █", "████ "],
}


def banner(word: str = "XAMKIDS") -> str:
    return "\n".join("  ".join(_GLYPHS[c][row] for c in word) for row in range(5))


def _tag(label: str, style: str) -> str:
    return f"[{style}]{label:<{TAG_WIDTH}}[/]"

console = Console(highlight=False)


def _query(path, sql: str, args: tuple = ()) -> list[dict]:
    if not path.exists():
        return []
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        c.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in c.execute(sql, args)]
        finally:
            c.close()
    except sqlite3.Error:  # base en cours d'écriture ou table pas encore créée : on réessaiera
        return []


# Codes internes (calcul, probleme_multi_etapes, fait_numerique…) remplacés par leur nom lisible à l'affichage.
_CODES = {**{k: short_label(k) for k in [*SKILLS, "presence"]},
          **{k: ERROR_SHORT.get(k) or k.replace("_", " ") for k in ERROR_TAXONOMY}}
_CODE_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, _CODES), key=len, reverse=True)) + r")\b")


def _plain(text: str) -> str:
    return _CODE_RE.sub(lambda m: _CODES[m.group(1)], text) if LANG == "en" else text


def _names() -> dict[int, str]:
    return {r["id"]: r["first_name"] for r in _query(RECORDS_DB, "SELECT id, first_name FROM learners")}


def _short(text, width: int) -> str:
    s = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)
    s = " ".join(s.split())
    return s if len(s) <= width else s[:width - 1] + "..."


def _args(inputs: str | None) -> str:
    """Arguments d'un appel d'outil, sans le bruit (thread_id, code Python complet)."""
    try:
        d = json.loads(inputs or "{}")
        if isinstance(d, str) and d.lstrip().startswith("{"):  # entrée enregistrée deux fois en JSON
            d = json.loads(d)
    except json.JSONDecodeError:  # entrée tronquée par le journal
        if '"python_code"' in (inputs or ""):
            return "python_code=" + tr("<code Python>")
        return _short(inputs or "", 80)
    if not isinstance(d, dict):
        return _short(d, 80)
    d = {k: v for k, v in d.items() if k != "thread_id" and v is not None}
    if "python_code" in d:
        d["python_code"] = tr("<{n} lignes de code>", n=len(d['python_code'].splitlines()))
    return _plain(", ".join(f"{k}={_short(v, 40)}" for k, v in d.items()))


def _who(learner_id, names: dict) -> str:
    return names.get(learner_id, tr("élève {id}", id=learner_id)) if learner_id else tr("classe")


def show_step(s: dict, names: dict) -> None:
    console.print(f"[grey82]{s['ts'][11:19]}[/]  {_tag(TAGS['agent'], 'bold bright_cyan')}[bold]{escape(_who(s.get('learner_id'), names))}[/]"
                  f" · [bright_cyan]{escape(_plain(s['title']))}[/]")
    if s.get("detail"):
        console.print(f"{INDENT}[grey82]{escape(_plain(_short(s['detail'], 400)))}[/]")


def show_call(e: dict, names: dict, details: bool) -> None:
    style = SERVER_STYLE.get(e["server"], "white")
    learner = e["actor"] == "élève"
    who = _who(e["learner_id"], names) if e["actor"] == "agent" or learner else e["actor"]
    if e["status"] in ("refused", "error"):
        tag = _tag(TAGS["refused"] if e["status"] == "refused" else TAGS["error"], "bold white on red")
    elif learner:
        tag = _tag(TAGS["learner"], "bold bright_yellow")
        e = {**e, "action": LEARNER_ACTIONS.get(e["action"], e["action"])}
    else:
        tag = _tag(TAGS["tool"], "bold") if e["actor"] == "agent" else _tag(TAGS["teacher"], "bold yellow")
    console.print(f"[grey82]{e['ts'][11:19]}[/]  {tag}[{style}]{escape(e['server'] or '')}[/]  "
                  f"[bold]{escape(e['action'])}[/]([grey82]{escape(_args(e['inputs']))}[/])  [grey82]{escape(who)}[/]")
    if e["status"] in ("refused", "error") or details:
        color = "red" if e["status"] in ("refused", "error") else "grey82"
        console.print(f"{INDENT}[{color}]{escape(_plain(_short(e['outputs'] or '', 300 if details else 200)))}[/]")


def show_run(r: dict, names: dict) -> None:
    tag, style, label = RUN_STATUS.get(r["status"], (r["status"].upper(), "white", r["status"]))
    text = _short(r["outcome"], 200) if r["status"] in ("waiting", "done", "error") and r.get("outcome") else label
    if r["status"] == "running":
        console.print()
    console.print(f"[grey82]{(r['updated_at'] or '')[11:19]}[/]  {_tag(tag, style)}[bold]{escape(_who(r['learner_id'], names))}[/]"
                  f" · {escape(TRIGGERS.get(r['trigger'], r['trigger'] or ''))} · [{style}]{escape(_plain(text))}[/]")


def main() -> None:
    ap = argparse.ArgumentParser(description=tr("Suivre l'agent XamKids en direct."))
    ap.add_argument("--details", action="store_true", help=tr("afficher les sorties de chaque outil"))
    ap.add_argument("--eleve", "--learner", dest="eleve", type=int, help=tr("identifiant d'un élève à suivre seul"))
    ap.add_argument("--historique", "--history", dest="historique", type=int, default=0,
                    help=tr("réafficher les N derniers appels avant de suivre"))
    a = ap.parse_args()

    last_audit = (_query(AUDIT_DB, "SELECT MAX(id) AS m FROM audit_log") or [{"m": 0}])[0]["m"] or 0
    last_audit = max(0, last_audit - a.historique)
    trace_pos = TRACE_FILE.stat().st_size if TRACE_FILE.exists() else 0
    run_state = {r["thread_id"]: r["status"] for r in _query(AGENT_DB, "SELECT thread_id, status FROM runs")}
    names = _names()

    console.print()
    console.print(f"[bold bright_green]{banner()}[/]")
    console.print()
    console.print(pick("[grey82]AGENT       raisonnement       OUTIL   appel d'un serveur MCP : [/][bright_green]xamkids-profile[/][grey82], [/]"
                       "[bright_magenta]run-python[/][grey82], [/][bright_blue]filesystem[/]",
                       "[grey82]AGENT       reasoning          TOOL    call to an MCP server: [/][bright_green]xamkids-profile[/][grey82], [/]"
                       "[bright_magenta]run-python[/][grey82], [/][bright_blue]filesystem[/]"))
    console.print(pick("[grey82]ENSEIGNANT  décision humaine   [/][bold white on red]REFUSÉ[/][grey82]  refusé par le serveur     "
                       "PAUSE   l'agent attend l'enseignant ou l'élève[/]",
                       "[grey82]TEACHER     human decision     [/][bold white on red]REFUSED[/][grey82] refused by the server     "
                       "PAUSE   the agent is waiting for the teacher or the learner[/]"))
    console.rule(style="grey82")
    console.print("[grey82]" + tr("En attente d'activité. Ctrl+C pour quitter.") + "[/]")
    live = Live(Text(""), console=console, refresh_per_second=8, transient=True)
    live.start()
    blink = 0
    try:
        while True:
            events = []  # (horodatage, ordre, type, données) : affichés dans l'ordre où ils se sont produits
            for e in _query(AUDIT_DB, "SELECT * FROM audit_log WHERE id > ? ORDER BY id", (last_audit,)):
                last_audit = e["id"]
                events.append((e["ts"], 0, "call", e))
            if TRACE_FILE.exists() and TRACE_FILE.stat().st_size > trace_pos:
                with TRACE_FILE.open(encoding="utf-8") as f:
                    f.seek(trace_pos)
                    chunk = f.read()
                    trace_pos = f.tell()
                for line in chunk.splitlines():
                    try:
                        s = json.loads(line)
                        events.append((s["ts"], 1, "step", s))
                    except (json.JSONDecodeError, KeyError):
                        pass
            for r in _query(AGENT_DB, "SELECT * FROM runs"):
                if run_state.get(r["thread_id"]) != r["status"]:
                    run_state[r["thread_id"]] = r["status"]
                    events.append((r["updated_at"] or "", 2, "run", r))
            # Point qui clignote tant qu'une exécution de l'agent est en cours.
            busy = [r for r in _query(AGENT_DB, "SELECT learner_id FROM runs WHERE status = 'running'")
                    if not a.eleve or r["learner_id"] in (a.eleve, None)]
            blink += 1
            if busy:
                who = ", ".join(sorted({_who(r["learner_id"], names) for r in busy}))
                dot = "[bold bright_green]●[/]" if blink % 2 else "[grey35]●[/]"
                live.update(Text.from_markup(f"{dot}  [grey82]{escape(who)} · {escape(tr('l’agent réfléchit…'))}[/]"), refresh=True)
            else:
                live.update(Text(""), refresh=True)
            if events:
                names = _names()  # un élève a pu arriver (livret)
            for _, _, kind, d in sorted(events, key=lambda x: (x[0], x[1])):
                if a.eleve and d.get("learner_id") not in (a.eleve, None):
                    continue
                {"call": lambda: show_call(d, names, a.details), "step": lambda: show_step(d, names),
                 "run": lambda: show_run(d, names)}[kind]()
            time.sleep(0.4)
    except KeyboardInterrupt:
        live.stop()
        console.print("\n[grey82]" + tr("Fin du suivi.") + "[/]")


if __name__ == "__main__":
    main()
