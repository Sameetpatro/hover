"""Shared LangChain tools that all agents can use.

Each tool wraps existing Hover analysis data (RAG chunks, files, symbols,
dependency graph) into a format LangGraph agents can call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Tool context — set once per pipeline run, used by all tool functions.
# ---------------------------------------------------------------------------

_ctx: dict[str, Any] = {}


def set_tool_context(
    *,
    project_root: Path,
    files: list[dict],
    symbols: list[dict],
    edges: list[dict],
    chunk_rows: list[dict],
) -> None:
    """Inject data into tool context at the start of a pipeline run."""
    _ctx["root"] = project_root
    _ctx["files"] = files
    _ctx["symbols"] = symbols
    _ctx["edges"] = edges
    _ctx["chunk_rows"] = chunk_rows


def _get(key: str) -> Any:
    return _ctx.get(key, [])


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def search_code(query: str) -> str:
    """Search the codebase using RAG retrieval. Returns the most relevant
    code snippets matching the query (up to 10 results).
    Use this to find code related to a concept, feature, or pattern."""
    from app.services.rag import retrieve_docs

    docs = retrieve_docs(query, _get("chunk_rows"), limit=10)
    if not docs:
        return "No relevant code found for this query."
    parts: list[str] = []
    for d in docs:
        path = d.metadata.get("path", "?")
        sym = d.metadata.get("symbol", "")
        header = f"FILE: {path}" + (f" ({sym})" if sym else "")
        parts.append(f"{header}\n{d.page_content[:800]}")
    return "\n\n---\n\n".join(parts)


@tool
def read_file(file_path: str) -> str:
    """Read the full content of a specific file in the project.
    Use the relative path (e.g. 'app/main.py', 'src/index.ts')."""
    root: Path = _ctx.get("root", Path("."))
    target = root / file_path
    if not target.is_file():
        # Try common prefixes
        for prefix in ["", "src/", "app/", "backend/", "frontend/"]:
            alt = root / prefix / file_path
            if alt.is_file():
                target = alt
                break
        else:
            return f"File not found: {file_path}"
    try:
        content = target.read_text(encoding="utf-8", errors="ignore")
        if len(content) > 6000:
            content = content[:6000] + "\n... [truncated]"
        return content
    except Exception as exc:
        return f"Error reading {file_path}: {exc}"


@tool
def list_files(pattern: str = "") -> str:
    """List all project files, optionally filtered by a glob pattern.
    Examples: '*.py', 'routes/*', 'models/', 'controllers/*.ts'.
    Returns file paths, languages, and roles."""
    files = _get("files")
    if not files:
        return "No files available."
    results = []
    for f in files:
        path = f.get("path", "")
        if pattern and pattern not in path.lower():
            continue
        lang = f.get("language", "?")
        role = f.get("role", "?")
        loc = f.get("loc", 0)
        results.append(f"{path}  [{lang}, role={role}, {loc} lines]")
    if not results:
        return f"No files matching '{pattern}' found."
    return "\n".join(results[:80])


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
def trace_imports(file_path: str) -> str:
    """Trace what a file imports and what imports it.
    Shows direct dependencies (outgoing) and dependents (incoming)."""
    edges = _get("edges")
    outgoing: list[str] = []
    incoming: list[str] = []
    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        if src == file_path or src.endswith(f"/{file_path}"):
            outgoing.append(f"  → imports {tgt}")
        if tgt == file_path or tgt.endswith(f"/{file_path}"):
            incoming.append(f"  ← imported by {src}")
    parts = []
    if outgoing:
        parts.append(f"OUTGOING ({len(outgoing)}):\n" + "\n".join(outgoing[:20]))
    if incoming:
        parts.append(f"INCOMING ({len(incoming)}):\n" + "\n".join(incoming[:20]))
    return "\n\n".join(parts) if parts else f"No import relationships found for {file_path}."


@tool
def get_function_body(file_path: str, function_name: str) -> str:
    """Get the source code of a specific function or class in a file.
    Provide the relative file path and the function/class name."""
    root: Path = _ctx.get("root", Path("."))
    target = root / file_path
    if not target.is_file():
        for prefix in ["", "src/", "app/", "backend/"]:
            alt = root / prefix / file_path
            if alt.is_file():
                target = alt
                break
        else:
            return f"File not found: {file_path}"
    try:
        content = target.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return f"Cannot read {file_path}"

    lines = content.splitlines()
    # Find the function/class definition
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

    # Grab up to 60 lines from the definition
    end_idx = min(start_idx + 60, len(lines))
    snippet = "\n".join(lines[start_idx:end_idx])
    if len(snippet) > 3000:
        snippet = snippet[:3000] + "\n... [truncated]"
    return f"FILE: {file_path} (lines {start_idx + 1}-{end_idx})\n\n{snippet}"


@tool
def get_dependencies() -> str:
    """Read the project's dependency files (package.json, requirements.txt,
    go.mod, Gemfile, pom.xml, etc.) to identify the tech stack."""
    root: Path = _ctx.get("root", Path("."))
    dep_files = [
        "package.json",
        "requirements.txt",
        "Pipfile",
        "pyproject.toml",
        "go.mod",
        "Gemfile",
        "pom.xml",
        "build.gradle",
        "Cargo.toml",
        "composer.json",
    ]
    results: list[str] = []
    for dep in dep_files:
        target = root / dep
        if not target.is_file():
            # Check common subdirs
            for sub in ["", "backend/", "frontend/", "server/", "client/"]:
                alt = root / sub / dep
                if alt.is_file():
                    target = alt
                    break
            else:
                continue
        try:
            content = target.read_text(encoding="utf-8", errors="ignore")
            # Truncate large files
            if len(content) > 3000:
                content = content[:3000] + "\n... [truncated]"
            rel = str(target.relative_to(root))
            results.append(f"=== {rel} ===\n{content}")
        except Exception:
            pass
    return "\n\n".join(results) if results else "No dependency files found."


# Convenience list of all tools for agent binding
ALL_TOOLS = [
    search_code,
    read_file,
    list_files,
    get_routes,
    trace_imports,
    get_function_body,
    get_dependencies,
]
