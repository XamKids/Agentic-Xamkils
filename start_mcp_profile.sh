#!/bin/sh
# Service MCP « xamkids-profile » seul : il accède à la base de la plateforme par le canal interne.
XAMKIDS_MCP_HTTP_PORT="${PORT:-8504}" exec python -m xamkids.mcp_server
