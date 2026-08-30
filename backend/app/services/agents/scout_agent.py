"""Scout DeepAgent — black-box project analyzer.

Powered by LangChain DeepAgents (deepagents.create_deep_agent).
Scans the project using file, dependency, and search tools to identify:
- Technology stack (languages, frameworks, databases, caches, queues)
- Infrastructure components (Redis, PostgreSQL, MongoDB, S3, etc.)
- Architecture pattern (MVC, microservices, monolith, etc.)
- All entry points (API routes, CLI commands, event handlers)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage

from app.services.rag import extract_json, get_chat_llm
from app.services.agents.tools import SCOUT_TOOLS

logger = logging.getLogger(__name__)

SCOUT_SYSTEM = """You are the Scout DeepAgent — an expert AI agent that profiles software codebases.
You analyze a project thoroughly to determine:
1. What the project does (concise summary)
2. Exact tech stack: languages, frameworks, databases, caches, queues, build/devops tools
3. Architecture style (Monolith, Microservices, Layered MVC, Serverless, Event-Driven, Clean Architecture)
4. Infrastructure components and their exact roles
5. Discovered entry points (HTTP endpoints, CLI commands, queue consumers, background tasks)

You have access to tools to read files, search code, list directories, and inspect configuration manifests.

Return ONLY a valid JSON object matching this structure:
{
  "project_name": "string",
  "description": "one paragraph describing what this project does",
  "tech_stack": {
    "languages": ["python", "typescript", ...],
    "frameworks": ["fastapi", "react", ...],
    "databases": ["postgresql", "sqlite", ...],
    "caches": ["redis", ...],
    "queues": ["celery", "rabbitmq", ...],
    "tools": ["docker", "nginx", "vite", ...]
  },
  "architecture_pattern": "monolith | microservices | layered | serverless | event-driven | ...",
  "infra_components": [
    {"name": "PostgreSQL", "type": "database", "role": "Primary relational database"},
    {"name": "Redis", "type": "cache", "role": "Session and cache store"}
  ],
  "entry_points": [
    {"type": "api", "path": "/api/users", "method": "GET", "file": "app/routes/users.py"}
  ]
}

Ensure the output is ONLY raw valid JSON (no markdown formatting, no code fences, no conversational text)."""

SCOUT_PROMPT = """Analyze this project and generate the complete ProjectProfile JSON.

Context provided:
PROJECT FILES:
{file_listing}

DEPENDENCIES:
{dependencies}

API ROUTES:
{routes}

CODE SAMPLES:
{code_samples}

Use your tools to explore any additional files if needed. Return ONLY valid JSON."""


def run_scout_agent(
    file_listing: str,
    dependencies: str,
    routes: str,
    code_samples: str,
) -> dict[str, Any]:
    """Run the Scout DeepAgent to profile the project."""
    llm = get_chat_llm()
    if llm is None:
        logger.info("Scout DeepAgent: no LLM available, running heuristic profiling")
        return _heuristic_profile(file_listing, dependencies, routes)

    prompt = SCOUT_PROMPT.format(
        file_listing=file_listing[:3500],
        dependencies=dependencies[:3500],
        routes=routes[:2500],
        code_samples=code_samples[:4000],
    )

    try:
        deep_agent = create_deep_agent(
            model=llm,
            tools=SCOUT_TOOLS,
            system_prompt=SCOUT_SYSTEM,
        )
        response = deep_agent.invoke({
            "messages": [HumanMessage(content=prompt)]
        })
        messages = response.get("messages", [])
        if messages:
            last_msg = messages[-1]
            content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
            data = extract_json(content)
            if data and ("tech_stack" in data or "architecture_pattern" in data):
                return data
            logger.warning("Scout DeepAgent: JSON parse incomplete, attempting fallback extraction")
    except Exception as exc:
        logger.exception("Scout DeepAgent execution encountered error: %s", exc)

    return _heuristic_profile(file_listing, dependencies, routes)


def _heuristic_profile(
    file_listing: str, dependencies: str, routes: str
) -> dict[str, Any]:
    """Build a reliable profile using deterministic heuristics."""
    listing_lower = file_listing.lower()
    deps_lower = dependencies.lower()

    languages = set()
    if any(ext in listing_lower for ext in [".py ", ".py\n", ".py:"]):
        languages.add("python")
    if any(ext in listing_lower for ext in [".ts ", ".tsx ", ".ts\n", ".tsx\n"]):
        languages.add("typescript")
    if any(ext in listing_lower for ext in [".js ", ".jsx ", ".js\n", ".jsx\n"]):
        languages.add("javascript")
    if ".go " in listing_lower or ".go\n" in listing_lower:
        languages.add("go")
    if ".java " in listing_lower or ".java\n" in listing_lower:
        languages.add("java")
    if ".rs " in listing_lower or ".rs\n" in listing_lower:
        languages.add("rust")

    frameworks = set()
    for fw, kw in [
        ("fastapi", "fastapi"), ("django", "django"), ("flask", "flask"),
        ("express", "express"), ("react", "react"), ("vue", "vue"),
        ("angular", "@angular"), ("nextjs", "next"), ("spring", "spring"),
        ("gin", "gin-gonic"), ("rails", "rails"), ("nest", "nestjs"),
    ]:
        if kw in deps_lower or kw in listing_lower:
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
    if "redis" in deps_lower or "redis" in listing_lower:
        caches.add("redis")
    if "memcache" in deps_lower or "memcached" in listing_lower:
        caches.add("memcached")

    queues: set[str] = set()
    if "celery" in deps_lower:
        queues.add("celery")
    if "rabbitmq" in deps_lower or "amqp" in deps_lower:
        queues.add("rabbitmq")
    if "kafka" in deps_lower:
        queues.add("kafka")

    infra = []
    for db in databases:
        infra.append({"name": db.title(), "type": "database", "role": f"Primary {db} store"})
    for cache in caches:
        infra.append({"name": cache.title(), "type": "cache", "role": f"{cache.title()} caching layer"})
    for q in queues:
        infra.append({"name": q.title(), "type": "queue", "role": f"{q.title()} async queue"})

    entry_points = []
    for line in routes.splitlines():
        line = line.strip()
        if line and any(m in line for m in ["GET", "POST", "PUT", "DELETE", "PATCH", "/"]):
            parts = line.split()
            path = parts[0] if parts else line
            method = parts[1] if len(parts) > 1 else "GET"
            entry_points.append({"type": "api", "path": path, "method": method, "file": ""})

    return {
        "project_name": "Analyzed Codebase",
        "description": "Codebase analyzed via Hover Scout DeepAgent.",
        "tech_stack": {
            "languages": sorted(languages) if languages else ["unknown"],
            "frameworks": sorted(frameworks),
            "databases": sorted(databases),
            "caches": sorted(caches),
            "queues": sorted(queues),
            "tools": ["docker"] if "docker" in deps_lower or "docker" in listing_lower else [],
        },
        "architecture_pattern": "monolith" if "microservices" not in listing_lower else "microservices",
        "infra_components": infra,
        "entry_points": entry_points[:25],
    }
