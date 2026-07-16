## Hover pipeline (Go)

1. **Upload** — ZIP stored in MinIO/S3 or local media
2. **Extract** — safe unzip + file inventory
3. **Detect** — language + role heuristics
4. **Analyze** — imports, symbols, dependency graph
5. **Chunk** — symbol-aware code chunks
6. **Embed** — OpenRouter embeddings or local hash vectors
7. **Architecture** — RAG retrieve + LLM refine, or heuristic JSON
8. **Visualize** — React Three Fiber cinematic scene

Worker modes:
- `WORKER_EAGER=true` — in-process goroutine (local default)
- `WORKER_EAGER=false` + Redis — `hover -mode worker` / `-mode all`
