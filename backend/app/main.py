"""Hover FastAPI app — Python + LangChain backend."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers.api import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Hover", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"service": "hover", "stack": "fastapi+langchain"}


@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/health/", methods=["GET", "HEAD"])
def health():
    """Render probes GET /health — keep this at the app root."""
    return Response(content='{"status":"ok"}', media_type="application/json", status_code=200)