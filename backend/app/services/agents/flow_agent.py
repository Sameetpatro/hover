"""Flow Tracer Agent — traces the complete request flow for each feature.

For every discovered feature, this agent traces the path:
  User → Server → API endpoint → Middleware → Service → Cache → Database → Response

This is the "deep" agent — it dynamically creates sub-tasks per feature,
following import chains and function calls to build accurate flow graphs.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.rag import extract_json, get_chat_llm

logger = logging.getLogger(__name__)

FLOW_SYSTEM = """You are the Flow Tracer Agent — an expert at tracing request flows through code.
Given a feature (an API endpoint or user action), you trace the COMPLETE path that a request
takes through the system, identifying every component it touches.

You MUST return ONLY valid JSON with this exact structure:
{
  "feature_id": "feat_0",
  "nodes": [
    {"id": "user", "type": "user", "label": "Client / User"},
    {"id": "server", "type": "server", "label": "FastAPI Server"},
    {"id": "api_get_student", "type": "api", "label": "GET /api/students/:id"},
    {"id": "redis_cache", "type": "cache", "label": "Redis Cache"},
    {"id": "postgres", "type": "database", "label": "PostgreSQL"}
  ],
  "edges": [
    {"from": "user", "to": "server", "label": "HTTP GET", "data": "student_id in URL path"},
    {"from": "server", "to": "api_get_student", "label": "Route match", "data": "Request routed to handler"},
    {"from": "api_get_student", "to": "redis_cache", "label": "Cache lookup", "data": "key: student:{id}"},
    {"from": "redis_cache", "to": "user", "label": "Cache HIT → Response", "data": "Student JSON", "condition": "cache_hit"},
    {"from": "api_get_student", "to": "postgres", "label": "SQL Query", "data": "SELECT * FROM students WHERE id = ?", "condition": "cache_miss"},
    {"from": "postgres", "to": "redis_cache", "label": "Cache write", "data": "SET student:{id} with TTL"},
    {"from": "postgres", "to": "user", "label": "Response", "data": "Student JSON (200 OK)"}
  ]
}

Rules for nodes:
- ALWAYS start with a "user" type node
- Use these types: user, server, api, service, cache, database, queue, worker, external
- Give each node a unique, descriptive ID
- Label should be human-readable (include the actual endpoint path for API nodes)

Rules for edges:
- "from" and "to" must reference valid node IDs
- "label" is the type of connection (HTTP GET, SQL Query, Cache lookup, etc.)
- "data" describes WHAT moves (the actual payload, query, key, etc.)
- "condition" is optional — use for branching (cache_hit, cache_miss, auth_success, auth_fail)
- Show the REAL data flow — what SQL queries, what cache keys, what payloads
- Include error/fallback paths if they exist

Return ONLY the JSON, no markdown."""


FLOW_PROMPT = """Trace the complete request flow for this feature:

FEATURE:
  Name: {name}
  Method: {method}
  Path: {path}
  Entry file: {entry_file}
  Entry function: {entry_function}
  Description: {description}

PROJECT PROFILE:
  Tech stack: {tech_stack}
  Infra components: {infra}

ENTRY POINT CODE:
{entry_code}

RELATED CODE (from import chain):
{related_code}

DEPENDENCY CODE (services/repositories called):
{dependency_code}

Trace the COMPLETE flow from User to Response. Include every component
the request touches: middleware, validators, services, caches, databases.
Show actual data (SQL queries, cache keys, payloads) — not generic placeholders."""


def run_flow_agent(
    feature: dict[str, Any],
    profile: dict[str, Any],
    entry_code: str,
    related_code: str,
    dependency_code: str,
) -> dict[str, Any]:
    """Trace the request flow for a single feature.

    Falls back to a generic flow if no LLM is available.
    """
    llm = get_chat_llm()
    if llm is None:
        logger.info("Flow agent: no LLM, using heuristic flow for %s", feature.get("name"))
        return _heuristic_flow(feature, profile)

    tech_stack = profile.get("tech_stack", {})
    infra = profile.get("infra_components", [])

    prompt = FLOW_PROMPT.format(
        name=feature.get("name", "?"),
        method=feature.get("method", "?"),
        path=feature.get("path", "?"),
        entry_file=feature.get("entry_file", "?"),
        entry_function=feature.get("entry_function", "?"),
        description=feature.get("description", ""),
        tech_stack=json.dumps(tech_stack)[:1500],
        infra=json.dumps(infra)[:1000],
        entry_code=entry_code[:3000],
        related_code=related_code[:4000],
        dependency_code=dependency_code[:3000],
    )

    try:
        response = llm.invoke([
            SystemMessage(content=FLOW_SYSTEM),
            HumanMessage(content=prompt),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)
        data = extract_json(content)
        if data and "nodes" in data and "edges" in data:
            data["feature_id"] = feature.get("id", "feat_0")
            return data
        logger.warning("Flow agent: invalid JSON for %s, falling back", feature.get("name"))
    except Exception as exc:
        logger.exception("Flow agent failed for %s: %s", feature.get("name"), exc)

    return _heuristic_flow(feature, profile)


def run_flow_agent_batch(
    features: list[dict[str, Any]],
    profile: dict[str, Any],
    code_getter: Any,  # callable(feature) -> (entry_code, related_code, dep_code)
) -> list[dict[str, Any]]:
    """Trace flows for all features. Runs sequentially (LLM calls)."""
    flows = []
    for feat in features:
        entry_code, related_code, dep_code = code_getter(feat)
        flow = run_flow_agent(feat, profile, entry_code, related_code, dep_code)
        flows.append(flow)
    return flows


def _heuristic_flow(
    feature: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    """Generate a generic flow based on the project profile."""
    tech = profile.get("tech_stack", {})
    frameworks = tech.get("frameworks", [])
    databases = tech.get("databases", [])
    caches = tech.get("caches", [])

    # Determine server label
    server_label = "Server"
    if "fastapi" in frameworks:
        server_label = "FastAPI Server"
    elif "express" in frameworks:
        server_label = "Express Server"
    elif "django" in frameworks:
        server_label = "Django Server"
    elif "flask" in frameworks:
        server_label = "Flask Server"
    elif "spring" in frameworks:
        server_label = "Spring Server"

    # Determine DB label
    db_label = databases[0].title() if databases else "Database"
    cache_label = caches[0].title() if caches else None

    method = feature.get("method", "GET")
    path = feature.get("path", "/")

    nodes = [
        {"id": "user", "type": "user", "label": "Client / User"},
        {"id": "server", "type": "server", "label": server_label},
        {"id": f"api_{feature.get('id', '0')}", "type": "api", "label": f"{method} {path}"},
    ]
    edges = [
        {"from": "user", "to": "server", "label": f"HTTP {method}", "data": "Request payload"},
        {"from": "server", "to": f"api_{feature.get('id', '0')}", "label": "Route match", "data": "Dispatched to handler"},
    ]

    api_id = f"api_{feature.get('id', '0')}"

    if cache_label:
        cache_id = "cache"
        nodes.append({"id": cache_id, "type": "cache", "label": f"{cache_label} Cache"})
        edges.append({"from": api_id, "to": cache_id, "label": "Cache lookup", "data": "Check cached data"})
        edges.append({"from": cache_id, "to": "user", "label": "Cache HIT", "data": "Cached response", "condition": "cache_hit"})

    db_id = "database"
    nodes.append({"id": db_id, "type": "database", "label": db_label})

    if cache_label:
        edges.append({"from": api_id, "to": db_id, "label": "Query", "data": "Database operation", "condition": "cache_miss"})
        edges.append({"from": db_id, "to": "cache", "label": "Cache write", "data": "Update cache"})
    else:
        edges.append({"from": api_id, "to": db_id, "label": "Query", "data": "Database operation"})

    edges.append({"from": db_id, "to": "user", "label": "Response", "data": "Result data"})

    return {
        "feature_id": feature.get("id", "feat_0"),
        "nodes": nodes,
        "edges": edges,
    }
