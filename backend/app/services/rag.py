"""LangChain RAG helpers — OpenRouter chat + embeddings, with offline fallback."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import get_settings


def _hash_embed(text: str, dim: int) -> list[float]:
    """Local fake embedding when no OpenRouter key is set."""
    vec = [0.0] * dim
    tokens = text.lower().split() or ["empty"]
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(0, min(len(digest), dim // 4 * 4), 4):
            idx = struct.unpack_from(">I", digest, i)[0] % dim
            vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def get_chat_llm() -> ChatOpenAI | None:
    settings = get_settings()
    if not settings.llm_ready:
        return None
    return ChatOpenAI(
        model=settings.openrouter_chat_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.2,
        default_headers={
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_app_title,
        },
    )


def get_embeddings() -> OpenAIEmbeddings | None:
    settings = get_settings()
    if not settings.llm_ready:
        return None
    return OpenAIEmbeddings(
        model=settings.openrouter_embedding_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_app_title,
        },
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    if not texts:
        return []
    emb = get_embeddings()
    if emb is None:
        return [_hash_embed(t, settings.embedding_dim) for t in texts]
    # LangChain embeds in batches internally
    return emb.embed_documents(texts)


def retrieve_docs(
    query: str,
    chunk_rows: list[dict[str, Any]],
    limit: int = 12,
) -> list[Document]:
    """Simple in-memory RAG retrieve over stored chunk embeddings."""
    if not chunk_rows:
        return []
    q_vecs = embed_texts([query])
    q = q_vecs[0]
    scored: list[tuple[float, dict]] = []
    for row in chunk_rows:
        vec = row.get("embedding") or []
        if isinstance(vec, str):
            vec = json.loads(vec)
        scored.append((cosine(q, vec), row))
    scored.sort(key=lambda x: x[0], reverse=True)
    docs: list[Document] = []
    for score, row in scored[:limit]:
        docs.append(
            Document(
                page_content=row["content"][:1200],
                metadata={
                    "path": row["file_path"],
                    "symbol": row.get("symbol_name", ""),
                    "score": score,
                },
            )
        )
    return docs


def extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


ARCHITECTURE_HINT = """
Return ONLY valid JSON with keys:
project_name, summary, layers, components, flows, entrypoints, data_stores.
layers: [{id, label, role}]
components: [{id, name, layer_id, kind, files, description}]
flows: [{id, label, steps: [{from, to, via, data}]}]
"""


def refine_architecture_with_langchain(
    project_name: str,
    heuristic: dict,
    docs: list[Document],
) -> dict | None:
    """Use LangChain ChatOpenAI (OpenRouter) to refine architecture JSON."""
    llm = get_chat_llm()
    if llm is None:
        return None

    context = "\n\n".join(
        f"FILE: {d.metadata.get('path')} ({d.metadata.get('symbol')})\n{d.page_content}"
        for d in docs[:10]
    )
    draft = json.dumps(heuristic)[:8000]
    prompt = f"""You are an expert software architect.
Refine this architecture JSON for a 3D visualization. Keep component ids stable when possible.
{ARCHITECTURE_HINT}

PROJECT: {project_name}

HEURISTIC DRAFT:
{draft}

RETRIEVED CODE:
{context[:12000]}
"""
    msg = llm.invoke(
        [
            SystemMessage(content="You output only valid JSON."),
            HumanMessage(content=prompt),
        ]
    )
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    data = extract_json(content)
    if not data or "components" not in data or "layers" not in data:
        return None
    data.setdefault("project_name", project_name)
    data.setdefault("flows", heuristic.get("flows", []))
    data.setdefault("entrypoints", heuristic.get("entrypoints", []))
    data.setdefault("data_stores", heuristic.get("data_stores", []))
    return data
