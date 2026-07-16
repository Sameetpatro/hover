"""Architecture JSON generation via RAG + heuristic fallback."""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from django.conf import settings

from indexing.embeddings import cosine_similarity, embed_texts


ARCHITECTURE_SCHEMA_HINT = """
Return ONLY valid JSON matching:
{
  "project_name": string,
  "summary": string,
  "layers": [{"id": string, "label": string, "role": "entry"|"gateway"|"logic"|"store"|"other"}],
  "components": [{"id": string, "name": string, "layer_id": string, "kind": "controller"|"service"|"model"|"worker"|"ui"|"config"|"entry", "files": [string], "description": string}],
  "flows": [{"id": string, "label": string, "steps": [{"from": string, "to": string, "via": "HTTP"|"queue"|"db"|"import"|"call", "data": string}]}],
  "entrypoints": [string],
  "data_stores": [string]
}
"""


def retrieve_chunks(project_id, query: str, limit: int = 12) -> list[dict]:
    from indexing.models import ChunkEmbedding, CodeChunk

    q_vec = embed_texts([query])[0]
    scored: list[tuple[float, CodeChunk]] = []
    for emb in ChunkEmbedding.objects.filter(project_id=project_id).select_related("chunk"):
        if not emb.embedding:
            continue
        score = cosine_similarity(q_vec, emb.embedding)
        scored.append((score, emb.chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, chunk in scored[:limit]:
        results.append(
            {
                "score": score,
                "path": chunk.file.path,
                "symbol": chunk.symbol_name,
                "content": chunk.content[:1200],
                "language": chunk.language,
            }
        )
    return results


def _role_to_layer(role: str) -> str:
    return {
        "ui": "client",
        "entry": "client",
        "api": "api",
        "logic": "services",
        "worker": "services",
        "db": "data",
        "config": "services",
    }.get(role, "services")


def _role_to_kind(role: str) -> str:
    return {
        "ui": "ui",
        "entry": "entry",
        "api": "controller",
        "logic": "service",
        "worker": "worker",
        "db": "model",
        "config": "config",
    }.get(role, "service")


def heuristic_architecture(project) -> dict[str, Any]:
    from analysis.models import DependencyEdge, DependencyNode, Symbol
    from projects.models import ProjectFile

    files = list(ProjectFile.objects.filter(project=project))
    nodes = list(DependencyNode.objects.filter(project=project))
    edges = list(
        DependencyEdge.objects.filter(project=project).select_related("source", "target")
    )
    symbols = list(Symbol.objects.filter(project=project).select_related("file"))

    layers = [
        {"id": "client", "label": "Client", "role": "entry"},
        {"id": "api", "label": "API", "role": "gateway"},
        {"id": "services", "label": "Services", "role": "logic"},
        {"id": "data", "label": "Data", "role": "store"},
    ]

    # Group files into components by top-level directory + role
    buckets: dict[str, list] = defaultdict(list)
    for f in files:
        if f.language in {"unknown", "markdown", "json", "yaml", "toml", "css", "scss"}:
            continue
        top = Path(f.path).parts[0] if Path(f.path).parts else "root"
        key = f"{_role_to_layer(f.role)}::{top}::{f.role or 'logic'}"
        buckets[key].append(f)

    components = []
    file_to_component: dict[str, str] = {}
    for key, group in buckets.items():
        layer_id, top, role = key.split("::")
        comp_id = f"c_{uuid.uuid4().hex[:10]}"
        name = f"{top}/{role}" if role else top
        # Prefer a meaningful name from dominant folder
        name = Path(group[0].path).parts[0] if len(Path(group[0].path).parts) > 1 else group[0].path
        if role == "api":
            name = f"{name} API"
        elif role == "ui":
            name = f"{name} UI"
        elif role == "db":
            name = f"{name} Models"
        elif role == "worker":
            name = f"{name} Workers"
        components.append(
            {
                "id": comp_id,
                "name": name[:64],
                "layer_id": layer_id,
                "kind": _role_to_kind(role),
                "files": [g.path for g in group[:40]],
                "description": f"{len(group)} files · role={role}",
            }
        )
        for g in group:
            file_to_component[g.path] = comp_id

    # Ensure at least some components from nodes
    if not components and nodes:
        for n in nodes[:20]:
            role = (n.metadata or {}).get("role", "logic")
            comp_id = f"c_{uuid.uuid4().hex[:10]}"
            components.append(
                {
                    "id": comp_id,
                    "name": n.label,
                    "layer_id": _role_to_layer(role),
                    "kind": _role_to_kind(role),
                    "files": [n.key],
                    "description": role,
                }
            )
            file_to_component[n.key] = comp_id

    # Build flows from edges and endpoints
    flows = []
    endpoints = [s for s in symbols if s.kind == "endpoint"]
    ui_comps = [c for c in components if c["kind"] == "ui"]
    api_comps = [c for c in components if c["kind"] == "controller"]
    svc_comps = [c for c in components if c["kind"] == "service"]
    data_comps = [c for c in components if c["kind"] == "model"]
    worker_comps = [c for c in components if c["kind"] == "worker"]

    if ui_comps and api_comps:
        steps = [
            {
                "from": ui_comps[0]["id"],
                "to": api_comps[0]["id"],
                "via": "HTTP",
                "data": "Request",
            }
        ]
        if svc_comps:
            steps.append(
                {
                    "from": api_comps[0]["id"],
                    "to": svc_comps[0]["id"],
                    "via": "call",
                    "data": "Domain call",
                }
            )
            if data_comps:
                steps.append(
                    {
                        "from": svc_comps[0]["id"],
                        "to": data_comps[0]["id"],
                        "via": "db",
                        "data": "Persist",
                    }
                )
        elif data_comps:
            steps.append(
                {
                    "from": api_comps[0]["id"],
                    "to": data_comps[0]["id"],
                    "via": "db",
                    "data": "Query",
                }
            )
        flows.append(
            {
                "id": f"flow_{uuid.uuid4().hex[:8]}",
                "label": "Client request path",
                "steps": steps,
            }
        )

    if api_comps and worker_comps:
        flows.append(
            {
                "id": f"flow_{uuid.uuid4().hex[:8]}",
                "label": "Async job path",
                "steps": [
                    {
                        "from": api_comps[0]["id"],
                        "to": worker_comps[0]["id"],
                        "via": "queue",
                        "data": "Job",
                    }
                ]
                + (
                    [
                        {
                            "from": worker_comps[0]["id"],
                            "to": data_comps[0]["id"],
                            "via": "db",
                            "data": "Write",
                        }
                    ]
                    if data_comps
                    else []
                ),
            }
        )

    # Import-derived secondary flow
    if edges and len(components) >= 2:
        step_pairs = []
        for e in edges[:30]:
            src = file_to_component.get(e.source.key)
            tgt = file_to_component.get(e.target.key)
            if src and tgt and src != tgt:
                step_pairs.append((src, tgt))
        # pick most common cross-component edge chain
        if step_pairs:
            counter = Counter(step_pairs)
            (a, b), _ = counter.most_common(1)[0]
            flows.append(
                {
                    "id": f"flow_{uuid.uuid4().hex[:8]}",
                    "label": "Module dependency flow",
                    "steps": [{"from": a, "to": b, "via": "import", "data": "Module"}],
                }
            )

    if not flows and len(components) >= 2:
        flows.append(
            {
                "id": f"flow_{uuid.uuid4().hex[:8]}",
                "label": "Primary path",
                "steps": [
                    {
                        "from": components[0]["id"],
                        "to": components[1]["id"],
                        "via": "call",
                        "data": "Data",
                    }
                ],
            }
        )

    langs = Counter(f.language for f in files if f.language and f.language != "unknown")
    top_langs = ", ".join(f"{k}" for k, _ in langs.most_common(3)) or "mixed"
    entrypoints = [
        f.path
        for f in files
        if f.role == "entry" or Path(f.path).name in {"main.py", "app.py", "index.ts", "manage.py", "server.js"}
    ][:10]
    if endpoints:
        entrypoints.extend(f"{s.file.path}:{s.name}" for s in endpoints[:8])

    data_stores = [c["id"] for c in data_comps] or [
        f.path for f in files if f.role == "db"
    ][:10]

    return {
        "project_name": project.name,
        "summary": f"{project.name}: {len(files)} files across {top_langs}. Mapped into layered architecture from static analysis.",
        "layers": layers,
        "components": components,
        "flows": flows,
        "entrypoints": entrypoints,
        "data_stores": data_stores,
    }


def _extract_json(text: str) -> dict | None:
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


def llm_architecture(project, retrieved: list[dict], base: dict) -> dict | None:
    if not settings.OPENAI_API_KEY:
        return None
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    context = "\n\n".join(
        f"FILE: {r['path']} ({r.get('symbol')})\n{r['content']}" for r in retrieved[:10]
    )
    prompt = f"""You are an expert software architect. Given a heuristic architecture draft and retrieved code snippets,
refine the architecture JSON for visualization. Keep component ids stable when possible.
{ARCHITECTURE_SCHEMA_HINT}

PROJECT: {project.name}

HEURISTIC DRAFT:
{json.dumps(base)[:8000]}

RETRIEVED CODE:
{context[:12000]}
"""
    resp = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": "You output only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    content = resp.choices[0].message.content or ""
    data = _extract_json(content)
    if not data or "components" not in data or "layers" not in data:
        return None
    data.setdefault("project_name", project.name)
    data.setdefault("flows", base.get("flows", []))
    data.setdefault("entrypoints", base.get("entrypoints", []))
    data.setdefault("data_stores", base.get("data_stores", []))
    return data


def generate_architecture(project) -> dict[str, Any]:
    base = heuristic_architecture(project)
    retrieved = retrieve_chunks(
        project.id,
        "system architecture data flow API client database workers services layers",
        limit=12,
    )
    refined = llm_architecture(project, retrieved, base)
    return refined or base
