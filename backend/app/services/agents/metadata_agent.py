"""Metadata Agent — extracts tech stack, system design, and structural metadata.

Produces supplementary data displayed in the System Design panel:
- Technology stack summary with categories
- Architecture pattern description
- Database schema inference
- Design patterns used
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.rag import extract_json, get_chat_llm

logger = logging.getLogger(__name__)

METADATA_SYSTEM = """You are the Metadata Agent — an expert at extracting structural metadata
from codebases. You analyze the project to produce a comprehensive metadata report.

Return ONLY valid JSON:
{
  "tech_stack": [
    {"name": "Python 3.11", "category": "language", "icon": "python"},
    {"name": "FastAPI", "category": "framework", "icon": "fastapi"},
    {"name": "PostgreSQL", "category": "database", "icon": "postgresql"},
    {"name": "Redis", "category": "cache", "icon": "redis"},
    {"name": "Docker", "category": "devops", "icon": "docker"},
    ...
  ],
  "system_design": "A monolithic REST API built with FastAPI...",
  "architecture_layers": [
    {"name": "Presentation", "description": "React frontend with TypeScript"},
    {"name": "API Gateway", "description": "FastAPI routes with input validation"},
    {"name": "Business Logic", "description": "Service layer with domain logic"},
    {"name": "Data Access", "description": "SQLAlchemy ORM with PostgreSQL"}
  ],
  "patterns": [
    {"name": "Repository Pattern", "description": "Data access abstracted behind repository classes"},
    {"name": "Cache-Aside", "description": "Redis used for caching with fallback to DB"},
    ...
  ],
  "db_schema": [
    {"table": "students", "columns": ["id", "name", "email", "grade"], "relations": ["courses"]},
    ...
  ]
}"""

METADATA_PROMPT = """Extract comprehensive metadata for this project.

PROJECT PROFILE:
{profile}

FILE LISTING:
{files}

CODE SAMPLES (models, config, schemas):
{code_samples}

DEPENDENCY FILES:
{dependencies}

Produce the metadata JSON. Be specific about versions, patterns, and schema."""


def run_metadata_agent(
    profile: dict[str, Any],
    file_listing: str,
    code_samples: str,
    dependencies: str,
) -> dict[str, Any]:
    """Extract project metadata.

    Falls back to profile-based metadata if no LLM available.
    """
    llm = get_chat_llm()
    if llm is None:
        logger.info("Metadata agent: no LLM, using heuristic metadata")
        return _heuristic_metadata(profile)

    prompt = METADATA_PROMPT.format(
        profile=json.dumps(profile, indent=2)[:3000],
        files=file_listing[:2000],
        code_samples=code_samples[:5000],
        dependencies=dependencies[:3000],
    )

    try:
        response = llm.invoke([
            SystemMessage(content=METADATA_SYSTEM),
            HumanMessage(content=prompt),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)
        data = extract_json(content)
        if data and "tech_stack" in data:
            return data
        logger.warning("Metadata agent: invalid JSON, falling back")
    except Exception as exc:
        logger.exception("Metadata agent failed: %s", exc)

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
        "system_design": profile.get("description", ""),
        "architecture_layers": [],
        "patterns": [],
        "db_schema": [],
    }
