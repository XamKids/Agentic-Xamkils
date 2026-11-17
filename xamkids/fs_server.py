"""Serveur MCP « filesystem » déployé dans son propre service : lecture seule des documents téléversés.

Mêmes quatre outils de lecture que le serveur Filesystem officiel (read_text_file, read_media_file, list_directory,
get_file_info), limités au dossier des documents. La plateforme y dépose chaque document téléversé (PUT /files/<nom>,
authentifié par XAMKIDS_INTERNAL_TOKEN).
"""
from __future__ import annotations

import base64
import hmac
import mimetypes
import os
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

ROOT = Path(os.environ.get("XAMKIDS_FS_ROOT", "uploads")).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
TOKEN = os.environ.get("XAMKIDS_INTERNAL_TOKEN", "")

mcp = FastMCP("filesystem", log_level="WARNING")


def _safe(path: str) -> Path:
    p = Path(path).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError(f"Access denied: {path} is outside the allowed directory")
    return p


@mcp.tool()
def read_text_file(path: str) -> str:
    """Read the complete contents of a text file."""
    return _safe(path).read_text(encoding="utf-8", errors="replace")


@mcp.tool()
def read_media_file(path: str) -> list[dict]:
    """Read an image or audio file and return it as base64 data with its MIME type."""
    p = _safe(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return [{"type": "image", "data": base64.b64encode(p.read_bytes()).decode(), "mimeType": mime}]


@mcp.tool()
def list_directory(path: str) -> str:
    """List the files and directories in a directory."""
    return "\n".join(("[DIR] " if c.is_dir() else "[FILE] ") + c.name for c in sorted(_safe(path).iterdir()))


@mcp.tool()
def get_file_info(path: str) -> str:
    """Retrieve size and modification time of a file or directory."""
    p = _safe(path)
    st = p.stat()
    return f"size: {st.st_size}\nmodified: {datetime.fromtimestamp(st.st_mtime).isoformat()}\nisDirectory: {p.is_dir()}"


@mcp.custom_route("/files/{name}", methods=["PUT"])
async def upload(request: Request):
    if not TOKEN or not hmac.compare_digest(request.headers.get("x-internal-token", "").encode(), TOKEN.encode()):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    name = Path(request.path_params["name"]).name
    (ROOT / name).write_bytes(await request.body())
    return JSONResponse({"ok": True, "path": str(ROOT / name)})


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request):
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    mcp.settings.host, mcp.settings.port = "0.0.0.0", int(os.environ.get("PORT", "8503"))
    mcp.run(transport="streamable-http")
