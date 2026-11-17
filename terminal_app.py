"""XamKids Terminal : service séparé qui affiche en direct ce que fait l'agent de la plateforme.

Il ne contient aucune donnée : il relaie le flux de la plateforme (XAMKIDS_TERMINAL_SOURCE) avec un jeton de lecture.
"""
import os
from pathlib import Path

import httpx
from flask import Flask, Response, render_template, request

SOURCE = os.environ.get("XAMKIDS_TERMINAL_SOURCE", "http://127.0.0.1:8501").rstrip("/")
TOKEN = os.environ.get("XAMKIDS_TERMINAL_TOKEN", "")

app = Flask(__name__, template_folder=str(Path(__file__).parent / "xamkids/web/templates"))


@app.get("/")
def home():
    return render_template("terminal.html", back=SOURCE + "/enseignant/", feed="/feed")


@app.get("/feed")
def feed():
    try:
        r = httpx.get(f"{SOURCE}/terminal/feed", params=request.args, headers={"X-Terminal-Token": TOKEN}, timeout=60)
        return Response(r.content, r.status_code, mimetype="application/json")
    except httpx.HTTPError:
        return Response('{"html": "", "next": %s}' % (request.args.get("after") or "null"), 200, mimetype="application/json")


@app.get("/health")
def health():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8502")), threaded=True)
