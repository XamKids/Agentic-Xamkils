#!/usr/bin/env bash
# Lance XamKids Profile en local : modèles (Ollama), interface, agent et serveurs MCP.
#   ./lancer.sh           démarre la plateforme
#   ./lancer.sh --reset   recrée la classe de démonstration avant de démarrer
set -e
cd "$(dirname "$0")"
export PATH="$PWD/.tools/bin:$PWD/.tools/node/bin:$PWD/.tools/ollama:$PATH"
[ -d .venv ] || { echo "Créez d'abord l'environnement : voir README.md (Installation)."; exit 1; }
mkdir -p data uploads

if [ "$1" = "--reset" ]; then
  rm -f data/xamkids.db data/agent.db data/audit.db uploads/*
fi
if command -v ollama >/dev/null && ! curl -s http://127.0.0.1:11434/api/version >/dev/null; then
  nohup ollama serve > data/ollama.log 2>&1 &
  sleep 3
fi
[ -f data/xamkids.db ] || .venv/bin/python -m xamkids.records.seed
echo "XamKids Profile : http://127.0.0.1:8501"
exec .venv/bin/python app.py
