"""Le terminal de suivi de l'agent (xamkids.live), affiché dans le navigateur.

Même contenu que `python -m xamkids.live --details` : chaque étape de raisonnement, chaque appel d'outil MCP,
chaque décision humaine, en direct. Lecture seule.
"""
from __future__ import annotations

import html
import io
import re
import threading
import time

from flask import jsonify, render_template, request
from rich.console import Console

from .. import live

HISTORY = 40          # derniers appels réaffichés à l'ouverture, pour que l'écran ne soit pas vide
KEEP = 4000           # morceaux conservés en mémoire

_lock = threading.Lock()
_chunks: list[str] = []   # morceaux de HTML, dans l'ordre
_base = 0                 # numéro du premier morceau conservé
_started = False

_BASIC = ["#1c1c1c", "#e5534b", "#3fb950", "#d4a72c", "#58a6ff", "#bc8cff", "#39c5cf", "#c9d1d9"]
_BRIGHT = ["#6e7681", "#ff7b72", "#56d364", "#e3b341", "#79c0ff", "#d2a8ff", "#56d4dd", "#ffffff"]
_SGR = re.compile(r"\x1b\[([0-9;]*)m")


def _xterm(n: int) -> str:
    if n < 8:
        return _BASIC[n]
    if n < 16:
        return _BRIGHT[n - 8]
    if n < 232:
        n -= 16
        return "#%02x%02x%02x" % tuple(0 if v == 0 else 55 + 40 * v for v in (n // 36, (n // 6) % 6, n % 6))
    g = 8 + 10 * (n - 232)
    return "#%02x%02x%02x" % (g, g, g)


def ansi_to_html(text: str) -> str:
    """Convertit les séquences de couleur ANSI produites par rich en HTML."""
    fg = bg = None
    bold = False
    out, pos, open_span = [], 0, False

    def close():
        nonlocal open_span
        if open_span:
            out.append("</span>")
            open_span = False

    for m in _SGR.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        pos = m.end()
        codes = [int(c) if c else 0 for c in m.group(1).split(";")]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                fg = bg = None; bold = False
            elif c == 1:
                bold = True
            elif c == 22:
                bold = False
            elif 30 <= c <= 37:
                fg = _BASIC[c - 30]
            elif 90 <= c <= 97:
                fg = _BRIGHT[c - 90]
            elif 40 <= c <= 47:
                bg = _BASIC[c - 40]
            elif 100 <= c <= 107:
                bg = _BRIGHT[c - 100]
            elif c == 39:
                fg = None
            elif c == 49:
                bg = None
            elif c in (38, 48) and i + 2 < len(codes) and codes[i + 1] == 5:
                if c == 38:
                    fg = _xterm(codes[i + 2])
                else:
                    bg = _xterm(codes[i + 2])
                i += 2
            i += 1
        close()
        style = ";".join(filter(None, [f"color:{fg}" if fg else "", f"background:{bg}" if bg else "",
                                       "font-weight:700" if bold else ""]))
        if style:
            out.append(f'<span style="{style}">')
            open_span = True
    out.append(html.escape(text[pos:]))
    close()
    return "".join(out)


def _emit(buf: io.StringIO) -> None:
    global _chunks, _base
    text = buf.getvalue()
    if not text:
        return
    buf.seek(0)
    buf.truncate()
    with _lock:
        _chunks.append(ansi_to_html(text))
        if len(_chunks) > KEEP:
            drop = len(_chunks) - KEEP
            _chunks = _chunks[drop:]
            _base += drop


def _run() -> None:
    buf = io.StringIO()
    live.console = Console(file=buf, force_terminal=True, color_system="256", width=150, highlight=False)
    c = live.console
    c.print(f"[bold bright_green]{live.banner()}[/]")
    c.print()
    c.print(live.pick("[grey82]AGENT       raisonnement       OUTIL   appel d'un serveur MCP[/]",
                      "[grey82]AGENT       reasoning          TOOL    call to an MCP server: [/][bright_green]xamkids-profile[/]"
                      "[grey82], [/][bright_magenta]run-python[/][grey82], [/][bright_blue]filesystem[/]"))
    c.print("[grey82]TEACHER     human decision     [/][bold white on red]REFUSED[/][grey82] refused by the server     "
            "PAUSE   the agent is waiting for the teacher or the learner[/]")
    c.rule(style="grey82")
    _emit(buf)
    state = live.initial_state(HISTORY)
    names = live._names()
    while True:
        try:
            events = live.new_events(state)
            if events:
                names = live._names()
            for _, _, kind, d in sorted(events, key=lambda x: (x[0], x[1])):
                live.show_event(kind, d, names, True)
            _emit(buf)
        except Exception:  # le suivi ne doit jamais faire tomber la plateforme
            pass
        time.sleep(0.5)


def _ensure_started() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_run, name="xamkids-terminal", daemon=True).start()


def register(app) -> None:
    @app.get("/terminal")
    def terminal():
        _ensure_started()
        return render_template("terminal.html")

    @app.get("/terminal/feed")
    def terminal_feed():
        _ensure_started()
        after = request.args.get("after", type=int)
        with _lock:
            end = _base + len(_chunks)
            start = max(after if after is not None else _base, _base)
            return jsonify({"html": "".join(_chunks[start - _base:]), "next": end})
