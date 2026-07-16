# Hover

Upload a project ZIP. Hover extracts it, runs static analysis + RAG indexing, generates Architecture JSON, and renders a cinematic React + Three.js system map.

## Stack

- **Backend:** Django 6 + DRF + Celery + Redis
- **Storage:** MinIO (S3) or local filesystem
- **DB:** PostgreSQL (Docker) or SQLite (local eager mode)
- **Frontend:** Vite + React + TypeScript + react-three-fiber + GSAP

## Quick start (local, no Docker)

Uses SQLite + local file storage + in-process Celery (`CELERY_TASK_ALWAYS_EAGER`).

```bash
# Backend
cp .env.local .env   # optional override
source .venv/bin/activate
cd backend
USE_SQLITE=true USE_LOCAL_STORAGE=true CELERY_TASK_ALWAYS_EAGER=true \
  python manage.py migrate
USE_SQLITE=true USE_LOCAL_STORAGE=true CELERY_TASK_ALWAYS_EAGER=true \
  python manage.py runserver

# Frontend (other terminal)
cd frontend && npm run dev
```

Open http://localhost:5173 and upload `fixtures/sample_app.zip`.

## Full stack (Docker Compose)

```bash
docker compose up --build
```

- API: http://localhost:8000
- MinIO console: http://localhost:9001 (`minioadmin` / `minioadmin`)
- Frontend still runs via `cd frontend && npm run dev` (proxies `/api` → `:8000`)

## API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/projects/` | Create project |
| POST | `/api/projects/{id}/uploads/` | Upload ZIP (multipart `file`) |
| POST | `/api/projects/{id}/uploads/complete/` | Enqueue pipeline |
| GET | `/api/jobs/{id}/` | Job status |
| GET | `/api/projects/{id}/tree/` | File tree |
| GET | `/api/projects/{id}/graph/` | Dependency graph |
| GET | `/api/projects/{id}/symbols/` | Symbols |
| GET | `/api/projects/{id}/architecture/` | Latest Architecture JSON |
| POST | `/api/projects/{id}/architecture/generate/` | Regenerate architecture |

## Pipeline stages

`queued → extracting → detecting → analyzing → chunking → embedding → indexed → generating → ready`

## Optional LLM

Set `OPENAI_API_KEY` (and optional `OPENAI_BASE_URL`) for embedding + architecture refinement. Without a key, Hover uses deterministic local embeddings and a heuristic architecture generator from the dependency graph.
