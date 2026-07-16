#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export $(grep -v '^#' .env.local | xargs)
source .venv/bin/activate
cd backend
python manage.py migrate --noinput
python manage.py runserver 0.0.0.0:8000
