"""Scout Agent — black-box project analyzer.

Scans the project from the outside to identify:
- Technology stack (languages, frameworks, databases, caches, queues)
- Infrastructure components (Redis, PostgreSQL, MongoDB, S3, etc.)
- Architecture pattern (MVC, microservices, monolith, etc.)
- All entry points (API routes, CLI commands, event handlers)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.rag import extract_json, get_chat_llm
from app.services.agents.tools import (
    get_dependencies,
    list_files,
    read_file,
    search_code,
    get_routes,
)

logger = logging.getLogger(__name__)

SCOUT_SYSTEM = """You are the Scout Agent — an expert at rapidly profiling software projects.
You analyze a codebase from a black-box perspective: what does it do, what tech does it use,
how is it structured. You have access to tools to search code, read files, and inspect dependencies.

Your job is to produce a ProjectProfile JSON with these exact keys:
{
  "project_name": "string",
  "description": "one paragraph describing what this project does",
  "tech_stack": {
    "languages": ["python", "typescript", ...],
    "frameworks": ["fastapi", "react", ...],
    "databases": ["postgresql", "sqlite", ...],
    "caches": ["redis", ...],
    "queues": ["celery", "rabbitmq", ...],
    "tools": ["docker", "nginx", ...]
  },
  "architecture_pattern": "monolith | microservices | serverless | mvc | ...",
  "infra_components": [
    {"name": "PostgreSQL", "type": "database", "role": "Primary data store"},
    {"name": "Redis", "type": "cache", "role": "Session/data caching"},
    ...
  ],
  "entry_points": [
    {"type": "api", "path": "/api/students", "method": "GET", "file": "routes/students.py"},
    ...
  ]
}

Return ONLY valid JSON. No markdown, no explanation."""

SCOUT_PROMPT = """Analyze this project to produce a ProjectProfile.

Here is what I know so far:

PROJECT FILES:
{file_listing}

DEPENDENCY FILES:
{dependencies}

API ROUTES:
{routes}

CODE SAMPLES (from RAG search):
{code_samples}

Now produce the ProjectProfile JSON. Be thorough — identify every database, cache,
queue, and infrastructure component. List ALL entry points you can find."""


def run_scout_agent(
    file_listing: str,
    dependencies: str,
    routes: str,
    code_samples: str,
) -> dict[str, Any]:
    """Run the Scout Agent to profile the project.

    Falls back to a heuristic profile if no LLM is available.
    """
    llm = get_chat_llm()
    if llm is None:
        logger.info("Scout agent: no LLM, using heuristic profile")
        return _heuristic_profile(file_listing, dependencies, routes)

    prompt = SCOUT_PROMPT.format(
        file_listing=file_listing[:4000],
        dependencies=dependencies[:4000],
        routes=routes[:3000],
        code_samples=code_samples[:5000],
    )

    try:
        response = llm.invoke([
            SystemMessage(content=SCOUT_SYSTEM),
            HumanMessage(content=prompt),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)
        data = extract_json(content)
        if data and "tech_stack" in data:
            return data
        logger.warning("Scout agent: LLM returned invalid JSON, falling back")
    except Exception as exc:
        logger.exception("Scout agent LLM call failed: %s", exc)

    return _heuristic_profile(file_listing, dependencies, routes)


def _heuristic_profile(
    file_listing: str, dependencies: str, routes: str
) -> dict[str, Any]:
    """Build a basic profile from file extensions and dependency keywords."""
    listing_lower = file_listing.lower()
    deps_lower = dependencies.lower()

    languages = set()
    if ".py " in listing_lower or ".py\n" in listing_lower:
        languages.add("python")
    if ".ts " in listing_lower or ".tsx " in listing_lower:
        languages.add("typescript")
    if ".js " in listing_lower or ".jsx " in listing_lower:
        languages.add("javascript")
    if ".go " in listing_lower:
        languages.add("go")
    if ".java " in listing_lower:
        languages.add("java")
    if ".rs " in listing_lower:
        languages.add("rust")

    frameworks = set()
    for fw, kw in [
        ("fastapi", "fastapi"), ("django", "django"), ("flask", "flask"),
        ("express", "express"), ("react", "react"), ("vue", "vue"),
        ("angular", "@angular"), ("nextjs", "next"), ("spring", "spring"),
        ("gin", "gin-gonic"), ("rails", "rails"),
    ]:
        if kw in deps_lower:
            frameworks.add(fw)

    databases = set()
    for db, kw in [
        ("postgresql", "psycopg"), ("postgresql", "postgres"),
        ("sqlite", "sqlite"), ("mongodb", "mongo"),
        ("mysql", "mysql"), ("redis", "redis"),
    ]:
        if kw in deps_lower or kw in listing_lower:
            databases.add(db)

    caches: set[str] = set()
    if "redis" in deps_lower:
        caches.add("redis")
    if "memcache" in deps_lower:
        caches.add("memcached")

    queues: set[str] = set()
    if "celery" in deps_lower:
        queues.add("celery")
    if "rabbitmq" in deps_lower or "amqp" in deps_lower:
        queues.add("rabbitmq")
    if "kafka" in deps_lower:
        queues.add("kafka")

    # Parse entry points from routes string
    entry_points = []
    for line in routes.splitlines():
        line = line.strip()
        if line.startswith("route(") or line.startswith("path("):
            entry_points.append({"type": "api", "path": line, "method": "?", "file": "?"})

    return {
        "project_name": "Unknown Project",
        "description": "Project profile generated by heuristic analysis.",
        "tech_stack": {
            "languages": sorted(languages),
            "frameworks": sorted(frameworks),
            "databases": sorted(databases),
            "caches": sorted(caches),
            "queues": sorted(queues),
            "tools": [],
        },
        "architecture_pattern": "monolith",
        "infra_components": [],
        "entry_points": entry_points[:20],
    }
