#!/usr/bin/env bash
# Laptop worker start karo: cloud queue se jobs lega, local pipeline
# chalayega, YouTube upload karega. Laptop off = jobs cloud me safe.
set -e
cd "$(dirname "$0")"

if [ -z "$CLOUD_URL" ]; then
  read -rp "Cloud URL (e.g. https://hybrid-shorts-cloud.onrender.com): " CLOUD_URL
  export CLOUD_URL
fi
if [ -z "$DASHBOARD_PASSWORD" ] && [ -z "$WORKER_TOKEN" ]; then
  read -rsp "Dashboard password: " DASHBOARD_PASSWORD; echo
  export DASHBOARD_PASSWORD
fi

# shellcheck disable=SC1091
[ -d .venv ] && . .venv/bin/activate
exec python worker.py "$@"
