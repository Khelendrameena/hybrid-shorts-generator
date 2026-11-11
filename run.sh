#!/usr/bin/env bash
# Linux/macOS launcher (Windows users: run.bat)
set -e
cd "$(dirname "$0")"
export USE_TF=0
source .venv/bin/activate 2>/dev/null || { echo "Run setup first: python3 -m venv .venv && pip install -r requirements.txt"; exit 1; }
# pip-bundled CUDA libraries (nvidia-cublas-cu12 / nvidia-cudnn-cu12) — in WSL
# bina CUDA toolkit ke Whisper ko GPU dene ke liye. Hon to loader path me daal do.
for d in .venv/lib/python*/site-packages/nvidia/cublas/lib .venv/lib/python*/site-packages/nvidia/cudnn/lib; do
  [ -d "$d" ] && export LD_LIBRARY_PATH="$PWD/$d:${LD_LIBRARY_PATH:-}"
done
(curl -s http://localhost:11434/api/tags >/dev/null 2>&1 || (command -v ollama >/dev/null && ollama serve &)) || true
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACK=$!
(cd frontend && npm run dev) &
FRONT=$!
echo "App: http://localhost:3000   API docs: http://localhost:8000/docs"
trap "kill $BACK $FRONT" EXIT
wait
