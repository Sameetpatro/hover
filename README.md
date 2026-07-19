# Hover

Upload a ZIP of your code. Hover analyzes it and shows a **3D animated map** of how your system is built — layers, components, and data flowing between them — so you can understand a project without reading every file.

---

## How the app works

```text
ZIP upload
   → extract files
   → detect languages & roles (UI / API / services / data)
   → build dependency graph + symbols
   → split code into smart chunks
   → RAG (embed + retrieve + LLM)
   → Architecture JSON
   → React + Three.js 3D map
```

1. You drop a project ZIP on the home page.  
2. The backend unzips it safely and scans the code (imports, functions, APIs, workers, models).  
3. Code is cut into chunks and turned into vectors.  
4. **RAG** pulls the most relevant chunks and helps build an Architecture JSON (layers, components, flows).  
5. The frontend draws that JSON as a layered 3D scene: nodes you can click, flows with moving packets, plus Tree / Classes / Flows tabs.

---

## What is used in this app

| Part | Technology | Role |
|------|------------|------|
| Backend API | **Python + FastAPI** | Upload, jobs, tree, graph, architecture endpoints |
| Analysis | Custom static analysis | Languages, roles, imports, symbols, dependency graph |
| RAG / LLM | **LangChain** + **OpenRouter** | Embeddings, retrieval, architecture refinement |
| Database | **SQLite** (local) or Postgres | Projects, jobs, chunks, architecture snapshots |
| Jobs | Background thread (or Redis worker) | Runs analysis without blocking the UI |
| Frontend | **React + TypeScript + Vite** | Upload UI and visualization pages |
| 3D | **Three.js** (react-three-fiber) + GSAP | Cinematic system map and animations |

Optional: set `OPENROUTER_API_KEY` for real embeddings and LLM-refined architecture. Without a key, Hover still runs using local hash embeddings and a heuristic architecture from the graph.

---

## RAG technology (simple explanation)

**RAG** = Retrieval-Augmented Generation.

1. **Index** — each code chunk becomes a vector (a list of numbers meaning “what this code is about”).  
2. **Retrieve** — when building architecture, Hover asks: which chunks talk about APIs, data flow, workers, storage? The closest vectors are pulled back.  
3. **Generate** — those chunks are given to an LLM (via LangChain → OpenRouter) to refine the Architecture JSON used by the 3D view.

So the map is grounded in *your* code, not a generic guess. LangChain code lives mainly in `backend/app/services/rag.py`.

---

## How to use this app

### Run locally

**Terminal 1 — backend**

```bash
cd /Users/sameetpatro/Desktop/Projects/Hover
source .venv/bin/activate
cd backend
export PYTHONPATH=.
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend**

```bash
cd /Users/sameetpatro/Desktop/Projects/Hover/frontend
npm run dev
```

Open **http://localhost:5173**.

### Try it

1. Drop a project ZIP (or use `fixtures/sample_app.zip`).  
2. Watch pipeline stages until the job finishes.  
3. You land on the visualize page:
   - **3D map** — tap a node to see what data comes in / goes out  
   - **Tree** — full project file tree  
   - **Classes** — who depends on whom  
   - **Flows** — step-by-step data-flow stories  
4. Use **All traffic** to see all dependency links; pick a named flow to highlight one path.  
5. **Regenerate** rebuilds architecture JSON (uses OpenRouter if configured).

### Optional OpenRouter

In `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_CHAT_MODEL=openai/gpt-4o-mini
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
```

Restart the backend after changing `.env`.

---
