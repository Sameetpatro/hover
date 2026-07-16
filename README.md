# Hover

Upload a project ZIP. Hover extracts it, runs static analysis + RAG indexing, generates Architecture JSON, and renders a cinematic React + Three.js system map.

## Stack

- **Backend:** Django 6 + DRF + Celery + Redis
- **Storage:** MinIO (S3) or local filesystem
- **DB:** PostgreSQL (Docker) or SQLite (local eager mode)
- **LLM:** [OpenRouter](https://openrouter.ai) (OpenAI-compatible)
- **Frontend:** Vite + React + TypeScript + react-three-fiber + GSAP

## Quick start (local, no Docker)

Uses SQLite + local file storage + in-process Celery (`CELERY_TASK_ALWAYS_EAGER`).

```bash
# 1. Add your OpenRouter key to .env
# OPENROUTER_API_KEY=sk-or-v1-...

source .venv/bin/activate
cd backend
python manage.py migrate
python manage.py runserver

# Frontend (other terminal)
cd frontend && npm run dev
```

Open http://localhost:5173 and upload `fixtures/sample_app.zip`.

## OpenRouter setup

1. Create a key at https://openrouter.ai/keys
2. Put credits on the account (pay-as-you-go)
3. Set in `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_CHAT_MODEL=openai/gpt-4o-mini
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
```

Without a key, Hover still runs using local hash embeddings + a heuristic architecture generator (no LLM).

## Full stack (Docker Compose)

```bash
docker compose up --build
```

- API: http://localhost:8000
- MinIO console: http://localhost:9001 (`minioadmin` / `minioadmin`)
- Frontend: `cd frontend && npm run dev` (proxies `/api` → `:8000`)

## What else do you need?

### Local development (minimum)

| Need | Option | Notes |
|------|--------|-------|
| Nothing extra | Current `.env` defaults | SQLite + local disk + eager Celery — works offline |
| Better RAG | `OPENROUTER_API_KEY` | Only external account you must add for LLM quality |

`docker compose` already gives you Postgres, Redis, and MinIO on your machine — you do **not** need Neon/Render for local work.

### Production / deploy (recommended)

| Concern | Suggested service | Why |
|---------|-------------------|-----|
| Postgres | **Neon** or Render Postgres | App data, jobs, chunks, architecture snapshots |
| Redis (queue) | **Upstash Redis** or Redis on Render | Celery broker for async ZIP analysis |
| Object storage | **Cloudflare R2** / AWS S3 / MinIO on a VPS | Store uploaded ZIPs (S3-compatible) |
| LLM | **OpenRouter** | Chat + embeddings (already wired) |
| Backend host | **Render** / Railway / Fly.io | Run Django `web` + Celery `worker` |
| Frontend host | **Vercel** / Netlify / Cloudflare Pages | Static Vite build; point API URL at backend |

You do **not** need a separate vector DB (Pinecone, etc.) right now — embeddings live in Postgres/SQLite via the app. A dedicated pgvector Neon DB is a nice upgrade later, not required to ship.

### Env vars to set in production

```env
DJANGO_SECRET_KEY=...          # strong secret
DJANGO_DEBUG=false
USE_SQLITE=false
USE_LOCAL_STORAGE=false
CELERY_TASK_ALWAYS_EAGER=false

POSTGRES_HOST=...              # Neon / Render connection
POSTGRES_DB=...
POSTGRES_USER=...
POSTGRES_PASSWORD=...

CELERY_BROKER_URL=rediss://... # Upstash / managed Redis
CELERY_RESULT_BACKEND=rediss://...

AWS_ACCESS_KEY_ID=...          # R2 / S3
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=hover
AWS_S3_ENDPOINT_URL=...         # e.g. https://<account>.r2.cloudflarestorage.com

OPENROUTER_API_KEY=sk-or-v1-...
```

### Not required yet

- Kafka (Redis/Celery is enough)
- Auth/billing
- Separate Pinecone/Weaviate cluster
- Custom fine-tuned models

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
