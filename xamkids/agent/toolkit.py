"""Connexion aux trois serveurs MCP locaux (stdio) via langchain-mcp-adapters.

- xamkids-profile : notre serveur, seul accès au dossier des élèves ;
- run-python (Pydantic MCP Run Python) : calculs exacts dans un bac à sable WebAssembly ;
- filesystem (serveur officiel) : lecture des documents téléversés, limitée au dossier uploads/.
"""
from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from ..config import NPX, PYTHON, ROOT, UPLOAD_DIR, tool_env
from ..i18n import tr
from ..records import audit

PROFILE_SERVER = "xamkids-profile"
# L'agent ne reçoit que les outils de lecture du serveur Filesystem.
FS_READ_TOOLS = {"read_text_file", "read_media_file", "list_directory", "get_file_info"}


def server_connections() -> dict[str, dict]:
    env = tool_env()
    connections = {
        PROFILE_SERVER: {"transport": "stdio", "command": PYTHON, "args": ["-m", "xamkids.mcp_server"],
                         "cwd": str(ROOT), "env": env},
        "run-python": {"transport": "stdio", "command": PYTHON, "args": ["-m", "mcp_run_python", "stdio"], "env": env},
    }
    if NPX:
        connections["filesystem"] = {"transport": "stdio", "command": NPX, "env": env,
                                     "args": ["-y", "@modelcontextprotocol/server-filesystem", str(UPLOAD_DIR)]}
    # Un serveur MCP peut tourner dans son propre service : XAMKIDS_MCP_RUN_PYTHON_URL, XAMKIDS_MCP_FILESYSTEM_URL…
    # (adresse terminée par /mcp). Sans la variable, il est lancé en local comme avant.
    for name in list(connections) + ["filesystem"]:
        url = os.environ.get("XAMKIDS_MCP_" + name.replace("-", "_").upper() + "_URL")
        if url:
            connections[name] = {"transport": "streamable_http", "url": url}
    return connections


class Toolkit:
    """Ouvre les serveurs MCP pour la durée d'une exécution et expose leurs outils."""

    def __init__(self) -> None:
        self.connections = server_connections()
        self.client = MultiServerMCPClient(self.connections)
        self.tools: dict[str, Any] = {}
        self.server_of: dict[str, str] = {}
        self.sessions: dict[str, Any] = {}
        self.unavailable: dict[str, str] = {}
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> "Toolkit":
        for name in self.connections:
            try:
                session = await self._stack.enter_async_context(self.client.session(name))
            except Exception as e:  # serveur emprunté absent (deno / node) : l'agent s'adapte et le signale
                self.unavailable[name] = repr(e)[:300]
                continue
            self.sessions[name] = session
            for tool in await load_mcp_tools(session):
                if name == "filesystem" and tool.name not in FS_READ_TOOLS:
                    continue
                self.tools[tool.name] = tool
                self.server_of[tool.name] = name
        if PROFILE_SERVER in self.unavailable:
            raise RuntimeError(tr("Serveur {server} indisponible : {error}", server=PROFILE_SERVER,
                                  error=self.unavailable[PROFILE_SERVER]))
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()

    def has(self, tool: str) -> bool:
        return tool in self.tools

    def catalog(self) -> str:
        """Liste des outils, telle que présentée au modèle."""
        return "\n".join(f"- {n} [{self.server_of[n]}] : {(t.description or '').splitlines()[0]}"
                         for n, t in self.tools.items())

    async def resource(self, uri: str) -> str:
        """Lit une ressource (lecture seule) du serveur xamkids-profile."""
        res = await self.sessions[PROFILE_SERVER].read_resource(uri)
        return res.contents[0].text

    async def call(self, name: str, thread_id: str | None = None, learner_id: int | None = None, /, **args) -> Any:
        """Appelle un outil. thread_id et learner_id (positionnels) servent à l'audit ; **args va à l'outil.

        Renvoie un dict pour xamkids-profile, le texte brut pour les autres serveurs
        (les blocs de contenu pour read_media_file).
        """
        server = self.server_of[name]
        if server == PROFILE_SERVER:
            args["thread_id"] = thread_id
        out = await self.tools[name].ainvoke(args)
        text = "".join(b.get("text", "") for b in out if isinstance(b, dict)) if isinstance(out, list) else str(out)
        if server == PROFILE_SERVER:  # ce serveur journalise lui-même ses appels
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"ok": False, "error": text}
        audit.log("agent", server, name, args, text, "ok", thread_id, learner_id)
        return out if name == "read_media_file" else text

