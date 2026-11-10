#!/usr/bin/env bash
# Linux/macOS launcher (Windows users: run.bat)
set -e
cd "$(dirname "$0")"
export USE_TF=0
source .venv/bin/activate 2>/dev/null || { echo "Run setup first: python3 -m venv .venv && pip install -r requirements.txt"; exit 1; }
(curl -s http://localhost:11434/api/tags >/dev/null 2>&1 || (command -v ollama >/dev/null && ollama serve &)) || true
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACK=$!
(cd frontend && npm run dev) &
FRONT=$!
echo "App: http://localhost:3000   API docs: http://localhost:8000/docs"
trap "kill $BACK $FRONT" EXIT
wait
