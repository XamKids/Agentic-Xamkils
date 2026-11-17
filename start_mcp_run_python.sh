#!/bin/sh
# Service MCP « run-python » seul (bac à sable Python), appelé par l'agent de la plateforme.
exec python -m mcp_run_python streamable-http --port "${PORT:-3001}"
