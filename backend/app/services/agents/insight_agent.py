"""Insight Generator Agent — produces rich hover content for flow edges.

For each step in each feature flow, generates human-readable explanations
including patterns detected, performance hints, and security observations.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.rag import extract_json, get_chat_llm

logger = logging.getLogger(__name__)

INSIGHT_SYSTEM = """You are the Insight Generator Agent — an expert at explaining code behavior
in human-readable terms. Given feature flows, you generate rich insights for each edge.

Return ONLY valid JSON — an array of insight objects, one per flow edge:
[
  {
    "feature_id": "feat_0",
    "from": "api_get_student",
    "to": "redis_cache",
    "insight": "Uses cache-aside pattern: checks Redis before hitting the database. Key format: student:{id} with 5-minute TTL.",
    "pattern": "Cache-Aside",
    "performance_note": "Sub-millisecond reads on cache hit, ~20ms on cache miss + DB query",
    "security_note": "No input validation on student ID — potential injection risk"
  },
  ...
]

Rules:
- One insight per edge in every feature flow
- "insight" is the main explanation shown on hover (2-3 sentences)
- "pattern" is the design pattern if applicable (or null)
- "performance_note" and "security_note" are optional observations
- Be specific, not generic — reference actual code details when possible"""

INSIGHT_PROMPT = """Generate insights for all edges in these feature flows:

FEATURES AND FLOWS:
{flows}

PROJECT PROFILE:
{profile}

RELEVANT CODE:
{code_samples}

Generate one insight per edge. Be specific about what happens at each step."""


def run_insight_agent(
    flows: list[dict[str, Any]],
    profile: dict[str, Any],
    code_samples: str,
) -> list[dict[str, Any]]:
    """Generate insights for all flow edges.

    Falls back to generic insights if no LLM available.
    """
    llm = get_chat_llm()
    if llm is None:
        logger.info("Insight agent: no LLM, using heuristic insights")
        return _heuristic_insights(flows)

    prompt = INSIGHT_PROMPT.format(
        flows=json.dumps(flows, indent=2)[:8000],
        profile=json.dumps(profile, indent=2)[:2000],
        code_samples=code_samples[:4000],
    )

    try:
        response = llm.invoke([
            SystemMessage(content=INSIGHT_SYSTEM),
            HumanMessage(content=prompt),
        ])
        content = response.content if isinstance(response.content, str) else str(response.content)

        # Parse JSON array
        content = content.strip()
        if content.startswith("```"):
            import re
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        data = None
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        if isinstance(data, list) and data:
            return data
        logger.warning("Insight agent: invalid JSON, falling back")
    except Exception as exc:
        logger.exception("Insight agent failed: %s", exc)

    return _heuristic_insights(flows)


def _heuristic_insights(flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate basic insights from edge labels and types."""
    insights = []
    for flow in flows:
        feature_id = flow.get("feature_id", "?")
        for edge in flow.get("edges", []):
            from_id = edge.get("from", "?")
            to_id = edge.get("to", "?")
            label = edge.get("label", "")
            data = edge.get("data", "")

            # Generate insight based on edge characteristics
            if "cache" in label.lower() or "cache" in to_id.lower():
                insight = f"Cache operation: {label}. {data}"
                pattern = "Cache-Aside"
            elif "sql" in label.lower() or "query" in label.lower() or "database" in to_id.lower():
                insight = f"Database operation: {label}. {data}"
                pattern = "Repository"
            elif "http" in label.lower() or "request" in label.lower():
                insight = f"Network call: {label}. {data}"
                pattern = None
            elif "queue" in label.lower() or "worker" in to_id.lower():
                insight = f"Async operation: {label}. {data}"
                pattern = "Message Queue"
            elif "route" in label.lower():
                insight = f"Request routing: {label}. {data}"
                pattern = "Router"
            else:
                insight = f"{label}: {data}"
                pattern = None

            insights.append({
                "feature_id": feature_id,
                "from": from_id,
                "to": to_id,
                "insight": insight,
                "pattern": pattern,
                "performance_note": None,
                "security_note": None,
            })
    return insights
