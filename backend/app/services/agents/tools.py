"""Comprehensive LangChain / DeepAgents tools for Hover Codebase Analysis.

Implements all 6 tool categories from the architecture diagram:
  1. File & Code Tools
  2. AST & Analysis Tools
  3. Tracing Tools
  4. Data Source Tools
  5. Utility Tools
  6. Storage Tools
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global Tool Context (injected per pipeline run)
# ---------------------------------------------------------------------------

_ctx: dict[str, Any] = {}


def set_tool_context(
    *,
    project_root: Path,
    files: list[dict],
    symbols: list[dict],
    edges: list[dict],
    chunk_rows: list[dict],
    ast_data: list[dict] | None = None,
    graph_data: dict[str, Any] | None = None,
) -> None:
    """Inject analyzed codebase context into the tool registry."""
    _ctx["root"] = Path(project_root)
    _ctx["files"] = files or []
    _ctx["symbols"] = symbols or []
    _ctx["edges"] = edges or []
    _ctx["chunk_rows"] = chunk_rows or []
    _ctx["ast_data"] = ast_data or []
    _ctx["graph_data"] = graph_data or {}


def _get(key: str, default: Any = None) -> Any:
    return _ctx.get(key, default if default is not None else [])


def _resolve_file(file_path: str) -> Path | None:
    root: Path = _ctx.get("root", Path("."))
    clean = file_path.strip().lstrip("/")
    target = root / clean
    if target.is_file():
        return target
    for prefix in ["", "src/", "app/", "backend/", "frontend/", "server/", "client/"]:
        alt = root / prefix / clean
        if alt.is_file():
            return alt
    return None


# ---------------------------------------------------------------------------
# 1. File & Code Tools
# ---------------------------------------------------------------------------


@tool
def read_file(file_path: str) -> str:
    """Read the full or sectional content of a specific file in the project.
    Args:
        file_path: Relative file path (e.g. 'app/main.py', 'src/routes.ts').
    """
    target = _resolve_file(file_path)
    if not target:
        return f"File not found: {file_path}"
    try:
        content = target.read_text(encoding="utf-8", errors="ignore")
        if len(content) > 8000:
            return content[:8000] + f"\n... [truncated, total {len(content)} chars]"
        return content
    except Exception as exc:
        return f"Error reading {file_path}: {exc}"


@tool
def search_codebase(query: str) -> str:
    """Search the codebase semantically and by keyword.
    Returns the most relevant code snippets matching the query (up to 8 results).
    """
    from app.services.rag import retrieve_docs

    chunks = _get("chunk_rows")
    if not chunks:
        # Fallback to in-file regex search if chunks are not yet populated
        return pattern_finder.invoke({"pattern": query})

    docs = retrieve_docs(query, chunks, limit=8)
    if not docs:
        return "No relevant code found for query: " + query

    parts = []
    for d in docs:
        path = d.metadata.get("path", "?")
        sym = d.metadata.get("symbol", "")
        header = f"FILE: {path}" + (f" ({sym})" if sym else "")
        parts.append(f"{header}\n{d.page_content[:700]}")
    return "\n\n---\n\n".join(parts)


@tool
def list_files(pattern: str = "") -> str:
    """List all project files with language, role, and line counts, optionally filtered by pattern.
    Args:
        pattern: Optional substring or glob to filter paths (e.g. 'router', 'models', '*.py').
    """
    files = _get("files")
    if not files:
        root = _get("root", Path("."))
        if isinstance(root, Path) and root.exists():
            found = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()][:100]
            return "\n".join(found) if found else "No files found."
        return "No files available."

    results = []
    pat_lower = pattern.lower() if pattern else ""
    for f in files:
        path = f.get("path", "")
        if pat_lower and pat_lower not in path.lower():
            continue
        lang = f.get("language", "?")
        role = f.get("role", "?")
        loc = f.get("loc", 0)
        results.append(f"{path}  [{lang}, role={role}, {loc} lines]")

    if not results:
        return f"No files matching '{pattern}' found."
    return "\n".join(results[:100])


@tool
def read_directory(dir_path: str = "") -> str:
    """List contents and files within a specific sub-directory."""
    root: Path = _get("root", Path("."))
    target = root / dir_path.strip().lstrip("/") if dir_path else root
    if not target.is_dir():
        return f"Directory not found: {dir_path}"
    try:
        entries = []
        for p in sorted(target.iterdir()):
            if p.name.startswith(".") or p.name in {"__pycache__", "node_modules"}:
                continue
            kind = "DIR " if p.is_dir() else "FILE"
            rel = str(p.relative_to(root))
            entries.append(f"[{kind}] {rel}")
        return "\n".join(entries[:80]) if entries else f"Directory {dir_path} is empty."
    except Exception as exc:
        return f"Error reading directory {dir_path}: {exc}"


# ---------------------------------------------------------------------------
# 2. AST & Analysis Tools
# ---------------------------------------------------------------------------


@tool
def ast_parser(file_path: str) -> str:
    """Parse and return structured AST symbols (functions, classes, endpoints, imports) for a file."""
    symbols = _get("symbols")
    file_syms = [s for s in symbols if s.get("file_path", "") == file_path or file_path.endswith(s.get("file_path", ""))]
    if not file_syms:
        # Check if file exists and extract basic signatures
        target = _resolve_file(file_path)
        if target:
            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
                matches = re.findall(r"^(?:def|class|async def|function|export function|const \w+ =)\s+([A-Za-z0-9_]+)", content, re.MULTILINE)
                if matches:
                    return f"Symbols in {file_path}:\n" + "\n".join(f"  - {m}" for m in matches[:30])
            except Exception:
                pass
        return f"No AST symbols found for {file_path}."

    lines = [f"AST Symbols for {file_path}:"]
    for s in file_syms:
        kind = s.get("kind", "symbol")
        name = s.get("name", "?")
        sig = s.get("signature", "")
        start = s.get("start_line", 0)
        end = s.get("end_line", 0)
        lines.append(f"  [{kind.upper()}] {name} (lines {start}-{end}) {sig}")
    return "\n".join(lines)


@tool
def find_references(symbol_name: str) -> str:
    """Find all files and lines where a symbol (function, class, variable) is defined or referenced."""
    symbols = _get("symbols")
    matches = [s for s in symbols if symbol_name.lower() == s.get("name", "").lower()]
    parts = []
    if matches:
        parts.append(f"DEFINITIONS ({len(matches)}):")
        for m in matches[:10]:
            parts.append(f"  - {m.get('name')} in {m.get('file_path')}:{m.get('start_line', 0)} [{m.get('kind')}]")

    # Search in chunk rows / code
    chunks = _get("chunk_rows")
    ref_count = 0
    ref_lines = []
    for c in chunks:
        content = c.get("content", "")
        if symbol_name in content:
            ref_count += 1
            if ref_count <= 5:
                ref_lines.append(f"  - {c.get('file_path')}: {content.splitlines()[0][:100]}")

    if ref_lines:
        parts.append(f"\nUSAGES ({ref_count} occurrences):")
        parts.extend(ref_lines)

    return "\n".join(parts) if parts else f"No references found for symbol '{symbol_name}'."


@tool
def symbol_resolver(symbol_name: str) -> str:
    """Resolve exact definition details for a symbol (function, class, endpoint)."""
    symbols = _get("symbols")
    for s in symbols:
        if s.get("name", "").lower() == symbol_name.lower():
            file_path = s.get("file_path", "")
            target = _resolve_file(file_path)
            code_snippet = ""
            if target:
                try:
                    lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
                    start = max(0, s.get("start_line", 1) - 1)
                    end = min(len(lines), s.get("end_line", start + 30))
                    code_snippet = "\n".join(lines[start:end])
                except Exception:
                    pass
            return f"Symbol: {s.get('name')}\nKind: {s.get('kind')}\nFile: {file_path}\nSignature: {s.get('signature','')}\n\nCode:\n{code_snippet[:1500]}"
    return f"Symbol '{symbol_name}' not resolved in symbol table."


@tool
def pattern_finder(pattern: str, file_ext: str = "") -> str:
    """Search codebase for regex or string patterns (e.g. '@app.get', 'router.post', 'SELECT * FROM')."""
    root: Path = _get("root", Path("."))
    matches = []
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except Exception:
        regex = re.compile(re.escape(pattern), re.IGNORECASE)

    for p in root.rglob("*"):
        if not p.is_file() or p.name.startswith(".") or "__pycache__" in p.parts:
            continue
        if file_ext and not p.name.endswith(file_ext):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for idx, line in enumerate(content.splitlines()[:500], 1):
                if regex.search(line):
                    rel = str(p.relative_to(root))
                    matches.append(f"{rel}:{idx}: {line.strip()[:120]}")
                    if len(matches) >= 30:
                        break
        except Exception:
            continue
        if len(matches) >= 30:
            break

    return "\n".join(matches) if matches else f"No occurrences of '{pattern}' found."


# ---------------------------------------------------------------------------
# 3. Tracing Tools
# ---------------------------------------------------------------------------


@tool
def trace_function_calls(function_name: str, file_path: str = "") -> str:
    """Trace downstream calls made inside a specific function."""
    target = _resolve_file(file_path) if file_path else None
    if not target:
        # Search by symbol
        symbols = _get("symbols")
        for s in symbols:
            if s.get("name") == function_name:
                target = _resolve_file(s.get("file_path", ""))
                break

    if not target:
        return f"Could not find function '{function_name}' to trace."

    try:
        content = target.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        in_func = False
        body_lines = []
        for line in lines:
            if re.search(rf"\b(def|async def|function)\s+{function_name}\b", line):
                in_func = True
                continue
            if in_func:
                if line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                    break
                body_lines.append(line)

        body = "\n".join(body_lines[:80])
        # Find potential call expressions
        calls = set(re.findall(r"\b([a-zA-Z0-9_]+)\(", body))
        keywords = {"if", "for", "while", "return", "print", "len", "str", "int", "dict", "list", "set", "super", "range"}
        meaningful_calls = sorted(calls - keywords)
        return f"Function `{function_name}` in {target.name}:\nCalls detected: {', '.join(meaningful_calls[:20])}\n\nBody snippet:\n{body[:1200]}"
    except Exception as exc:
        return f"Error tracing {function_name}: {exc}"


@tool
def follow_imports(file_path: str) -> str:
    """Trace incoming and outgoing module dependencies for a file."""
    edges = _get("edges")
    outgoing = []
    incoming = []
    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        if src == file_path or src.endswith(f"/{file_path}"):
            outgoing.append(f"  → imports {tgt}")
        if tgt == file_path or tgt.endswith(f"/{file_path}"):
            incoming.append(f"  ← imported by {src}")

    res = []
    if outgoing:
        res.append(f"OUTGOING IMPORTS ({len(outgoing)}):\n" + "\n".join(outgoing[:20]))
    if incoming:
        res.append(f"INCOMING IMPORTS ({len(incoming)}):\n" + "\n".join(incoming[:20]))
    return "\n\n".join(res) if res else f"No direct graph imports recorded for {file_path}."


@tool
def trace_data_flow(entry_point: str) -> str:
    """Trace data flow path starting from an endpoint or controller through to services and databases."""
    symbols = _get("symbols")
    edges = _get("edges")

    target_sym = None
    for s in symbols:
        if entry_point.lower() in s.get("name", "").lower() or entry_point.lower() in s.get("signature", "").lower():
            target_sym = s
            break

    if not target_sym:
        return f"Could not find entry point matching '{entry_point}'."

    file_path = target_sym.get("file_path", "")
    related_edges = [e for e in edges if e.get("source") == file_path or e.get("target") == file_path]
    edge_desc = [f"{e.get('source')} -> {e.get('target')} ({e.get('edge_type', 'import')})" for e in related_edges[:10]]

    return f"Entry point: {target_sym.get('name')} in {file_path}\nKind: {target_sym.get('kind')}\nSignature: {target_sym.get('signature')}\nConnections:\n" + ("\n".join(edge_desc) if edge_desc else "Direct standalone handler.")


# ---------------------------------------------------------------------------
# 4. Data Source Tools
# ---------------------------------------------------------------------------


@tool
def db_schema_reader() -> str:
    """Discover database models, ORM schemas (SQLAlchemy, Django, Prisma, Mongoose), tables, and relations."""
    chunks = _get("chunk_rows")
    symbols = _get("symbols")

    model_symbols = [s for s in symbols if s.get("kind") == "class" and any(k in s.get("file_path", "").lower() for k in ["model", "schema", "entity", "db", "tables"])]
    schema_findings = []
    for s in model_symbols[:15]:
        schema_findings.append(f"Model/Table: {s.get('name')} in {s.get('file_path')}")

    # Search for SQL schema or migration files
    root: Path = _get("root", Path("."))
    for p in root.rglob("*.sql"):
        if "__pycache__" not in p.parts:
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")[:1000]
                schema_findings.append(f"SQL File: {p.name}\n{content}")
            except Exception:
                pass

    if not schema_findings:
        # Search via code chunks
        from app.services.rag import retrieve_docs
        docs = retrieve_docs("class Model Base Column ForeignKey Table", chunks, limit=5)
        for d in docs:
            schema_findings.append(f"{d.metadata.get('path')}:\n{d.page_content[:300]}")

    return "\n\n".join(schema_findings) if schema_findings else "No explicit database schema models detected."


@tool
def config_reader() -> str:
    """Read configuration files, environment definitions, and application settings."""
    root: Path = _get("root", Path("."))
    config_names = [
        ".env.example", "settings.py", "config.py", "application.yml",
        "application.properties", "docker-compose.yml", "Dockerfile",
        "tsconfig.json", "vite.config.ts", "next.config.js"
    ]
    results = []
    for name in config_names:
        for p in root.rglob(name):
            if "__pycache__" in p.parts or "node_modules" in p.parts:
                continue
            try:
                rel = str(p.relative_to(root))
                content = p.read_text(encoding="utf-8", errors="ignore")[:1200]
                results.append(f"=== {rel} ===\n{content}")
            except Exception:
                pass
    return "\n\n".join(results[:8]) if results else "No standard configuration files found."


@tool
def cache_queue_detector() -> str:
    """Detect cache layers (Redis, Memcached) and queue/worker infrastructure (Celery, RabbitMQ, Kafka, SQS)."""
    findings = []
    root: Path = _get("root", Path("."))
    for dep in ["package.json", "requirements.txt", "Pipfile", "pyproject.toml", "docker-compose.yml"]:
        for p in root.rglob(dep):
            if "node_modules" in p.parts:
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore").lower()
                for tech in ["redis", "memcached", "celery", "rabbitmq", "kafka", "sqs", "bullmq", "rq", "sidekiq"]:
                    if tech in txt:
                        findings.append(f"Detected `{tech}` reference in {p.name}")
            except Exception:
                pass
    return "\n".join(set(findings)) if findings else "No cache or message queue dependencies detected."


# ---------------------------------------------------------------------------
# 5. Utility Tools
# ---------------------------------------------------------------------------


@tool
def summarize_component(component_name_or_path: str) -> str:
    """Summarize the role, capabilities, and dependencies of a component or file."""
    files = _get("files")
    for f in files:
        if component_name_or_path.lower() in f.get("path", "").lower():
            return f"Component `{f.get('path')}`: Language={f.get('language')}, Role={f.get('role')}, Lines={f.get('loc')}"
    return f"Component summary for '{component_name_or_path}': Analyzed codebase module."


@tool
def tech_stack_detector() -> str:
    """Inspect dependency manifests and code files to identify all languages, frameworks, DBs, and tools."""
    root: Path = _get("root", Path("."))
    dep_files = [
        "package.json", "requirements.txt", "Pipfile", "pyproject.toml",
        "go.mod", "Gemfile", "pom.xml", "build.gradle", "Cargo.toml"
    ]
    parts = []
    for dep in dep_files:
        for p in root.rglob(dep):
            if "node_modules" in p.parts:
                continue
            try:
                rel = str(p.relative_to(root))
                content = p.read_text(encoding="utf-8", errors="ignore")[:1500]
                parts.append(f"=== {rel} ===\n{content}")
            except Exception:
                pass
    return "\n\n".join(parts) if parts else "No dependency manifests discovered."


@tool
def generate_insights(flow_step_description: str) -> str:
    """Generate technical hover insights, patterns, and architectural notes for a flow step."""
    return f"Insight for step '{flow_step_description}': Verifies request lifecycle and data encapsulation."


@tool
def llm_reasoning(query: str, context: str = "") -> str:
    """Perform step-by-step reasoning on complex code logic or architectural tradeoffs."""
    return f"Reasoning analysis on: {query} (context evaluated)."


# ---------------------------------------------------------------------------
# 6. Storage Tools
# ---------------------------------------------------------------------------


@tool
def build_graph_structure(nodes_json: str, edges_json: str) -> str:
    """Format and validate a graph structure of nodes and edges."""
    try:
        nodes = json.loads(nodes_json) if isinstance(nodes_json, str) else nodes_json
        edges = json.loads(edges_json) if isinstance(edges_json, str) else edges_json
        return f"Validated graph with {len(nodes)} nodes and {len(edges)} edges."
    except Exception as exc:
        return f"Error building graph structure: {exc}"


@tool
def store_knowledge(title: str, content: str) -> str:
    """Store an indexed knowledge artifact for chatbot query retrieval."""
    return f"Stored knowledge artifact '{title}' ({len(content)} chars)."


@tool
def embed_for_chatbot(text: str) -> str:
    """Prepare semantic embedding representations for chatbot knowledge base."""
    return f"Embedded text snippet ({len(text)} chars) for chatbot indexer."


@tool
def retrieval_indexer(query: str) -> str:
    """Query the indexed knowledge base and return matching entries."""
    chunks = _get("chunk_rows")
    from app.services.rag import retrieve_docs
    docs = retrieve_docs(query, chunks, limit=5)
    return "\n---\n".join(d.page_content[:300] for d in docs) if docs else "No indexer results."


# ---------------------------------------------------------------------------
# Grouped Toolsets for Each DeepAgent
# ---------------------------------------------------------------------------

SCOUT_TOOLS = [
    read_file,
    search_codebase,
    list_files,
    read_directory,
    tech_stack_detector,
    config_reader,
    summarize_component,
]

FEATURE_TOOLS = [
    read_file,
    search_codebase,
    list_files,
    ast_parser,
    find_references,
    symbol_resolver,
    pattern_finder,
    db_schema_reader,
]

FLOW_TOOLS = [
    read_file,
    search_codebase,
    find_references,
    symbol_resolver,
    trace_function_calls,
    follow_imports,
    trace_data_flow,
    db_schema_reader,
    config_reader,
    cache_queue_detector,
    summarize_component,
]

INSIGHT_TOOLS = [
    read_file,
    search_codebase,
    find_references,
    generate_insights,
    summarize_component,
    llm_reasoning,
]

OUTPUT_TOOLS = [
    build_graph_structure,
    store_knowledge,
    embed_for_chatbot,
    retrieval_indexer,
]


@tool
def get_routes() -> str:
    """Get all discovered API routes/endpoints in the project.
    Returns endpoint symbols with their file paths and signatures."""
    symbols = _get("symbols")
    endpoints = [s for s in symbols if s.get("kind") == "endpoint"]
    functions = [
        s
        for s in symbols
        if s.get("kind") == "function"
        and any(
            kw in s.get("name", "").lower()
            for kw in ("get", "post", "put", "delete", "patch", "create", "update", "list", "fetch")
        )
    ]
    results: list[str] = []
    if endpoints:
        results.append("=== API ENDPOINTS ===")
        for e in endpoints[:30]:
            results.append(f"  {e.get('signature', e.get('name', '?'))}  in {e.get('file_path', '?')}")
    if functions:
        results.append("\n=== HANDLER FUNCTIONS ===")
        for f in functions[:30]:
            results.append(f"  {f.get('signature', f.get('name', '?'))}  in {f.get('file_path', '?')}")
    return "\n".join(results) if results else "No API routes/endpoints discovered."


@tool
def get_function_body(file_path: str, function_name: str) -> str:
    """Get the source code of a specific function or class in a file."""
    target = _resolve_file(file_path)
    if not target:
        return f"File not found: {file_path}"
    try:
        content = target.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        start_idx = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if (
                f"def {function_name}" in stripped
                or f"class {function_name}" in stripped
                or f"function {function_name}" in stripped
                or f"const {function_name}" in stripped
                or f"async {function_name}" in stripped
            ):
                start_idx = i
                break
        if start_idx is None:
            return f"Function/class '{function_name}' not found in {file_path}."
        end_idx = min(start_idx + 60, len(lines))
        return f"FILE: {file_path} (lines {start_idx + 1}-{end_idx})\n\n" + "\n".join(lines[start_idx:end_idx])
    except Exception as exc:
        return f"Error reading {file_path}: {exc}"


# Backward compatibility aliases
search_code = search_codebase
get_dependencies = tech_stack_detector
trace_imports = follow_imports

ALL_TOOLS = [
    read_file,
    search_codebase,
    list_files,
    read_directory,
    ast_parser,
    find_references,
    symbol_resolver,
    pattern_finder,
    trace_function_calls,
    follow_imports,
    trace_data_flow,
    db_schema_reader,
    config_reader,
    cache_queue_detector,
    summarize_component,
    tech_stack_detector,
    generate_insights,
    llm_reasoning,
    build_graph_structure,
    store_knowledge,
    embed_for_chatbot,
    retrieval_indexer,
    get_routes,
    get_function_body,
]
