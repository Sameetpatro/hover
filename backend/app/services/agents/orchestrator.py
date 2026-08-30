"""LangGraph Orchestrator — 8-Stage Pipeline with LangChain DeepAgents.

Coordinates the complete 8-stage architecture workflow via a LangGraph StateGraph:
  1. Ingest & Extract (LangGraph Node: Unzip Tool, File System Read)
  2. Static Analysis (LangGraph Node: AST Parser, Dependency Parser, Code Indexer, Regex Finder)
  3. Scout (LangGraph Node + Scout DeepAgent: Tech Stack, Architecture Style, Major Components)
  4. Feature Discovery & Inventory (LangGraph Node + Feature DeepAgent: Endpoints, Modules, Features)
  5. Flow Analysis Manager (LangGraph Node + Spawns N Flow DeepAgents per endpoint/feature)
  6. Graph Builder & Aggregator (LangGraph Node: Build Graph Structure, Deduplicate Nodes, Merge Flows)
  7. Insight Generator (LangGraph Node + Insight DeepAgent: Explanations, Tooltips, Insights)
  8. Output (LangGraph Node: 3D Map + Chatbot Knowledge Base Indexer)
"""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.services import analysis as an
from app.services.agents.feature_agent import run_feature_agent
from app.services.agents.flow_agent import run_flow_agent_batch
from app.services.agents.insight_agent import run_insight_agent
from app.services.agents.metadata_agent import run_metadata_agent
from app.services.agents.scout_agent import run_scout_agent
from app.services.agents.tools import set_tool_context
from app.services.architecture import generate_architecture
from app.services.rag import embed_texts, retrieve_docs
from app.services.storage import safe_join

logger = logging.getLogger(__name__)

SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv"}


# ---------------------------------------------------------------------------
# State Schema for the 8-Stage LangGraph Pipeline
# ---------------------------------------------------------------------------


class AgentState(TypedDict, total=False):
    # Pipeline execution parameters & inputs
    project_id: str
    project_name: str
    zip_path: str
    extract_dir: str
    project_root: str

    # Stage 1 & 2 outputs (Deterministic AST & files)
    extracted_files: list[dict]
    files: list[dict]
    symbols: list[dict]
    edges: list[dict]
    chunk_rows: list[dict]

    # Stage 3-5 outputs (DeepAgent exploration)
    profile: dict
    features: list[dict]
    feature_flows: list[dict]

    # Stage 6 output (Unified graph)
    aggregated_graph: dict

    # Stage 7 output (Insight DeepAgent)
    insights: list[dict]
    metadata: dict

    # Stage 8 output (3D snapshot & knowledge index)
    output_manifest: dict
    architecture_data: dict

    # Progress tracking callback: callable(stage_name, progress_float)
    on_progress: Any


# ---------------------------------------------------------------------------
# Helper Context Utilities
# ---------------------------------------------------------------------------


def _gather_tool_data(state: AgentState) -> None:
    """Initialize shared tool context with state data."""
    root = Path(state.get("project_root", "."))
    set_tool_context(
        project_root=root,
        files=state.get("files", []),
        symbols=state.get("symbols", []),
        edges=state.get("edges", []),
        chunk_rows=state.get("chunk_rows", []),
    )


def _search_rag(query: str, state: AgentState, limit: int = 8) -> str:
    """RAG search returning formatted snippets."""
    docs = retrieve_docs(query, state.get("chunk_rows", []), limit=limit)
    parts = []
    for d in docs:
        path = d.metadata.get("path", "?")
        sym = d.metadata.get("symbol", "")
        header = f"FILE: {path}" + (f" ({sym})" if sym else "")
        parts.append(f"{header}\n{d.page_content[:600]}")
    return "\n\n---\n\n".join(parts) if parts else "(no results)"


def _file_listing(state: AgentState) -> str:
    """Compact file structure listing."""
    lines = []
    for f in state.get("files", [])[:100]:
        path = f.get("path", "?")
        lang = f.get("language", "?")
        role = f.get("role", "?")
        lines.append(f"{path}  [{lang}, {role}]")
    return "\n".join(lines)


def _get_routes_text(state: AgentState) -> str:
    """Extract discovered endpoint symbols."""
    symbols = state.get("symbols", [])
    lines = []
    for s in symbols:
        if s.get("kind") == "endpoint":
            lines.append(f"  {s.get('signature', s.get('name', '?'))}  in {s.get('file_path', '?')}")
    return "\n".join(lines) if lines else "(no routes found)"


def _get_dependencies_text(state: AgentState) -> str:
    """Extract dependency manifest files."""
    root = Path(state.get("project_root", "."))
    dep_files = [
        "package.json", "requirements.txt", "Pipfile", "pyproject.toml",
        "go.mod", "Gemfile", "pom.xml", "Cargo.toml", "composer.json",
    ]
    parts = []
    for dep in dep_files:
        for sub in ["", "backend/", "frontend/", "server/", "client/"]:
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
# 8 LangGraph Node Implementations
# ---------------------------------------------------------------------------


def node_1_ingest_extract(state: AgentState) -> dict:
    """Stage 1: Ingest & Extract (Unzip Tool, File System Read)."""
    logger.info("📦 [Stage 1/8] Ingest & Extract starting")
    cb = state.get("on_progress")
    if cb:
        cb("extracting", 0.10)

    zip_path_str = state.get("zip_path")
    extract_dir_str = state.get("extract_dir")

    # If already extracted beforehand, verify project root
    if not zip_path_str or not Path(zip_path_str).exists():
        root = Path(state.get("project_root", "."))
        logger.info("📦 [Stage 1/8] Using pre-extracted directory at %s", root)
        return {"project_root": str(root)}

    zip_path = Path(zip_path_str)
    dest = Path(extract_dir_str or (zip_path.parent / "src"))
    dest.mkdir(parents=True, exist_ok=True)

    extracted_records: list[dict] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = Path(info.filename.replace("\\", "/")).parts
            if any(p in SKIP_DIRS for p in parts) or Path(info.filename).name.startswith("."):
                continue
            target = safe_join(dest, info.filename)
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
            try:
                text = target.read_text(encoding="utf-8", errors="ignore")
                loc = text.count("\n") + (1 if text else 0)
            except Exception:
                loc = 0
            extracted_records.append({
                "path": info.filename.replace("\\", "/"),
                "size": target.stat().st_size,
                "loc": loc,
                "abs": target,
            })

    children = [p for p in dest.iterdir() if p.name != "__MACOSX"]
    root = dest
    if len(children) == 1 and children[0].is_dir():
        root = children[0]

    normalized_records = []
    for item in extracted_records:
        abs_path = item["abs"]
        try:
            rel = str(abs_path.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = item["path"]
        normalized_records.append({**item, "path": rel, "abs": root / rel})

    logger.info("📦 [Stage 1/8] Ingest complete: %d files extracted", len(normalized_records))
    return {
        "project_root": str(root),
        "extracted_files": normalized_records,
    }


def node_2_static_analysis(state: AgentState) -> dict:
    """Stage 2: Static Analysis (AST Parser, Dependency Parser, Code Indexer, Pattern Finder)."""
    logger.info("🔬 [Stage 2/8] Static Analysis starting")
    cb = state.get("on_progress")
    if cb:
        cb("analyzing", 0.25)

    root = Path(state.get("project_root", "."))
    extracted = state.get("extracted_files", [])

    # If extracted_files is empty, scan project_root directly
    if not extracted and root.exists():
        for p in root.rglob("*"):
            if not p.is_file() or any(skip in p.parts for skip in SKIP_DIRS):
                continue
            try:
                rel = str(p.relative_to(root)).replace("\\", "/")
                txt = p.read_text(encoding="utf-8", errors="ignore")
                loc = txt.count("\n") + (1 if txt else 0)
                extracted.append({"path": rel, "size": p.stat().st_size, "loc": loc, "abs": p})
            except Exception:
                pass

    analyzed = []
    files_data = []
    for fr in extracted:
        abs_path = fr.get("abs")
        if not abs_path or not abs_path.is_file():
            continue
        res = an.analyze_file(fr["path"], abs_path)
        analyzed.append(res)
        files_data.append({
            "path": res.path,
            "language": res.language,
            "role": res.role,
            "loc": res.loc,
            "size_bytes": fr.get("size", 0),
            "imports": res.imports[:50],
        })

    # Build dependency graph
    nodes, raw_edges = an.build_graph(analyzed)
    edges_data = [{"source": e["source"], "target": e["target"], "edge_type": e.get("edge_type", "import")} for e in raw_edges]

    # Collect AST symbols
    symbols_data = []
    for a in analyzed:
        for s in a.symbols:
            symbols_data.append({
                "name": s.name,
                "kind": s.kind,
                "file_path": a.path,
                "signature": s.signature,
                "start_line": s.start_line,
                "end_line": s.end_line,
            })

    # Chunking & Embedding index
    if cb:
        cb("embedding", 0.40)

    chunk_defs = []
    for a in analyzed:
        abs_path = root / a.path
        if abs_path.is_file():
            for ch in an.chunk_file(a, abs_path):
                chunk_defs.append((a.path, ch))

    texts = [f"File: {path}\nSymbol: {ch.get('symbol_name','')}\n{ch['content']}" for path, ch in chunk_defs]
    vectors = embed_texts(texts) if texts else []
    chunk_rows = []
    for i, (path, ch) in enumerate(chunk_defs):
        emb = vectors[i] if i < len(vectors) else []
        chunk_rows.append({
            "content": ch["content"],
            "file_path": path,
            "symbol_name": ch.get("symbol_name", ""),
            "language": ch.get("language", ""),
            "start_line": ch.get("start_line", 0),
            "end_line": ch.get("end_line", 0),
            "embedding": emb,
        })

    logger.info("🔬 [Stage 2/8] Static Analysis complete: %d files, %d symbols, %d edges, %d chunks",
                len(files_data), len(symbols_data), len(edges_data), len(chunk_rows))

    return {
        "files": files_data,
        "symbols": symbols_data,
        "edges": edges_data,
        "chunk_rows": chunk_rows,
    }


def node_3_scout(state: AgentState) -> dict:
    """Stage 3: Scout (High Level Understanding via Scout DeepAgent)."""
    logger.info("🔍 [Stage 3/8] Scout DeepAgent: profiling tech stack and architecture")
    cb = state.get("on_progress")
    if cb:
        cb("scouting", 0.50)

    _gather_tool_data(state)

    file_listing = _file_listing(state)
    dependencies = _get_dependencies_text(state)
    routes = _get_routes_text(state)
    code_samples = _search_rag("entry point main server app routing configuration", state)

    profile = run_scout_agent(file_listing, dependencies, routes, code_samples)
    profile.setdefault("project_name", state.get("project_name", "Unknown Project"))
    logger.info("🔍 [Stage 3/8] Scout complete: %s (pattern=%s)",
                profile.get("project_name"), profile.get("architecture_pattern"))
    return {"profile": profile}


def node_4_feature_discovery(state: AgentState) -> dict:
    """Stage 4: Feature Discovery & Inventory (via Feature DeepAgent)."""
    logger.info("📋 [Stage 4/8] Feature Discovery DeepAgent: cataloging endpoints and features")
    cb = state.get("on_progress")
    if cb:
        cb("discovering", 0.60)

    _gather_tool_data(state)

    profile = state.get("profile", {})
    routes = _get_routes_text(state)
    code_samples = _search_rag("API route endpoint controller handler", state)
    file_listing = _file_listing(state)

    features = run_feature_agent(profile, routes, code_samples, file_listing)
    logger.info("📋 [Stage 4/8] Feature Discovery complete: found %d features", len(features))
    return {"features": features}


def node_5_flow_analysis_manager(state: AgentState) -> dict:
    """Stage 5: Flow Analysis Manager (Spawns N Flow DeepAgents per endpoint/feature)."""
    features = state.get("features", [])
    logger.info("🔗 [Stage 5/8] Flow Analysis Manager: spawning %d Flow DeepAgents", len(features))
    cb = state.get("on_progress")
    if cb:
        cb("tracing", 0.70)

    _gather_tool_data(state)
    profile = state.get("profile", {})
    root = Path(state.get("project_root", "."))

    def code_getter(feat: dict) -> tuple[str, str, str]:
        entry_file = feat.get("entry_file", "")
        name = feat.get("name", "")
        entry_code = ""
        if entry_file:
            target = root / entry_file
            if target.is_file():
                try:
                    entry_code = target.read_text(encoding="utf-8", errors="ignore")[:3000]
                except Exception:
                    pass

        query = f"{name} {feat.get('entry_function', '')} {feat.get('path', '')} handler service model"
        related_code = _search_rag(query, state, limit=6)

        dep_code_parts = []
        for edge in state.get("edges", []):
            if edge.get("source", "") == entry_file:
                dep_file = root / edge.get("target", "")
                if dep_file.is_file():
                    try:
                        dep_code_parts.append(
                            f"=== {edge['target']} ===\n" + dep_file.read_text(encoding="utf-8", errors="ignore")[:1500]
                        )
                    except Exception:
                        pass
                if len(dep_code_parts) >= 4:
                    break
        dep_code = "\n\n".join(dep_code_parts) if dep_code_parts else "(no dependencies)"
        return entry_code, related_code, dep_code

    flows = run_flow_agent_batch(features, profile, code_getter)
    logger.info("🔗 [Stage 5/8] Flow Analysis complete: traced %d flows", len(flows))
    return {"feature_flows": flows}


def node_6_graph_builder_aggregator(state: AgentState) -> dict:
    """Stage 6: Graph Builder & Aggregator (Build Graph Structure, Deduplicate, Merge Flows)."""
    logger.info("🏗️ [Stage 6/8] Graph Builder & Aggregator: merging and deduplicating flow graphs")
    cb = state.get("on_progress")
    if cb:
        cb("aggregating", 0.80)

    flows = state.get("feature_flows", [])
    raw_nodes: list[dict] = []
    raw_edges: list[dict] = []

    node_registry: dict[str, dict] = {}
    edge_keys: set[str] = set()
    merged_edges: list[dict] = []

    for flow in flows:
        feat_id = flow.get("feature_id", "")
        for n in flow.get("nodes", []):
            nid = n.get("id", "")
            if nid not in node_registry:
                node_registry[nid] = {
                    "id": nid,
                    "type": n.get("type", "service"),
                    "label": n.get("label", nid),
                    "features": [feat_id],
                }
            else:
                if feat_id not in node_registry[nid]["features"]:
                    node_registry[nid]["features"].append(feat_id)

        for e in flow.get("edges", []):
            from_id = e.get("from", "")
            to_id = e.get("to", "")
            ekey = f"{from_id}->{to_id}:{e.get('label','')}"
            if ekey not in edge_keys:
                edge_keys.add(ekey)
                merged_edges.append({**e, "features": [feat_id]})
            else:
                for me in merged_edges:
                    if f"{me.get('from')}->{me.get('to')}:{me.get('label','')}" == ekey:
                        if feat_id not in me["features"]:
                            me["features"].append(feat_id)

    aggregated_graph = {
        "nodes": list(node_registry.values()),
        "edges": merged_edges,
        "flows_count": len(flows),
    }

    logger.info("🏗️ [Stage 6/8] Graph Builder complete: %d unified nodes, %d unified edges",
                len(node_registry), len(merged_edges))
    return {"aggregated_graph": aggregated_graph}


def node_7_insight_generator(state: AgentState) -> dict:
    """Stage 7: Insight Generator (via Insight DeepAgent)."""
    logger.info("💡 [Stage 7/8] Insight DeepAgent: generating edge tooltips and explanations")
    cb = state.get("on_progress")
    if cb:
        cb("enriching", 0.88)

    _gather_tool_data(state)
    flows = state.get("feature_flows", [])
    profile = state.get("profile", {})
    code_samples = _search_rag("service repository cache query pattern security", state)

    insights = run_insight_agent(flows, profile, code_samples)

    # Synthesize metadata
    file_listing = _file_listing(state)
    dependencies = _get_dependencies_text(state)
    metadata = run_metadata_agent(profile, file_listing, code_samples, dependencies)

    logger.info("💡 [Stage 7/8] Insight Generator complete: %d insights generated", len(insights))
    return {
        "insights": insights,
        "metadata": metadata,
    }


def node_8_output(state: AgentState) -> dict:
    """Stage 8: Output (3D Map Snapshot + Chatbot Knowledge Base Index)."""
    logger.info("🚀 [Stage 8/8] Output: preparing 3D visualization and chatbot knowledge base")
    cb = state.get("on_progress")
    if cb:
        cb("ready", 1.0)

    # Compile 3D architecture snapshot data
    files_data = state.get("files", [])
    symbols_data = state.get("symbols", [])
    edges_data = state.get("edges", [])
    chunk_rows = state.get("chunk_rows", [])

    class MockProject:
        name = state.get("project_name", "Hover Project")
        id = state.get("project_id", "project_0")

    class MockFile:
        def __init__(self, d):
            self.path = d.get("path", "")
            self.language = d.get("language", "")
            self.role = d.get("role", "")
            self.loc = d.get("loc", 0)

    class MockSymbol:
        def __init__(self, d):
            self.name = d.get("name", "")
            self.kind = d.get("kind", "")
            self.file_path = d.get("file_path", "")
            self.signature = d.get("signature", "")

    class MockChunk:
        def __init__(self, d):
            self.content = d.get("content", "")
            self.file_path = d.get("file_path", "")
            self.symbol_name = d.get("symbol_name", "")
            emb = d.get("embedding", [])
            self.embedding_json = json.dumps(emb) if isinstance(emb, list) else str(emb)

    p_files = [MockFile(f) for f in files_data]
    p_symbols = [MockSymbol(s) for s in symbols_data]
    p_chunks = [MockChunk(c) for c in chunk_rows]

    arch_data = generate_architecture(
        MockProject(),
        p_files,
        p_symbols,
        edges_data,
        p_chunks,
    )

    output_manifest = {
        "status": "ready",
        "project_id": state.get("project_id"),
        "project_name": state.get("project_name"),
        "features_count": len(state.get("features", [])),
        "flows_count": len(state.get("feature_flows", [])),
        "insights_count": len(state.get("insights", [])),
        "knowledge_chunks": len(chunk_rows),
    }

    logger.info("🚀 [Stage 8/8] Pipeline complete for %s", state.get("project_name"))
    return {
        "output_manifest": output_manifest,
        "architecture_data": arch_data,
    }


# ---------------------------------------------------------------------------
# Construct the 8-Stage LangGraph StateGraph
# ---------------------------------------------------------------------------


def build_8_stage_graph() -> StateGraph:
    """Build the unified 8-Stage LangGraph pipeline.

    Topology:
      1_ingest_extract → 2_static_analysis → 3_scout → 4_feature_discovery
      → 5_flow_analysis_manager → 6_graph_builder_aggregator → 7_insight_generator
      → 8_output → END
    """
    graph = StateGraph(AgentState)

    # Register the 8 nodes
    graph.add_node("1_ingest_extract", node_1_ingest_extract)
    graph.add_node("2_static_analysis", node_2_static_analysis)
    graph.add_node("3_scout", node_3_scout)
    graph.add_node("4_feature_discovery", node_4_feature_discovery)
    graph.add_node("5_flow_analysis_manager", node_5_flow_analysis_manager)
    graph.add_node("6_graph_builder_aggregator", node_6_graph_builder_aggregator)
    graph.add_node("7_insight_generator", node_7_insight_generator)
    graph.add_node("8_output", node_8_output)

    # Linear workflow sequence
    graph.set_entry_point("1_ingest_extract")
    graph.add_edge("1_ingest_extract", "2_static_analysis")
    graph.add_edge("2_static_analysis", "3_scout")
    graph.add_edge("3_scout", "4_feature_discovery")
    graph.add_edge("4_feature_discovery", "5_flow_analysis_manager")
    graph.add_edge("5_flow_analysis_manager", "6_graph_builder_aggregator")
    graph.add_edge("6_graph_builder_aggregator", "7_insight_generator")
    graph.add_edge("7_insight_generator", "8_output")
    graph.add_edge("8_output", END)

    return graph


_compiled_graph = None


def get_agent_graph():
    """Get or compile the 8-stage LangGraph workflow."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_8_stage_graph().compile()
    return _compiled_graph


def run_deep_analysis(
    *,
    project_id: str,
    project_name: str,
    project_root: str,
    zip_path: str = "",
    extract_dir: str = "",
    files: list[dict] | None = None,
    symbols: list[dict] | None = None,
    edges: list[dict] | None = None,
    chunk_rows: list[dict] | None = None,
    on_progress: Any = None,
) -> dict[str, Any]:
    """Execute the full 8-Stage LangGraph + DeepAgents workflow."""
    graph = get_agent_graph()

    initial_state: AgentState = {
        "project_id": project_id,
        "project_name": project_name,
        "project_root": project_root,
        "zip_path": zip_path,
        "extract_dir": extract_dir,
        "files": files or [],
        "symbols": symbols or [],
        "edges": edges or [],
        "chunk_rows": chunk_rows or [],
        "on_progress": on_progress,
    }

    logger.info("🚀 Executing 8-Stage LangGraph pipeline for project: %s", project_name)
    result = graph.invoke(initial_state)
    logger.info("✅ 8-Stage LangGraph pipeline complete for project: %s", project_name)

    return {
        "profile": result.get("profile", {}),
        "features": result.get("features", []),
        "feature_flows": result.get("feature_flows", []),
        "aggregated_graph": result.get("aggregated_graph", {}),
        "metadata": result.get("metadata", {}),
        "insights": result.get("insights", []),
        "architecture_data": result.get("architecture_data", {}),
        "output_manifest": result.get("output_manifest", {}),
    }
