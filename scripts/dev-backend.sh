#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
cd backend
export PYTHONPATH=.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
