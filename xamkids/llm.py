"""Modèles open-weights locaux via Ollama : rien ne quitte l'école.

Si Ollama ou le modèle n'est pas disponible, l'agent passe en « mode règles » : mêmes étapes, mêmes outils
et mêmes garde-fous, mais les hypothèses et les résumés viennent de règles et de modèles de phrases.
"""
from __future__ import annotations

import base64
import json
import re

import httpx

from .config import LLM_MODEL, OLLAMA_URL, VLM_MODEL


def _installed_models() -> list[str]:
    try:
        return [m["name"] for m in httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).json().get("models", [])]
    except Exception:
        return []


def status() -> dict:
    models = _installed_models()
    has = lambda m: m in models or f"{m}:latest" in models  # noqa: E731
    return {"llm": has(LLM_MODEL), "vlm": has(VLM_MODEL), "llm_model": LLM_MODEL, "vlm_model": VLM_MODEL}


def _parse_json(text: str) -> dict | None:
    for candidate in (text, (re.search(r"\{.*\}", text or "", re.S) or [None])[0]):
        try:
            return json.loads(candidate)
        except (TypeError, ValueError):
            continue
    return None


def chat_json(system: str, user: str, model: str = LLM_MODEL, images: list[bytes] | None = None,
              timeout: float = 180, temperature: float = 0.1) -> dict | None:
    """Appel au modèle local en sortie JSON. Renvoie None si le modèle est indisponible ou la sortie invalide."""
    message: dict = {"role": "user", "content": user}
    if images:
        message["images"] = [base64.b64encode(i).decode() for i in images]
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=timeout, json={
            "model": model, "stream": False, "format": "json", "options": {"temperature": temperature},
            "messages": [{"role": "system", "content": system}, message],
        })
        r.raise_for_status()
        return _parse_json(r.json()["message"]["content"])
    except Exception:
        return None
