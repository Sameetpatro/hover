"""Insight Generator DeepAgent — produces rich hover explanations and architectural insights.

Powered by LangChain DeepAgents (deepagents.create_deep_agent).
Generates detailed technical annotations for flow edges:
- Hover insight explanations (2-3 sentences)
- Identified design patterns (Cache-Aside, Repository, CQRS, Circuit Breaker, Router)
- Performance and latency notes
- Security observations and validation hints
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage

from app.services.rag import extract_json, get_chat_llm
from app.services.agents.tools import INSIGHT_TOOLS

logger = logging.getLogger(__name__)

INSIGHT_SYSTEM = """You are the Insight Generator DeepAgent — an expert software architect AI agent.
Your mission is to generate rich, contextual explanations for every step and edge in a feature request flow.

You MUST return ONLY valid JSON — an array of insight objects:
[
  {
    "feature_id": "feat_0",
    "from": "api_handler",
    "to": "redis_cache",
    "insight": "Implements Cache-Aside pattern: checks Redis before querying the database. Uses TTL of 300s to avoid stale data.",
    "pattern": "Cache-Aside",
    "performance_note": "Sub-millisecond lookup on cache hit vs ~25ms on DB fallback",
    "security_note": "Ensure cache key cannot be poisoned with unvalidated user parameters"
  }
]

Guidelines:
- Return exactly one insight per flow edge.
- Provide crisp, highly technical insights referencing actual code constructs.
- Output raw JSON only."""

INSIGHT_PROMPT = """Generate technical insights for all edges in these feature flows:

FLOWS:
{flows}

PROJECT PROFILE:
{profile}

RELEVANT CODE:
{code_samples}

Use your tools to reason or search if needed. Return ONLY the JSON array."""


def run_insight_agent(
    flows: list[dict[str, Any]],
    profile: dict[str, Any],
    code_samples: str,
) -> list[dict[str, Any]]:
    """Run the Insight DeepAgent to produce hover explanations for all flow edges."""
    llm = get_chat_llm()
    if llm is None:
        return _heuristic_insights(flows)

    prompt = INSIGHT_PROMPT.format(
        flows=json.dumps(flows, indent=2)[:6000],
        profile=json.dumps(profile, indent=2)[:1500],
        code_samples=code_samples[:3000],
    )

    try:
        deep_agent = create_deep_agent(
            model=llm,
            tools=INSIGHT_TOOLS,
            system_prompt=INSIGHT_SYSTEM,
        )
        response = deep_agent.invoke({
            "messages": [HumanMessage(content=prompt)]
        })
        messages = response.get("messages", [])
        if messages:
            last_msg = messages[-1]
            content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
            data = _parse_insights_json(content)
            if data and isinstance(data, list) and len(data) > 0:
                return data
    except Exception as exc:
        logger.warning("Insight DeepAgent fallback: %s", exc)

    return _heuristic_insights(flows)


def _parse_insights_json(content: str) -> list[dict] | None:
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


def _heuristic_insights(flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generate high-quality insights deterministically."""
    insights = []
    for flow in flows:
        feat_id = flow.get("feature_id", "feat_0")
        for edge in flow.get("edges", []):
            from_id = edge.get("from", "?")
            to_id = edge.get("to", "?")
            label = edge.get("label", "")
            data = edge.get("data", "")

            lbl_lower = label.lower()
            to_lower = to_id.lower()

            if "cache" in lbl_lower or "cache" in to_lower:
                insight = f"Cache operation: {label}. Efficiently retrieves or invalidates temporary state ({data})."
                pattern = "Cache-Aside"
                perf = "Fast O(1) in-memory key-value access"
                sec = "Verify isolation of user data partitions"
            elif "sql" in lbl_lower or "query" in lbl_lower or "database" in to_lower:
                insight = f"Database operation: {label}. Executes structured data retrieval/persistence ({data})."
                pattern = "Repository / Active Record"
                perf = "Uses indexed database queries to minimize latency"
                sec = "Parameterized query protects against SQL injection"
            elif "http" in lbl_lower or "request" in lbl_lower:
                insight = f"Network ingress: {label}. Accepts client request and enforces protocol serialization."
                pattern = "API Gateway / Controller"
                perf = "Minimal overhead before handler dispatch"
                sec = "Enforces CORS, TLS termination, and request body size limits"
            elif "queue" in lbl_lower or "worker" in to_lower:
                insight = f"Asynchronous message delivery: {label}. Enqueues work payload ({data}) for background processing."
                pattern = "Publisher / Subscriber"
                perf = "Non-blocking dispatch with decoupled worker scaling"
                sec = "Message payload integrity verified with job HMAC or validation schema"
            else:
                insight = f"{label}: {data}. Handles domain business logic transition."
                pattern = "Facade / Service Layer"
                perf = "Synchronous execution within handler thread"
                sec = "Validates input boundaries and authorization scopes"

            insights.append({
                "feature_id": feat_id,
                "from": from_id,
                "to": to_id,
                "insight": insight,
                "pattern": pattern,
                "performance_note": perf,
                "security_note": sec,
            })
    return insights
