"""Build Architecture JSON from files/graph, optionally refined by LangChain RAG."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.db import CodeChunk, Project, ProjectFile, Symbol
from app.services.rag import refine_architecture_with_langchain, retrieve_docs


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


def heuristic_architecture(
    project: Project,
    files: list[ProjectFile],
    symbols: list[Symbol],
    edges: list[dict],
) -> dict[str, Any]:
    layers = [
        {"id": "client", "label": "Client", "role": "entry"},
        {"id": "api", "label": "API", "role": "gateway"},
        {"id": "services", "label": "Services", "role": "logic"},
        {"id": "data", "label": "Data", "role": "store"},
    ]

    buckets: dict[str, list[ProjectFile]] = defaultdict(list)
    for f in files:
        if f.language in {"unknown", "markdown", "json", "yaml", "toml", "css", "scss"}:
            continue
        top = Path(f.path).parts[0] if Path(f.path).parts else "root"
        key = f"{_role_to_layer(f.role)}::{top}::{f.role or 'logic'}"
        buckets[key].append(f)

    components = []
    file_to_comp: dict[str, str] = {}
    for key, group in buckets.items():
        layer_id, top, role = key.split("::")
        comp_id = f"c_{uuid.uuid4().hex[:10]}"
        name = top
        if role == "api":
            name = f"{top} API"
        elif role == "ui":
            name = f"{top} UI"
        elif role == "db":
            name = f"{top} Models"
        elif role == "worker":
            name = f"{top} Workers"
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
            file_to_comp[g.path] = comp_id

    ui = [c for c in components if c["kind"] == "ui"]
    api = [c for c in components if c["kind"] == "controller"]
    svc = [c for c in components if c["kind"] == "service"]
    data = [c for c in components if c["kind"] == "model"]
    worker = [c for c in components if c["kind"] == "worker"]

    flows = []
    if ui and api:
        steps = [
            {
                "from": ui[0]["id"],
                "to": api[0]["id"],
                "via": "HTTP",
                "data": "HTTP Request / JSON body",
                "description": (
                    f"User action in {ui[0]['name']} triggers an HTTP call into "
                    f"{api[0]['name']} (controllers/routes)."
                ),
            }
        ]
        if svc:
            steps.append(
                {
                    "from": api[0]["id"],
                    "to": svc[0]["id"],
                    "via": "call",
                    "data": "Domain command / DTO",
                    "description": (
                        f"{api[0]['name']} validates the request and calls "
                        f"{svc[0]['name']} for business logic."
                    ),
                }
            )
            if data:
                steps.append(
                    {
                        "from": svc[0]["id"],
                        "to": data[0]["id"],
                        "via": "db",
                        "data": "Entity / row to persist",
                        "description": (
                            f"{svc[0]['name']} writes or updates records through "
                            f"{data[0]['name']} (models / repository)."
                        ),
                    }
                )
        elif data:
            steps.append(
                {
                    "from": api[0]["id"],
                    "to": data[0]["id"],
                    "via": "db",
                    "data": "Query / persist",
                    "description": (
                        f"{api[0]['name']} talks directly to {data[0]['name']} "
                        "for reads or writes."
                    ),
                }
            )
        flows.append(
            {
                "id": f"flow_{uuid.uuid4().hex[:8]}",
                "label": "Client request path",
                "description": (
                    "End-to-end path of a typical user request: UI → API → "
                    "services/data, showing what payload moves at each hop."
                ),
                "steps": steps,
            }
        )

    if api and worker:
        steps = [
            {
                "from": api[0]["id"],
                "to": worker[0]["id"],
                "via": "queue",
                "data": "Job payload / task id",
                "description": (
                    f"{api[0]['name']} enqueues async work for {worker[0]['name']} "
                    "(background processing)."
                ),
            }
        ]
        if data:
            steps.append(
                {
                    "from": worker[0]["id"],
                    "to": data[0]["id"],
                    "via": "db",
                    "data": "Processed result / status",
                    "description": (
                        f"{worker[0]['name']} finishes the job and updates "
                        f"{data[0]['name']}."
                    ),
                }
            )
        flows.append(
            {
                "id": f"flow_{uuid.uuid4().hex[:8]}",
                "label": "Async job path",
                "description": (
                    "How work leaves the request thread: API pushes a job, "
                    "a worker consumes it, then optionally persists results."
                ),
                "steps": steps,
            }
        )

    if edges and len(components) >= 2:
        pairs: Counter[tuple[str, str]] = Counter()
        for e in edges[:40]:
            a = file_to_comp.get(e.get("source", ""))
            b = file_to_comp.get(e.get("target", ""))
            if a and b and a != b:
                pairs[(a, b)] += 1
        if pairs:
            (a, b), _ = pairs.most_common(1)[0]
            a_name = next((c["name"] for c in components if c["id"] == a), a)
            b_name = next((c["name"] for c in components if c["id"] == b), b)
            flows.append(
                {
                    "id": f"flow_{uuid.uuid4().hex[:8]}",
                    "label": "Module dependency flow",
                    "description": (
                        f"Strongest import link in the codebase: {a_name} depends on {b_name}."
                    ),
                    "steps": [
                        {
                            "from": a,
                            "to": b,
                            "via": "import",
                            "data": "Module / symbol reference",
                            "description": (
                                f"Code in {a_name} imports symbols from {b_name} "
                                "(compile-time / static dependency)."
                            ),
                        }
                    ],
                }
            )

    if not flows and len(components) >= 2:
        flows.append(
            {
                "id": f"flow_{uuid.uuid4().hex[:8]}",
                "label": "Primary path",
                "description": "Fallback path connecting the two largest components.",
                "steps": [
                    {
                        "from": components[0]["id"],
                        "to": components[1]["id"],
                        "via": "call",
                        "data": "Internal data",
                        "description": (
                            f"{components[0]['name']} interacts with {components[1]['name']}."
                        ),
                    }
                ],
            }
        )

    langs = Counter(f.language for f in files if f.language and f.language != "unknown")
    top_langs = ", ".join(k for k, _ in langs.most_common(3)) or "mixed"
    entrypoints = [
        f.path
        for f in files
        if f.role == "entry"
        or Path(f.path).name in {"main.py", "app.py", "index.ts", "manage.py", "server.js", "main.go"}
    ][:10]
    for s in symbols:
        if s.kind == "endpoint":
            entrypoints.append(f"{s.file_path}:{s.name}")
        if len(entrypoints) > 12:
            break

    return {
        "project_name": project.name,
        "summary": (
            f"{project.name}: {len(files)} files across {top_langs}. "
            "Mapped into layered architecture from static analysis + LangChain RAG."
        ),
        "layers": layers,
        "components": components,
        "flows": flows,
        "entrypoints": entrypoints,
        "data_stores": [c["id"] for c in data],
    }


def generate_architecture(
    project: Project,
    files: list[ProjectFile],
    symbols: list[Symbol],
    edges: list[dict],
    chunks: list[CodeChunk],
) -> dict[str, Any]:
    base = heuristic_architecture(project, files, symbols, edges)
    rows = [
        {
            "content": c.content,
            "file_path": c.file_path,
            "symbol_name": c.symbol_name,
            "embedding": c.embedding_json,
        }
        for c in chunks
    ]
    docs = retrieve_docs(
        "system architecture data flow API client database workers services layers",
        rows,
        limit=12,
    )
    refined = refine_architecture_with_langchain(project.name, base, docs)
    return refined or base
