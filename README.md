# Hover

Upload a project ZIP → **FastAPI + LangChain** analyzes it → React + Three.js shows a 3D system map.

**Guide:** [docs/HOVER_EXPLAINED.md](docs/HOVER_EXPLAINED.md)

## Quick start

```bash
# Terminal 1 — Python API
source .venv/bin/activate
cd backend
export PYTHONPATH=.
uvicorn app.main:app --reload --port 8000

# Terminal 2 — React UI
cd frontend && npm run dev
```

Open http://localhost:5173 and upload `fixtures/sample_app.zip`.

## Stack

| Layer | Tech |
|-------|------|
| API | **FastAPI** |
| RAG / LLM | **LangChain** + OpenRouter |
| DB | SQLite (local) or Postgres |
| Jobs | Thread (eager) or Redis worker |
| Frontend | React + Three.js |

## OpenRouter (optional)

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_CHAT_MODEL=openai/gpt-4o-mini
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
```

Without a key, Hover still works (local hash embeddings + heuristic architecture).
