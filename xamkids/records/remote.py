"""Accès distant à la base SQLite de la plateforme, pour un serveur MCP déployé dans son propre service.

La plateforme garde les fichiers (xamkids.db, audit.db). Le serveur xamkids-profile, lui, tourne ailleurs et
passe par ce canal : chaque transaction est ouverte, utilisée puis validée côté plateforme.
Variables : XAMKIDS_DB_REMOTE_URL (adresse de la plateforme) et XAMKIDS_INTERNAL_TOKEN (secret partagé).
"""
from __future__ import annotations

import os

import httpx

URL = os.environ.get("XAMKIDS_DB_REMOTE_URL", "").rstrip("/")
TOKEN = os.environ.get("XAMKIDS_INTERNAL_TOKEN", "")
ENABLED = bool(URL and TOKEN)


class Row:
    """Ligne de résultat : accessible par nom ou par position, comme sqlite3.Row."""

    def __init__(self, keys: list[str], values: list):
        self._keys, self._values = keys, values

    def keys(self):
        return list(self._keys)

    def __getitem__(self, k):
        return self._values[k] if isinstance(k, int) else self._values[self._keys.index(k)]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


class Cursor:
    def __init__(self, data: dict):
        self.rows = [Row(data["keys"], r) for r in data["rows"]]
        self.lastrowid, self.rowcount = data.get("lastrowid"), data.get("rowcount", -1)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class RemoteConnection:
    def __init__(self, kind: str):
        self.kind = kind
        self._http = httpx.Client(timeout=60, headers={"X-Internal-Token": TOKEN})
        self.id = None  # la transaction s'ouvre au premier appel

    def _post(self, body: dict) -> dict:
        r = self._http.post(f"{URL}/internal/db/{self.kind}", json=body)
        r.raise_for_status()
        return r.json()

    def execute(self, sql: str, args=()) -> Cursor:
        if self.id is None:
            self.id = self._post({"op": "begin"})["id"]
        return Cursor(self._post({"op": "exec", "id": self.id, "sql": sql, "args": list(args)}))

    def executescript(self, script: str) -> None:  # le schéma est créé par la plateforme
        return None

    def commit(self) -> None:
        if self.id is not None:
            self._post({"op": "end", "id": self.id, "commit": True})
            self.id = None

    def close(self) -> None:
        try:
            if self.id is not None:
                self._post({"op": "end", "id": self.id, "commit": False})
                self.id = None
        finally:
            self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        try:
            if exc_type is None:
                self.commit()
        finally:
            self.close()
        return False
