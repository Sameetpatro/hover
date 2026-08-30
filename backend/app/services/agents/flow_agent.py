"""Flow Tracer DeepAgent — traces complete request lifecycles per feature.

Powered by LangChain DeepAgents (deepagents.create_deep_agent).
Spawns one dedicated Flow DeepAgent per endpoint/feature:
  User → Server → API handler → Middleware → Service → Cache → Database → Response
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage

from app.services.rag import extract_json, get_chat_llm
from app.services.agents.tools import FLOW_TOOLS

logger = logging.getLogger(__name__)

FLOW_SYSTEM = """You are the Flow Tracer DeepAgent — an expert AI agent that traces the end-to-end execution flow of an endpoint or feature.

Given a feature, you trace the exact sequence of components involved:
User -> Web Server / Router -> Handler -> Middleware / Auth -> Business Service -> Cache -> Database -> Response.

You have access to tools for tracing function calls, following imports, inspecting DB schemas, and reading configs.

You MUST return ONLY valid JSON with this exact schema:
{
  "feature_id": "feat_0",
  "nodes": [
    {"id": "user", "type": "user", "label": "Client / User"},
    {"id": "server", "type": "server", "label": "FastAPI Server"},
    {"id": "api_handler", "type": "api", "label": "GET /api/students/:id"},
    {"id": "redis_cache", "type": "cache", "label": "Redis Cache"},
    {"id": "postgres_db", "type": "database", "label": "PostgreSQL"}
  ],
  "edges": [
    {"from": "user", "to": "server", "label": "HTTP GET", "data": "student_id in URL path"},
    {"from": "server", "to": "api_handler", "label": "Route Match", "data": "Dispatched to handler"},
    {"from": "api_handler", "to": "redis_cache", "label": "Cache Lookup", "data": "Key: student:{id}"},
    {"from": "redis_cache", "to": "user", "label": "Cache HIT", "data": "200 OK (cached JSON)", "condition": "cache_hit"},
    {"from": "api_handler", "to": "postgres_db", "label": "SQL Query", "data": "SELECT * FROM students WHERE id = ?", "condition": "cache_miss"},
    {"from": "postgres_db", "to": "redis_cache", "label": "Cache Write", "data": "SET student:{id}"},
    {"from": "postgres_db", "to": "user", "label": "Response", "data": "200 OK (fresh JSON)"}
  ]
}

Node Types allowed: user, server, api, service, cache, database, queue, worker, external.
Node IDs must be unique strings.
Edges must connect existing node IDs with descriptive labels and realistic data descriptions."""

FLOW_PROMPT = """Trace the complete request flow for this feature:

FEATURE:
  ID: {feature_id}
  Name: {name}
  Method: {method}
  Path: {path}
  Entry file: {entry_file}
  Entry function: {entry_function}
  Description: {description}

PROJECT PROFILE:
  Tech stack: {tech_stack}
  Infra: {infra}

ENTRY CODE:
{entry_code}

RELATED CODE (import chain):
{related_code}

DEPENDENCY CODE (services / repositories):
{dependency_code}

Use your tools to inspect functions and follow imports. Return ONLY valid JSON."""


def run_flow_agent(
    feature: dict[str, Any],
    profile: dict[str, Any],
    entry_code: str,
    related_code: str,
    dependency_code: str,
) -> dict[str, Any]:
    """Run an individual Flow DeepAgent for a single feature."""
    llm = get_chat_llm()
    feature_id = feature.get("id", "feat_0")
    if llm is None:
        return _heuristic_flow(feature, profile)

    tech_stack = profile.get("tech_stack", {})
    infra = profile.get("infra_components", [])

    prompt = FLOW_PROMPT.format(
        feature_id=feature_id,
        name=feature.get("name", "Unknown"),
        method=feature.get("method", "GET"),
        path=feature.get("path", "/"),
        entry_file=feature.get("entry_file", ""),
        entry_function=feature.get("entry_function", ""),
        description=feature.get("description", ""),
        tech_stack=json.dumps(tech_stack)[:1200],
        infra=json.dumps(infra)[:800],
        entry_code=entry_code[:2500],
        related_code=related_code[:3000],
        dependency_code=dependency_code[:2000],
    )

    try:
        deep_agent = create_deep_agent(
            model=llm,
            tools=FLOW_TOOLS,
            system_prompt=FLOW_SYSTEM,
        )
        response = deep_agent.invoke({
            "messages": [HumanMessage(content=prompt)]
        })
        messages = response.get("messages", [])
        if messages:
            last_msg = messages[-1]
            content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
            data = extract_json(content)
            if data and "nodes" in data and "edges" in data:
                data["feature_id"] = feature_id
                return data
    except Exception as exc:
        logger.warning("Flow DeepAgent fallback for feature %s: %s", feature.get("name"), exc)

    return _heuristic_flow(feature, profile)


def run_flow_agent_batch(
    features: list[dict[str, Any]],
    profile: dict[str, Any],
    code_getter: Any,
) -> list[dict[str, Any]]:
    """Spawns Flow DeepAgents for each feature and aggregates results."""
    flows = []
    for feat in features:
        entry_code, related_code, dep_code = code_getter(feat)
        flow = run_flow_agent(feat, profile, entry_code, related_code, dep_code)
        flows.append(flow)
    return flows


def _heuristic_flow(
    feature: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    """Generate a realistic flow based on tech stack and feature metadata."""
    feat_id = feature.get("id", "feat_0")
    method = feature.get("method", "GET").upper()
    path = feature.get("path", "/")
    tech = profile.get("tech_stack", {})
    frameworks = tech.get("frameworks", [])
    databases = tech.get("databases", [])
    caches = tech.get("caches", [])

    server_label = "Web Server"
    if "fastapi" in frameworks:
        server_label = "FastAPI Server"
    elif "express" in frameworks:
        server_label = "Express Server"
    elif "django" in frameworks:
        server_label = "Django Server"
    elif "flask" in frameworks:
        server_label = "Flask Server"
    elif "nextjs" in frameworks:
        server_label = "Next.js App Router"

    db_label = databases[0].title() if databases else "Database"
    cache_label = caches[0].title() if caches else None

    api_node_id = f"api_{feat_id}"
    nodes = [
        {"id": "user", "type": "user", "label": "Client / User"},
        {"id": "server", "type": "server", "label": server_label},
        {"id": api_node_id, "type": "api", "label": f"{method} {path}"},
    ]
    edges = [
        {"from": "user", "to": "server", "label": f"HTTP {method}", "data": f"Request {path}"},
        {"from": "server", "to": api_node_id, "label": "Route Match", "data": "Dispatched to controller"},
    ]

    if cache_label and method == "GET":
        cache_id = "cache"
        nodes.append({"id": cache_id, "type": "cache", "label": f"{cache_label} Cache"})
        edges.append({"from": api_node_id, "to": cache_id, "label": "Cache Lookup", "data": f"key: {feat_id}"})
        edges.append({"from": cache_id, "to": "user", "label": "Cache HIT", "data": "200 OK (cached)", "condition": "cache_hit"})

    db_id = "database"
    nodes.append({"id": db_id, "type": "database", "label": db_label})

    if cache_label and method == "GET":
        edges.append({"from": api_node_id, "to": db_id, "label": "Query", "data": "SQL Query", "condition": "cache_miss"})
        edges.append({"from": db_id, "to": "cache", "label": "Cache Write", "data": "Store in cache"})
    else:
        edges.append({"from": api_node_id, "to": db_id, "label": "Database Operation", "data": "Execute query"})

    edges.append({"from": db_id, "to": "user", "label": "Response", "data": "200 OK (JSON)"})

    return {
        "feature_id": feat_id,
        "nodes": nodes,
        "edges": edges,
    }
