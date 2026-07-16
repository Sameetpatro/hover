# Hover

Upload a project ZIP. Hover extracts it, runs static analysis + RAG indexing, generates Architecture JSON, and renders a cinematic React + Three.js system map.

## Stack

- **Backend:** Go (chi) + Redis worker queue
- **Storage:** MinIO (S3) or local filesystem
- **DB:** SQLite (local) or PostgreSQL (Docker/prod)
- **LLM:** [OpenRouter](https://openrouter.ai) (OpenAI-compatible)
- **Frontend:** Vite + React + TypeScript + react-three-fiber + GSAP

## Quick start (local)

```bash
# Backend
cd backend
go run ./cmd/server

# Frontend (other terminal)
cd frontend && npm run dev
```

Open http://localhost:5173 and upload `fixtures/sample_app.zip`.

Optional: set `OPENROUTER_API_KEY` in `.env` for real embeddings + LLM architecture.

## Docker Compose

```bash
docker compose up --build
cd frontend && npm run dev
```

## OpenRouter

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_CHAT_MODEL=openai/gpt-4o-mini
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
```

## What else do you need?

| Mode | Needs |
|------|--------|
| Local | Go 1.22+, Node — SQLite + local disk + eager worker (default) |
| Local full stack | Docker Compose (Postgres, Redis, MinIO) |
| Production | Neon/Postgres, Upstash Redis, R2/S3, OpenRouter, host for Go API+worker, Vercel for frontend |

## API

Same contract as before (`/api/projects/`, uploads, jobs, tree, graph, symbols, architecture). Frontend unchanged.
