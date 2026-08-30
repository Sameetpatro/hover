"""Feature Discovery Agent — identifies individual user-facing features.

Reads API routes, controllers, and service files to discover features like:
- "Get Student" (GET /api/students/:id)
- "Create Order" (POST /api/orders)
- "User Login" (POST /auth/login)

Each feature gets a unique color for visualization.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.rag import extract_json, get_chat_llm

logger = logging.getLogger(__name__)

# Palette of distinct, vibrant colors for feature flows
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

FEATURE_SYSTEM = """You are the Feature Discovery Agent — an expert at identifying user-facing
features in a codebase. You analyze API routes, controllers, and services to discover
individual features that a user or client can interact with.

A "feature" is a discrete capability: GET /students/:id, POST /orders, user login, etc.

You MUST return ONLY valid JSON — an array of features:
[
  {
    "name": "Get Student",
    "description": "Retrieves a single student record by ID",
    "method": "GET",
    "path": "/api/students/:id",
    "entry_file": "routes/students.py",
    "entry_function": "get_student",
    "category": "students"
  },
  ...
]

Rules:
- Group CRUD operations as separate features (Get Student, Create Student, etc.)
- Include the HTTP method if it's an API endpoint
- Include non-HTTP features too (CLI commands, scheduled tasks, WebSocket handlers)
- Be thorough — find ALL features, not just the obvious ones
- Maximum 20 features (combine very similar ones if there are more)
- Return ONLY the JSON array, no markdown"""

FEATURE_PROMPT = """Discover all user-facing features in this project.

PROJECT PROFILE:
{profile}

API ROUTES & ENDPOINTS:
{routes}

CODE SAMPLES (controllers/routes/handlers):
{code_samples}

FILE STRUCTURE:
{files}

Find every distinct feature. Return the JSON array."""


def run_feature_agent(
    profile: dict[str, Any],
    routes: str,
    code_samples: str,
    file_listing: str,
) -> list[dict[str, Any]]:
    """Discover features in the project.

    Falls back to route-based heuristic if no LLM is available.
    """
    llm = get_chat_llm()
    if llm is None:
        logger.info("Feature agent: no LLM, using heuristic features")
        return _heuristic_features(profile, routes)

    import json

    prompt = FEATURE_PROMPT.format(
        profile=json.dumps(profile, indent=2)[:3000],
        routes=routes[:3000],
        code_samples=code_samples[:6000],
        files=file_listing[:2000],
    )

    try:
        response = llm.invoke([
            SystemMessage(content=FEATURE_SYSTEM),
            HumanMessage(content=prompt),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)

        # Try to parse as array
        content = content.strip()
        if content.startswith("```"):
            import re
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        data = None
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try extracting array
            import re
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        if isinstance(data, list) and data:
            # Assign colors
            for i, feat in enumerate(data):
                feat["color"] = FEATURE_COLORS[i % len(FEATURE_COLORS)]
                feat.setdefault("id", f"feat_{i}")
            return data[:20]

        logger.warning("Feature agent: LLM returned invalid data, falling back")
    except Exception as exc:
        logger.exception("Feature agent LLM call failed: %s", exc)

    return _heuristic_features(profile, routes)


def _heuristic_features(
    profile: dict[str, Any], routes: str
) -> list[dict[str, Any]]:
    """Build features from entry points in the profile."""
    features = []
    entry_points = profile.get("entry_points", [])

    for i, ep in enumerate(entry_points[:20]):
        method = ep.get("method", "?").upper()
        path = ep.get("path", "?")
        file_ = ep.get("file", "?")

        # Generate a name from the path
        parts = [p for p in path.split("/") if p and not p.startswith(":") and not p.startswith("{")]
        name_parts = parts[-2:] if len(parts) >= 2 else parts
        if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
            name = f"{method.title()} {' '.join(p.title() for p in name_parts)}"
        else:
            name = " ".join(p.title() for p in name_parts) or f"Feature {i + 1}"

        features.append({
            "id": f"feat_{i}",
            "name": name,
            "description": f"{method} {path}",
            "method": method,
            "path": path,
            "entry_file": file_,
            "entry_function": "",
            "category": name_parts[0] if name_parts else "general",
            "color": FEATURE_COLORS[i % len(FEATURE_COLORS)],
        })

    if not features:
        features.append({
            "id": "feat_0",
            "name": "Main Application",
            "description": "Primary application entry point",
            "method": "",
            "path": "/",
            "entry_file": "",
            "entry_function": "",
            "category": "general",
            "color": FEATURE_COLORS[0],
        })

    return features
