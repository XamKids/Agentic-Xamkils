"""Langue de la plateforme : français par défaut (langue de l'école au Sénégal), anglais en option.

La langue se choisit au lancement et vaut pour tout : interface, textes de l'agent, phrases du modèle,
exercices, voix. Changer de langue demande de recréer les données (les exercices et les observations de la
classe fictive sont créés dans la langue choisie) :

    XAMKIDS_LANG=en ./lancer.sh --reset

Deux outils :
- tr("Texte français {x}", x=...) : traduit une phrase via les catalogues xamkids/i18n_en/*.py (clé = le texte
  français exact), puis remplace les {champs}. Sans traduction connue, le français est gardé.
- pick(fr, en) : choisit entre deux valeurs structurées (listes d'exercices, consignes du modèle, expressions
  régulières…), quand une simple phrase ne suffit pas.
"""
from __future__ import annotations

import importlib
import os
import pkgutil

LANG = "en" if os.environ.get("XAMKIDS_LANG", "fr").lower().startswith("en") else "fr"
EN: dict[str, str] = {}
_loaded = False


def _catalog() -> dict[str, str]:
    global _loaded
    if not _loaded:
        from . import i18n_en
        for mod in pkgutil.iter_modules(i18n_en.__path__):
            EN.update(getattr(importlib.import_module(f"{i18n_en.__name__}.{mod.name}"), "EN", {}))
        _loaded = True
    return EN


def tr(text: str, **fields) -> str:
    """Phrase dans la langue de la plateforme. Les {champs} ne sont remplacés que si des valeurs sont données."""
    if LANG == "en" and text:
        text = _catalog().get(text, text)
    return text.format(**fields) if fields else text


def pick(fr, en):
    """Valeur dans la langue de la plateforme."""
    return en if LANG == "en" else fr


def missing(texts: list[str]) -> list[str]:
    """Phrases sans traduction anglaise (aide pour vérifier les catalogues)."""
    cat = _catalog()
    return [t for t in texts if t not in cat]
