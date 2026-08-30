"""Feature Discovery DeepAgent — discovers and catalogs user-facing features and endpoints.

Powered by LangChain DeepAgents (deepagents.create_deep_agent).
Analyzes routes, schemas, and controllers to discover features:
- Endpoints (REST, GraphQL, gRPC, WebSockets)
- User actions (Login, Register, Checkout, Search)
- Background jobs and worker tasks
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage

from app.services.rag import extract_json, get_chat_llm
from app.services.agents.tools import FEATURE_TOOLS

logger = logging.getLogger(__name__)

FEATURE_COLORS = [
    "#f472b6",  # pink
    "#60a5fa",  # blue
    "#34d399",  # emerald
    "#fbbf24",  # amber
    "#a78bfa",  # violet
    "#fb923c",  # orange
    "#2dd4bf",  # teal
    "#e879f9",  # fuchsia
    "#4ade80",  # green
    "#f87171",  # red
    "#38bdf8",  # sky
    "#facc15",  # yellow
]

FEATURE_SYSTEM = """You are the Feature Discovery DeepAgent — an expert AI agent that identifies all distinct features and API capabilities in a codebase.

A "feature" is a distinct user or client interaction point:
- API endpoints (e.g. GET /api/users, POST /api/auth/login, PUT /api/orders/:id)
- Asynchronous tasks / workers
- Core system workflows

You have access to tools for AST parsing, pattern finding, symbol resolution, and database schema discovery.

You MUST return ONLY a valid JSON array of feature objects:
[
  {
    "id": "feat_0",
    "name": "User Login",
    "description": "Authenticates user credentials and issues JWT token",
    "method": "POST",
    "path": "/api/auth/login",
    "entry_file": "app/routers/auth.py",
    "entry_function": "login",
    "category": "authentication"
  }
]

Guidelines:
- Return between 4 and 20 discrete features.
- Name each feature clearly (e.g., 'Get Student', 'Create Order', 'List Products').
- Populate method, path, entry_file, and entry_function whenever identifiable.
- Output raw JSON only."""

FEATURE_PROMPT = """Discover and catalog all functional features and endpoints in this project.

PROJECT PROFILE:
{profile}

DISCOVERED ROUTES / ENDPOINTS:
{routes}

CODE SAMPLES:
{code_samples}

FILE STRUCTURE:
{files}

Use your tools to inspect schemas and symbols if needed. Return ONLY the JSON array."""


def run_feature_agent(
    profile: dict[str, Any],
    routes: str,
    code_samples: str,
    file_listing: str,
) -> list[dict[str, Any]]:
    """Discover features in the project using Feature DeepAgent."""
    llm = get_chat_llm()
    if llm is None:
        logger.info("Feature DeepAgent: no LLM available, generating heuristic features")
        return _heuristic_features(profile, routes)

    prompt = FEATURE_PROMPT.format(
        profile=json.dumps(profile, indent=2)[:3000],
        routes=routes[:3000],
        code_samples=code_samples[:5000],
        files=file_listing[:2000],
    )

    try:
        deep_agent = create_deep_agent(
            model=llm,
            tools=FEATURE_TOOLS,
            system_prompt=FEATURE_SYSTEM,
        )
        response = deep_agent.invoke({
            "messages": [HumanMessage(content=prompt)]
        })
        messages = response.get("messages", [])
        if messages:
            last_msg = messages[-1]
            content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
            data = _parse_features_json(content)
            if data and isinstance(data, list) and len(data) > 0:
                for i, feat in enumerate(data):
                    feat["color"] = FEATURE_COLORS[i % len(FEATURE_COLORS)]
                    feat.setdefault("id", f"feat_{i}")
                return data[:20]
    except Exception as exc:
        logger.exception("Feature DeepAgent execution failed: %s", exc)

    return _heuristic_features(profile, routes)


def _parse_features_json(content: str) -> list[dict] | None:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return None


def _format_feature_name(method: str, path: str, file_path: str = "") -> tuple[str, str, str]:
    """Generates clean human-readable name, normalized path, and category."""
    file_stem = Path(file_path).stem.lower() if file_path else ""
    cat = file_stem if file_stem and file_stem not in ("main", "app", "routes", "views", "api", "__init__") else "general"

    # Build full route path with prefix if not present
    full_path = path
    if cat != "general" and not path.startswith(f"/api/{cat}") and not path.startswith(f"/{cat}"):
        if path == "/":
            full_path = f"/api/{cat}/"
        else:
            full_path = f"/api/{cat}{path if path.startswith('/') else '/' + path}"

    parts = [p.replace("{", "").replace("}", "").replace(":", "") for p in path.split("/") if p]
    if parts:
        clean_parts = [p.replace("_", " ").title() for p in parts]
        name = f"{method.upper()} {' '.join(clean_parts)}"
    elif cat != "general":
        name = f"{method.upper()} {cat.replace('_', ' ').title()}"
    else:
        name = f"{method.upper()} Root"

    return name, full_path, cat


def _heuristic_features(
    profile: dict[str, Any], routes: str
) -> list[dict[str, Any]]:
    """Build features from entry points, discovered routes text, and tool symbols."""
    features = []
    seen_routes = set()

    # 1. From profile entry points
    entry_points = profile.get("entry_points", [])
    for ep in entry_points:
        method = ep.get("method", "GET").upper()
        path = ep.get("path", "/")
        file_ = ep.get("file", "")
        name, full_path, cat = _format_feature_name(method, path, file_)
        key = f"{method}:{full_path}"
        if key in seen_routes:
            continue
        seen_routes.add(key)

        features.append({
            "id": f"feat_{len(features)}",
            "name": name,
            "description": f"{method} {full_path}",
            "method": method,
            "path": full_path,
            "entry_file": file_,
            "entry_function": ep.get("entry_function", ""),
            "category": cat,
            "color": FEATURE_COLORS[len(features) % len(FEATURE_COLORS)],
        })

    # 2. Parse from routes string if profile entry points missed some
    if routes and routes != "(no routes found)":
        for line in routes.splitlines():
            line = line.strip()
            if not line or line.startswith("==="):
                continue
            m = re.search(r"\b(GET|POST|PUT|DELETE|PATCH)\s+([/\w{}\-:_]+)", line, re.IGNORECASE)
            file_m = re.search(r"in\s+([^\s]+)", line)
            if m:
                method = m.group(1).upper()
                path = m.group(2)
                file_ = file_m.group(1) if file_m else ""
                name, full_path, cat = _format_feature_name(method, path, file_)
                key = f"{method}:{full_path}"
                if key not in seen_routes:
                    seen_routes.add(key)
                    features.append({
                        "id": f"feat_{len(features)}",
                        "name": name,
                        "description": f"{method} {full_path}",
                        "method": method,
                        "path": full_path,
                        "entry_file": file_,
                        "entry_function": "",
                        "category": cat,
                        "color": FEATURE_COLORS[len(features) % len(FEATURE_COLORS)],
                    })

    # 3. Fallback from tool symbols directly
    if not features:
        from app.services.agents.tools import _get
        symbols = _get("symbols")
        for s in symbols:
            if s.get("kind") == "endpoint":
                sig = s.get("signature", s.get("name", ""))
                m = re.search(r"(GET|POST|PUT|DELETE|PATCH)\s+([/\w{}\-:_]+)", sig, re.IGNORECASE)
                if m:
                    method = m.group(1).upper()
                    path = m.group(2)
                    file_ = s.get("file_path", "")
                    name, full_path, cat = _format_feature_name(method, path, file_)
                    key = f"{method}:{full_path}"
                    if key not in seen_routes:
                        seen_routes.add(key)
                        features.append({
                            "id": f"feat_{len(features)}",
                            "name": name,
                            "description": f"{method} {full_path}",
                            "method": method,
                            "path": full_path,
                            "entry_file": file_,
                            "entry_function": s.get("name", ""),
                            "category": cat,
                            "color": FEATURE_COLORS[len(features) % len(FEATURE_COLORS)],
                        })

    if not features:
        features.append({
            "id": "feat_0",
            "name": "Core Application Service",
            "description": "Primary service entry point",
            "method": "GET",
            "path": "/",
            "entry_file": "",
            "entry_function": "",
            "category": "core",
            "color": FEATURE_COLORS[0],
        })

    return features[:20]
