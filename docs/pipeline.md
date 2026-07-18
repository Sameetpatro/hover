## Hover pipeline (FastAPI + LangChain)

1. **Upload** — ZIP stored on disk or MinIO/S3  
2. **Extract** — safe unzip  
3. **Detect / analyze** — language, roles, imports, symbols, graph  
4. **Chunk** — symbol-aware pieces  
5. **Embed** — LangChain `OpenAIEmbeddings` via OpenRouter (or local hash)  
6. **RAG** — retrieve top chunks, LangChain `ChatOpenAI` refines Architecture JSON  
7. **Visualize** — React + Three.js  

Jobs: eager background thread (local) or Redis worker (`python -m app.worker`).
