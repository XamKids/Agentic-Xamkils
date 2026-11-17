#!/bin/sh
# Service MCP « filesystem » seul : lecture des documents téléversés.
XAMKIDS_FS_ROOT=/app/uploads exec python -m xamkids.fs_server
