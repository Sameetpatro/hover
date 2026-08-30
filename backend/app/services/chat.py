"""Codebase Q&A Chatbot with Conversation Memory and Tool-Assisted Source Verification.

Answers user queries regarding their uploaded codebase (e.g. "does this project use Celery?",
"where is authentication implemented?"), citing exact files, line numbers, and code blocks.
Maintains persistent multi-turn chat history.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import (
    CodeChunk,
    DependencyEdge,
    Feature,
    Project,
    ProjectChatMessage,
    ProjectFile,
    ProjectMeta,
    Symbol,
)
from app.services.agents.tools import (
    get_dependencies,
    get_routes,
    list_files,
    read_file,
    search_code,
    set_tool_context,
)
from app.services.rag import get_chat_llm, retrieve_docs

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """You are the Hover AI Codebase Assistant. You are an expert software engineer with deep, direct access to the user's uploaded codebase.

Your mission:
1. Answer the user's questions about the project architecture, dependencies, technologies, code logic, endpoints, and workflows accurately and thoroughly.
2. CRITICAL: When the user asks if a technology, framework, database, library, or pattern is used (e.g., "Does this project use Celery?", "Where is Redis used?", "How are students fetched?"):
   - ALWAYS verify the codebase directly.
   - State clearly YES or NO.
   - Name the exact FILE PATH(S) and LINE NUMBERS where it is imported, configured, and used.
   - Quote the relevant code snippet(s) in markdown code blocks with line numbers.
3. Maintain conversational memory: remember previous questions and answers in this thread.
4. Keep your explanations clear, structured, and easy to understand with markdown headings, bullet points, and bold text."""


def read_file_with_line_numbers(project_root: Path, file_path: str, max_lines: int = 150) -> str:
    """Helper to read file and format with line numbers (e.g. ' 14: import celery')."""
    target = project_root / file_path
    if not target.is_file():
        for prefix in ["", "app/", "src/", "backend/"]:
            alt = project_root / prefix / file_path
            if alt.is_file():
                target = alt
                break
        else:
            return f"File not found: {file_path}"
    try:
        lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
        formatted = []
        for i, line in enumerate(lines[:max_lines], 1):
            formatted.append(f"{i:4d} | {line}")
        if len(lines) > max_lines:
            formatted.append(f"... [{len(lines) - max_lines} more lines]")
        return "\n".join(formatted)
    except Exception as exc:
        return f"Error reading {file_path}: {exc}"


def get_conversation_history(db: Session, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve chat history for a project ordered chronologically."""
    messages = (
        db.query(ProjectChatMessage)
        .filter(ProjectChatMessage.project_id == project_id)
        .order_by(ProjectChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": m.id,
            "project_id": m.project_id,
            "role": m.role,
            "content": m.content,
            "sources": json.loads(m.sources_json or "[]"),
            "created_at": m.created_at,
        }
        for m in messages
    ]


def answer_project_query(
    db: Session,
    project_id: str,
    user_query: str,
) -> dict[str, Any]:
    """Process user message, execute tool-assisted reasoning with memory, and save chat turn."""
    settings = get_settings()
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")

    # 1. Gather project context
    files = db.query(ProjectFile).filter(ProjectFile.project_id == project_id).all()
    symbols = db.query(Symbol).filter(Symbol.project_id == project_id).all()
    edges = db.query(DependencyEdge).filter(DependencyEdge.project_id == project_id).all()
    chunks = db.query(CodeChunk).filter(CodeChunk.project_id == project_id).all()
    meta = db.query(ProjectMeta).filter(ProjectMeta.project_id == project_id).first()
    features = db.query(Feature).filter(Feature.project_id == project_id).all()

    work_dir = Path(settings.extract_root) / project_id / "src"
    if not work_dir.exists():
        # Fallback to extract root
        work_dir = Path(settings.extract_root) / project_id

    # If single top directory in extract
    children = [p for p in work_dir.iterdir() if p.name != "__MACOSX" and p.is_dir()]
    if len(children) == 1 and (children[0] / "app").exists() or len(children) == 1 and (children[0] / "src").exists():
        work_dir = children[0]

    files_data = [{"path": f.path, "language": f.language, "role": f.role, "loc": f.loc} for f in files]
    symbols_data = [{"name": s.name, "kind": s.kind, "file_path": s.file_path, "signature": s.signature, "start_line": s.start_line, "end_line": s.end_line} for s in symbols]
    edges_data = [{"source": e.source_key, "target": e.target_key} for e in edges]
    chunk_rows = [
        {"content": c.content, "file_path": c.file_path, "symbol_name": c.symbol_name, "start_line": c.start_line, "end_line": c.end_line, "embedding": c.embedding_json}
        for c in chunks
    ]

    set_tool_context(
        project_root=work_dir,
        files=files_data,
        symbols=symbols_data,
        edges=edges_data,
        chunk_rows=chunk_rows,
    )

    # 2. Retrieve relevant code snippets via RAG
    relevant_docs = retrieve_docs(user_query, chunk_rows, limit=8)
    code_context_parts = []
    sources = []
    for d in relevant_docs:
        path = d.metadata.get("path", "")
        sym = d.metadata.get("symbol", "")
        code_context_parts.append(
            f"FILE: {path} (symbol: {sym})\n{d.page_content}"
        )
        sources.append({"file": path, "symbol": sym})

    code_context = "\n\n---\n\n".join(code_context_parts)

    # Project summary context
    tech_stack_text = meta.tech_stack_json if meta else "[]"
    features_summary = ", ".join([f"{f.method} {f.path}" for f in features if f.path])

    # 3. Load conversation memory
    past_messages = (
        db.query(ProjectChatMessage)
        .filter(ProjectChatMessage.project_id == project_id)
        .order_by(ProjectChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    past_messages.reverse()

    # 4. Generate Answer via LLM
    llm = get_chat_llm()
    if llm is not None:
        messages = [
            SystemMessage(content=CHAT_SYSTEM_PROMPT),
            SystemMessage(
                content=f"PROJECT: {project.name}\n"
                f"TECH STACK: {tech_stack_text}\n"
                f"DISCOVERED ENDPOINTS: {features_summary}\n\n"
                f"RELEVANT CODE SNIPPETS WITH LINE DATA:\n{code_context[:12000]}"
            ),
        ]

        # Append memory history
        for m in past_messages:
            if m.role == "user":
                messages.append(HumanMessage(content=m.content))
            else:
                messages.append(AIMessage(content=m.content))

        # Append current user prompt
        messages.append(HumanMessage(content=user_query))

        try:
            ai_res = llm.invoke(messages)
            assistant_reply = ai_res.content if isinstance(ai_res.content, str) else str(ai_res.content)
        except Exception as exc:
            logger.exception("Chat LLM invocation failed: %s", exc)
            assistant_reply = _heuristic_chat_fallback(user_query, files_data, chunk_rows, work_dir)
    else:
        assistant_reply = _heuristic_chat_fallback(user_query, files_data, chunk_rows, work_dir)

    # 5. Persist User and Assistant Messages in DB (Memory)
    user_msg = ProjectChatMessage(
        project_id=project_id,
        role="user",
        content=user_query,
        sources_json="[]",
    )
    db.add(user_msg)
    db.flush()

    assistant_msg = ProjectChatMessage(
        project_id=project_id,
        role="assistant",
        content=assistant_reply,
        sources_json=json.dumps(sources[:6]),
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return {
        "id": assistant_msg.id,
        "project_id": project_id,
        "role": "assistant",
        "content": assistant_reply,
        "sources": sources[:6],
        "created_at": assistant_msg.created_at,
    }


def _heuristic_chat_fallback(
    query: str,
    files: list[dict],
    chunks: list[dict],
    work_dir: Path,
) -> str:
    """Offline heuristic search when no LLM API key is present."""
    q = query.lower()
    matched_chunks = []
    for c in chunks:
        content = c.get("content", "")
        path = c.get("file_path", "")
        if any(term in content.lower() or term in path.lower() for term in q.split() if len(term) > 3):
            matched_chunks.append(c)

    if not matched_chunks:
        return (
            f"I scanned the codebase for **'{query}'**, but could not find direct matches in the extracted files. "
            "Please check if `OPENROUTER_API_KEY` is configured for in-depth AI reasoning."
        )

    top = matched_chunks[:3]
    lines = [f"Found relevant code references for **'{query}'**:\n"]
    for item in top:
        path = item.get("file_path", "?")
        start = item.get("start_line", 1)
        end = item.get("end_line", 30)
        lines.append(f"### 📄 `{path}` (lines {start}-{end})\n```python\n{item.get('content', '')[:600]}\n```\n")

    return "\n".join(lines)


def clear_conversation_history(db: Session, project_id: str) -> None:
    """Clear chat memory for a project."""
    db.query(ProjectChatMessage).filter(ProjectChatMessage.project_id == project_id).delete()
    db.commit()
