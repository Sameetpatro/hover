"""LangGraph Orchestrator — DeepAgents multi-agent pipeline.

Coordinates 5 specialist agents via a LangGraph StateGraph:
  Scout → Feature Discovery → Flow Tracer → [Metadata + Insight] → Done

The graph dynamically adapts based on what each agent discovers.
This is the "deep" part: the Flow Tracer spawns sub-tasks per feature.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.services.agents.tools import set_tool_context
from app.services.agents.scout_agent import run_scout_agent
from app.services.agents.feature_agent import run_feature_agent
from app.services.agents.flow_agent import run_flow_agent_batch
from app.services.agents.metadata_agent import run_metadata_agent
from app.services.agents.insight_agent import run_insight_agent
from app.services.rag import retrieve_docs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State schema — flows through the entire graph
# ---------------------------------------------------------------------------


class AgentState(TypedDict, total=False):
    # Inputs (set before graph invocation)
    project_id: str
    project_name: str
    project_root: str              # Path to extracted source
    files: list[dict]              # AnalyzedFile dicts
    symbols: list[dict]            # Symbol dicts
    edges: list[dict]              # Dependency edges
    chunk_rows: list[dict]         # RAG chunks with embeddings
    # Agent outputs
    profile: dict                  # Scout agent → ProjectProfile
    features: list[dict]           # Feature agent → features list
    feature_flows: list[dict]      # Flow agent → per-feature flow graphs
    metadata: dict                 # Metadata agent → tech/design info
    insights: list[dict]           # Insight agent → edge insights
    # Progress callback
    on_progress: Any               # callable(stage, progress) or None


# ---------------------------------------------------------------------------
# Helper: gather code for tools
# ---------------------------------------------------------------------------


def _gather_tool_data(state: AgentState) -> None:
    """Initialize tool context from state."""
    root = Path(state.get("project_root", "."))
    set_tool_context(
        project_root=root,
        files=state.get("files", []),
        symbols=state.get("symbols", []),
        edges=state.get("edges", []),
        chunk_rows=state.get("chunk_rows", []),
    )


def _search_rag(query: str, state: AgentState, limit: int = 8) -> str:
    """Quick RAG search returning formatted text."""
    docs = retrieve_docs(query, state.get("chunk_rows", []), limit=limit)
    parts = []
    for d in docs:
        path = d.metadata.get("path", "?")
        sym = d.metadata.get("symbol", "")
        header = f"FILE: {path}" + (f" ({sym})" if sym else "")
        parts.append(f"{header}\n{d.page_content[:600]}")
    return "\n\n---\n\n".join(parts) if parts else "(no results)"


def _file_listing(state: AgentState) -> str:
    """Build a compact file listing."""
    lines = []
    for f in state.get("files", [])[:100]:
        path = f.get("path", "?")
        lang = f.get("language", "?")
        role = f.get("role", "?")
        lines.append(f"{path}  [{lang}, {role}]")
    return "\n".join(lines)


def _get_routes_text(state: AgentState) -> str:
    """Extract routes from symbols."""
    symbols = state.get("symbols", [])
    lines = []
    for s in symbols:
        if s.get("kind") == "endpoint":
            lines.append(f"  {s.get('signature', s.get('name', '?'))}  in {s.get('file_path', '?')}")
    return "\n".join(lines) if lines else "(no routes found)"


def _get_dependencies_text(state: AgentState) -> str:
    """Read dependency files from project root."""
    root = Path(state.get("project_root", "."))
    dep_files = [
        "package.json", "requirements.txt", "Pipfile", "pyproject.toml",
        "go.mod", "Gemfile", "pom.xml", "Cargo.toml", "composer.json",
    ]
    parts = []
    for dep in dep_files:
        for sub in ["", "backend/", "frontend/", "server/"]:
            target = root / sub / dep
            if target.is_file():
                try:
                    content = target.read_text(encoding="utf-8", errors="ignore")[:2000]
                    rel = str(target.relative_to(root))
                    parts.append(f"=== {rel} ===\n{content}")
                except Exception:
                    pass
    return "\n\n".join(parts) if parts else "(no dependency files)"


# ---------------------------------------------------------------------------
# Graph node functions
# ---------------------------------------------------------------------------


def scout_node(state: AgentState) -> dict:
    """Run the Scout Agent to profile the project."""
    logger.info("🔍 Scout Agent: profiling project %s", state.get("project_name"))
    cb = state.get("on_progress")
    if cb:
        cb("scouting", 0.50)

    _gather_tool_data(state)

    file_listing = _file_listing(state)
    dependencies = _get_dependencies_text(state)
    routes = _get_routes_text(state)
    code_samples = _search_rag("project entry point main server setup configuration", state)

    profile = run_scout_agent(file_listing, dependencies, routes, code_samples)
    profile.setdefault("project_name", state.get("project_name", "Unknown"))
    logger.info("🔍 Scout Agent done: %s (%s)", profile.get("project_name"), profile.get("architecture_pattern"))
    return {"profile": profile}


def feature_node(state: AgentState) -> dict:
    """Run the Feature Discovery Agent."""
    logger.info("📋 Feature Agent: discovering features")
    cb = state.get("on_progress")
    if cb:
        cb("discovering", 0.58)

    profile = state.get("profile", {})
    routes = _get_routes_text(state)
    code_samples = _search_rag("API route handler controller endpoint create get update delete", state)
    file_listing = _file_listing(state)

    features = run_feature_agent(profile, routes, code_samples, file_listing)
    logger.info("📋 Feature Agent done: found %d features", len(features))
    return {"features": features}


def flow_node(state: AgentState) -> dict:
    """Run the Flow Tracer Agent for each feature."""
    features = state.get("features", [])
    logger.info("🔗 Flow Agent: tracing %d features", len(features))
    cb = state.get("on_progress")
    if cb:
        cb("tracing", 0.65)

    profile = state.get("profile", {})
    root = Path(state.get("project_root", "."))

    def code_getter(feat: dict) -> tuple[str, str, str]:
        """Gather code context for a feature."""
        entry_file = feat.get("entry_file", "")
        entry_func = feat.get("entry_function", "")
        name = feat.get("name", "")

        # Read entry file
        entry_code = ""
        if entry_file:
            target = root / entry_file
            if target.is_file():
                try:
                    entry_code = target.read_text(encoding="utf-8", errors="ignore")[:3000]
                except Exception:
                    pass

        # RAG search for related code
        query = f"{name} {entry_func} {feat.get('path', '')} handler service"
        related_code = _search_rag(query, state, limit=6)

        # Follow imports from entry file
        dep_code_parts = []
        for edge in state.get("edges", []):
            if edge.get("source", "") == entry_file:
                dep_file = root / edge.get("target", "")
                if dep_file.is_file():
                    try:
                        dep_code_parts.append(
                            f"=== {edge['target']} ===\n"
                            + dep_file.read_text(encoding="utf-8", errors="ignore")[:1500]
                        )
                    except Exception:
                        pass
                if len(dep_code_parts) >= 4:
                    break
        dep_code = "\n\n".join(dep_code_parts) if dep_code_parts else "(no dependencies found)"

        return entry_code, related_code, dep_code

    flows = run_flow_agent_batch(features, profile, code_getter)
    logger.info("🔗 Flow Agent done: traced %d flows", len(flows))
    return {"feature_flows": flows}


def metadata_node(state: AgentState) -> dict:
    """Run the Metadata Agent."""
    logger.info("📊 Metadata Agent: extracting metadata")
    cb = state.get("on_progress")
    if cb:
        cb("enriching", 0.80)

    profile = state.get("profile", {})
    file_listing = _file_listing(state)
    code_samples = _search_rag("model schema database migration config settings", state)
    dependencies = _get_dependencies_text(state)

    metadata = run_metadata_agent(profile, file_listing, code_samples, dependencies)
    logger.info("📊 Metadata Agent done")
    return {"metadata": metadata}


def insight_node(state: AgentState) -> dict:
    """Run the Insight Generator Agent."""
    logger.info("💡 Insight Agent: generating insights")
    cb = state.get("on_progress")
    if cb:
        cb("enriching", 0.88)

    flows = state.get("feature_flows", [])
    profile = state.get("profile", {})
    code_samples = _search_rag("service logic repository cache database query", state)

    insights = run_insight_agent(flows, profile, code_samples)
    logger.info("💡 Insight Agent done: %d insights", len(insights))
    return {"insights": insights}


# ---------------------------------------------------------------------------
# Build the LangGraph
# ---------------------------------------------------------------------------


def build_agent_graph() -> StateGraph:
    """Construct the DeepAgents LangGraph pipeline.

    Graph topology:
        scout → feature_discovery → flow_tracer → metadata → insight → END

    The metadata and insight agents run sequentially for simplicity.
    In a production version these could fan out in parallel.
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("scout", scout_node)
    graph.add_node("feature_discovery", feature_node)
    graph.add_node("flow_tracer", flow_node)
    graph.add_node("metadata", metadata_node)
    graph.add_node("insight", insight_node)

    # Define edges (linear pipeline)
    graph.set_entry_point("scout")
    graph.add_edge("scout", "feature_discovery")
    graph.add_edge("feature_discovery", "flow_tracer")
    graph.add_edge("flow_tracer", "metadata")
    graph.add_edge("metadata", "insight")
    graph.add_edge("insight", END)

    return graph


# Pre-compile the graph
_compiled_graph = None


def get_agent_graph():
    """Get or create the compiled agent graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agent_graph().compile()
    return _compiled_graph


def run_deep_analysis(
    *,
    project_id: str,
    project_name: str,
    project_root: str,
    files: list[dict],
    symbols: list[dict],
    edges: list[dict],
    chunk_rows: list[dict],
    on_progress: Any = None,
) -> dict[str, Any]:
    """Run the full DeepAgents pipeline and return all agent outputs.

    Returns a dict with keys: profile, features, feature_flows, metadata, insights.
    """
    graph = get_agent_graph()

    initial_state: AgentState = {
        "project_id": project_id,
        "project_name": project_name,
        "project_root": project_root,
        "files": files,
        "symbols": symbols,
        "edges": edges,
        "chunk_rows": chunk_rows,
        "on_progress": on_progress,
    }

    logger.info("🚀 DeepAgents pipeline starting for project: %s", project_name)
    result = graph.invoke(initial_state)
    logger.info("✅ DeepAgents pipeline complete for project: %s", project_name)

    return {
        "profile": result.get("profile", {}),
        "features": result.get("features", []),
        "feature_flows": result.get("feature_flows", []),
        "metadata": result.get("metadata", {}),
        "insights": result.get("insights", []),
    }
