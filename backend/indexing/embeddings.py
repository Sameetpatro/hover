"""Embedding service with OpenAI-compatible API and local hash fallback."""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Iterable

from django.conf import settings


def _hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic local embedding when no API key is configured."""
    vec = [0.0] * dim
    tokens = text.lower().split()
    if not tokens:
        tokens = ["empty"]
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        for i in range(0, min(len(digest), dim // 4 * 4), 4):
            idx = struct.unpack_from(">I", digest, i)[0] % dim
            vec[idx] += 1.0
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_texts(texts: list[str]) -> list[list[float]]:
    dim = settings.EMBEDDING_DIM
    if not texts:
        return []
    if not settings.OPENAI_API_KEY:
        return [_hash_embed(t, dim) for t in texts]

    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    # Batch in groups of 64
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):
        batch = texts[i : i + 64]
        resp = client.embeddings.create(model=settings.OPENAI_EMBEDDING_MODEL, input=batch)
        ordered = sorted(resp.data, key=lambda d: d.index)
        out.extend([list(d.embedding) for d in ordered])
    return out


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list or len(a_list) != len(b_list):
        return 0.0
    dot = sum(x * y for x, y in zip(a_list, b_list))
    na = math.sqrt(sum(x * x for x in a_list)) or 1.0
    nb = math.sqrt(sum(y * y for y in b_list)) or 1.0
    return dot / (na * nb)
