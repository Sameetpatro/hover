"""Simple static analysis: language, role, imports, symbols, graph, chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

EXT_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown",
    ".sh": "shell",
}

PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
JS_IMPORT = re.compile(
    r"""(?:import\s+(?:[^'"]+\s+from\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))"""
)
PY_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\((.*?)\)\s*:", re.M)
PY_CLASS = re.compile(r"^\s*class\s+(\w+)\s*(?:\(|:)", re.M)
JS_FUNC = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|"
    r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>|"
    r"(?:export\s+)?class\s+(\w+)"
)
DJANGO_URL = re.compile(r"""path\(\s*['"]([^'"]+)['"]""")
FLASK_ROUTE = re.compile(r"""@(?:\w+\.)?route\(\s*['"]([^'"]+)['"]""")


@dataclass
class Symbol:
    name: str
    kind: str
    start_line: int
    end_line: int
    signature: str = ""


@dataclass
class AnalyzedFile:
    path: str
    language: str
    role: str
    loc: int
    imports: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)


def detect_language(path: str, content: str = "") -> str:
    name = Path(path).name.lower()
    if name == "dockerfile" or name.startswith("dockerfile"):
        return "dockerfile"
    lang = EXT_LANG.get(Path(path).suffix.lower(), "")
    if lang:
        return lang
    if content.lstrip().startswith("#!"):
        shebang = content.split("\n", 1)[0].lower()
        if "python" in shebang:
            return "python"
        if "node" in shebang or "bash" in shebang:
            return "shell"
    return "unknown"


def infer_role(path: str, language: str) -> str:
    lower = path.lower().replace("\\", "/")
    name = Path(lower).name
    if any(x in lower for x in ("migration", "models.py", "/db/", "repository", "prisma")):
        return "db"
    if any(x in lower for x in ("controller", "views.py", "urls.py", "routes", "api/", "handlers")):
        return "api"
    if any(x in lower for x in ("component", "pages/", "frontend", "ui/", ".tsx", ".jsx")):
        return "ui"
    if any(x in lower for x in ("worker", "celery", "task", "queue", "consumer")):
        return "worker"
    if any(x in lower for x in ("config", "settings", "docker", "package.json", "requirements")):
        return "config"
    if language in {"html", "css"}:
        return "ui"
    if name in {"main.py", "app.py", "index.ts", "index.js", "manage.py", "server.js", "main.go"}:
        return "entry"
    return "logic"


def _line_at(content: str, idx: int) -> int:
    return content[:idx].count("\n") + 1


def analyze_file(path: str, abs_path: Path) -> AnalyzedFile:
    try:
        content = abs_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        content = ""
    language = detect_language(path, content)
    af = AnalyzedFile(
        path=path,
        language=language,
        role=infer_role(path, language),
        loc=content.count("\n") + (1 if content else 0),
    )
    if language == "python":
        for m in PY_IMPORT.finditer(content):
            af.imports.append(m.group(1) or m.group(2))
        for m in PY_CLASS.finditer(content):
            line = _line_at(content, m.start())
            af.symbols.append(Symbol(m.group(1), "class", line, line, f"class {m.group(1)}"))
        for m in PY_DEF.finditer(content):
            line = _line_at(content, m.start())
            af.symbols.append(Symbol(m.group(1), "function", line, line, f"def {m.group(1)}({m.group(2)})"))
        for m in DJANGO_URL.finditer(content):
            line = _line_at(content, m.start())
            af.symbols.append(Symbol(m.group(1), "endpoint", line, line, f"path('{m.group(1)}')"))
        for m in FLASK_ROUTE.finditer(content):
            line = _line_at(content, m.start())
            af.symbols.append(Symbol(m.group(1), "endpoint", line, line, f"route('{m.group(1)}')"))
    elif language in {"javascript", "typescript"}:
        for m in JS_IMPORT.finditer(content):
            af.imports.append(m.group(1) or m.group(2))
        for m in JS_FUNC.finditer(content):
            name = m.group(1) or m.group(2) or m.group(3)
            if not name:
                continue
            line = _line_at(content, m.start())
            kind = "class" if m.group(3) else "function"
            af.symbols.append(Symbol(name, kind, line, line, name))
    return af


def resolve_import(import_name: str, from_path: str, all_paths: set[str]) -> str | None:
    if not import_name:
        return None
    if import_name.startswith("."):
        base = Path(from_path).parent
        rel = import_name
        while rel.startswith(".."):
            base = base.parent
            rel = rel[3:] if rel.startswith("../") else rel[2:]
        rel = rel.lstrip("./")
        candidates = [
            str(base / f"{rel}.py"),
            str(base / rel / "__init__.py"),
            str(base / f"{rel}.ts"),
            str(base / f"{rel}.tsx"),
            str(base / f"{rel}.js"),
            str(base / rel / "index.ts"),
            str(base / rel / "index.js"),
        ]
        for c in candidates:
            norm = c.replace("\\", "/")
            if norm in all_paths:
                return norm
        return None
    dotted = import_name.replace(".", "/")
    for c in [f"{dotted}.py", f"{dotted}/__init__.py", f"{dotted}.ts", f"{dotted}.js", f"src/{dotted}.ts"]:
        if c in all_paths:
            return c
    for p in all_paths:
        if p.endswith(f"/{dotted}.py") or p.endswith(f"/{dotted}.ts"):
            return p
    return None


def build_graph(analyzed: list[AnalyzedFile]) -> tuple[list[dict], list[dict]]:
    all_paths = {a.path for a in analyzed}
    nodes = [
        {
            "key": a.path,
            "label": Path(a.path).name,
            "kind": a.role or "module",
            "metadata": {"language": a.language, "role": a.role, "loc": a.loc},
        }
        for a in analyzed
    ]
    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for a in analyzed:
        for imp in a.imports:
            target = resolve_import(imp, a.path, all_paths)
            if not target or target == a.path:
                continue
            key = (a.path, target)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": a.path, "target": target, "edge_type": "import", "metadata": {"import": imp}})
    return nodes, edges


def chunk_file(analyzed: AnalyzedFile, abs_path: Path, max_chars: int = 1800) -> list[dict]:
    try:
        content = abs_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    lines = content.splitlines()
    chunks: list[dict] = []
    for sym in analyzed.symbols:
        start = max(sym.start_line - 1, 0)
        end = min(start + 40, len(lines))
        body = "\n".join(lines[start:end])
        if len(body) > max_chars:
            body = body[:max_chars]
        if not body.strip():
            continue
        chunks.append(
            {
                "symbol_name": sym.name,
                "language": analyzed.language,
                "start_line": start + 1,
                "end_line": end,
                "content": body,
                "metadata": {"kind": sym.kind, "role": analyzed.role},
            }
        )
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
    return chunks
