"""Metadata Agent — synthesizes tech stack, system design, and structural metadata.

Produces supplementary data displayed in the System Design panel:
- Technology stack summary with categorizations and icons
- Architecture pattern description and layer breakdowns
- Database schema inference
- Design patterns identified
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.rag import extract_json, get_chat_llm

logger = logging.getLogger(__name__)

METADATA_SYSTEM = """You are the Metadata Synthesizer Agent — an expert at extracting comprehensive structural metadata from software codebases.

Return ONLY valid JSON with this exact schema:
{
  "tech_stack": [
    {"name": "Python 3.11", "category": "language", "icon": "python"},
    {"name": "FastAPI", "category": "framework", "icon": "fastapi"},
    {"name": "PostgreSQL", "category": "database", "icon": "postgresql"},
    {"name": "Redis", "category": "cache", "icon": "redis"},
    {"name": "Docker", "category": "devops", "icon": "docker"}
  ],
  "system_design": "A high-performance modern service built with FastAPI and PostgreSQL...",
  "architecture_layers": [
    {"name": "Presentation", "description": "Frontend UI or API client consumers"},
    {"name": "API Layer", "description": "HTTP route handlers with validation"},
    {"name": "Business Logic", "description": "Domain services and workflow orchestrators"},
    {"name": "Persistence", "description": "Relational or document data stores"}
  ],
  "patterns": [
    {"name": "Repository Pattern", "description": "Abstracts data persistence operations"},
    {"name": "Cache-Aside", "description": "Redis caching layer with DB fallback"}
  ],
  "db_schema": [
    {"table": "users", "columns": ["id", "email", "hashed_password", "created_at"], "relations": ["orders"]}
  ]
}"""

METADATA_PROMPT = """Extract comprehensive system design and architecture metadata for this project.

PROJECT PROFILE:
{profile}

FILE LISTING:
{files}

CODE SAMPLES:
{code_samples}

DEPENDENCY MANIFESTS:
{dependencies}

Produce the metadata JSON."""


def run_metadata_agent(
    profile: dict[str, Any],
    file_listing: str,
    code_samples: str,
    dependencies: str,
) -> dict[str, Any]:
    """Extract project metadata and system design."""
    llm = get_chat_llm()
    if llm is None:
        return _heuristic_metadata(profile)

    prompt = METADATA_PROMPT.format(
        profile=json.dumps(profile, indent=2)[:3000],
        files=file_listing[:2000],
        code_samples=code_samples[:4000],
        dependencies=dependencies[:3000],
    )

    try:
        response = llm.invoke([
            SystemMessage(content=METADATA_SYSTEM),
            HumanMessage(content=prompt),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)
        data = extract_json(content)
        if data and ("tech_stack" in data or "system_design" in data):
            return data
    except Exception as exc:
        logger.warning("Metadata agent LLM fallback: %s", exc)

    return _heuristic_metadata(profile)


def _heuristic_metadata(profile: dict[str, Any]) -> dict[str, Any]:
    """Build metadata from the scout profile."""
    tech = profile.get("tech_stack", {})

    tech_stack = []
    for lang in tech.get("languages", []):
        tech_stack.append({"name": lang.title(), "category": "language", "icon": lang})
    for fw in tech.get("frameworks", []):
        tech_stack.append({"name": fw.title(), "category": "framework", "icon": fw})
    for db in tech.get("databases", []):
        tech_stack.append({"name": db.title(), "category": "database", "icon": db})
    for cache in tech.get("caches", []):
        tech_stack.append({"name": cache.title(), "category": "cache", "icon": cache})
    for q in tech.get("queues", []):
        tech_stack.append({"name": q.title(), "category": "queue", "icon": q})
    for t in tech.get("tools", []):
        tech_stack.append({"name": t.title(), "category": "devops", "icon": t})

    return {
        "tech_stack": tech_stack,
        "system_design": profile.get("description", "Analyzed software project architecture."),
        "architecture_layers": [
            {"name": "API & Ingress", "description": "Entry points and routing"},
            {"name": "Application Logic", "description": "Core business rules"},
            {"name": "Persistence", "description": "Database and storage"},
        ],
        "patterns": [
            {"name": "Layered Architecture", "description": "Clear separation between routing and business rules"},
        ],
        "db_schema": [],
    }
