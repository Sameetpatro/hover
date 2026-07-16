"""Symbol-aware code chunking."""

from __future__ import annotations

from pathlib import Path

from analysis.pipeline import AnalyzedFile


def chunk_file(analyzed: AnalyzedFile, abs_path: Path, max_chars: int = 1800) -> list[dict]:
    try:
        content = abs_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    lines = content.splitlines()
    chunks: list[dict] = []

    if analyzed.symbols:
        for sym in analyzed.symbols:
            start = max(sym.get("start_line", 1) - 1, 0)
            # Take a window of lines after symbol start
            end = min(start + 40, len(lines))
            body = "\n".join(lines[start:end])
            if len(body) > max_chars:
                body = body[:max_chars]
            if not body.strip():
                continue
            chunks.append(
                {
                    "symbol_name": sym.get("name", ""),
                    "language": analyzed.language,
                    "start_line": start + 1,
                    "end_line": end,
                    "content": body,
                    "metadata": {"kind": sym.get("kind", ""), "role": analyzed.role},
                }
            )

    # Always add a file-level overview chunk
    overview = "\n".join(lines[:80])
    if len(overview) > max_chars:
        overview = overview[:max_chars]
    if overview.strip():
        chunks.append(
            {
                "symbol_name": Path(analyzed.path).name,
                "language": analyzed.language,
                "start_line": 1,
                "end_line": min(80, len(lines)),
                "content": overview,
                "metadata": {"kind": "file", "role": analyzed.role},
            }
        )

    # Fallback: sliding windows for files without symbols
    if not analyzed.symbols and len(lines) > 80:
        for i in range(80, len(lines), 60):
            body = "\n".join(lines[i : i + 60])
            if not body.strip():
                continue
            chunks.append(
                {
                    "symbol_name": "",
                    "language": analyzed.language,
                    "start_line": i + 1,
                    "end_line": min(i + 60, len(lines)),
                    "content": body[:max_chars],
                    "metadata": {"kind": "window", "role": analyzed.role},
                }
            )
    return chunks
