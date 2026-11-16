"""Modèles open-weights locaux via Ollama : rien ne quitte l'école.

Si Ollama ou le modèle n'est pas disponible, l'agent passe en « mode règles » : mêmes étapes, mêmes outils
et mêmes garde-fous, mais les hypothèses et les résumés viennent de règles et de modèles de phrases.
"""
from __future__ import annotations

import base64
import json
import re

import httpx

import os

from .config import LLM_MODEL, OLLAMA_URL, VLM_MODEL

# Démonstration en ligne : un service compatible avec l'API « chat completions » (par exemple OpenRouter) peut
# remplacer Ollama. Dans une école, ces variables restent vides : tout tourne sur la machine.
API_URL = os.environ.get("XAMKIDS_LLM_API_URL", "").rstrip("/")
API_KEY = os.environ.get("XAMKIDS_LLM_API_KEY", "")


def _installed_models() -> list[str]:
    try:
        return [m["name"] for m in httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).json().get("models", [])]
    except Exception:
        return []


def status() -> dict:
    if API_URL:
        return {"llm": True, "vlm": True, "llm_model": LLM_MODEL, "vlm_model": VLM_MODEL}
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
    if API_URL:
        return _chat_json_api(system, user, model, images, timeout, temperature)
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=timeout, json={
            "model": model, "stream": False, "format": "json", "options": {"temperature": temperature},
            "messages": [{"role": "system", "content": system}, message],
        })
        r.raise_for_status()
        return _parse_json(r.json()["message"]["content"])
    except Exception:
        return None


def _chat_json_api(system: str, user: str, model: str, images: list[bytes] | None, timeout: float,
                   temperature: float) -> dict | None:
    """Même contrat que chat_json, via un service hébergé compatible « chat completions »."""
    content: list | str = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(i).decode()}}
            for i in images]
    body = {"model": model, "temperature": temperature, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    for attempt in (body, {k: v for k, v in body.items() if k != "response_format"}):  # 2e essai sans format imposé
        try:
            r = httpx.post(f"{API_URL}/chat/completions", timeout=timeout, headers=headers, json=attempt)
            r.raise_for_status()
            if (out := _parse_json(r.json()["choices"][0]["message"]["content"])) is not None:
                return out
        except Exception:
            continue
    return None
