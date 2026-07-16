"""AST + static analysis pipeline using tree-sitter and regex fallbacks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from analysis.language import detect_language, infer_role


@dataclass
class AnalyzedFile:
    path: str
    language: str
    role: str
    loc: int
    imports: list[str] = field(default_factory=list)
    symbols: list[dict] = field(default_factory=list)


PYTHON_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)
JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[^'"]+\s+from\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))"""
)
PY_DEF_RE = re.compile(r"^\s*(async\s+)?def\s+(\w+)\s*\((.*?)\)\s*:", re.MULTILINE)
PY_CLASS_RE = re.compile(r"^\s*class\s+(\w+)\s*(?:\(|:)", re.MULTILINE)
JS_FUNC_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|"
    r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>|"
    r"(?:export\s+)?class\s+(\w+)"
)
DJANGO_URL_RE = re.compile(r"""path\(\s*['"]([^'"]+)['"]""")
FLASK_ROUTE_RE = re.compile(r"""@(?:\w+\.)?route\(\s*['"]([^'"]+)['"]""")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _python_analysis(path: str, content: str) -> AnalyzedFile:
    imports: list[str] = []
    for m in PYTHON_IMPORT_RE.finditer(content):
        imports.append(m.group(1) or m.group(2))
    symbols: list[dict] = []
    for m in PY_CLASS_RE.finditer(content):
        line = content[: m.start()].count("\n") + 1
        symbols.append(
            {
                "name": m.group(1),
                "kind": "class",
                "start_line": line,
                "end_line": line,
                "signature": f"class {m.group(1)}",
            }
        )
    for m in PY_DEF_RE.finditer(content):
        line = content[: m.start()].count("\n") + 1
        name = m.group(2)
        kind = "endpoint" if name in {"get", "post", "put", "patch", "delete"} else "function"
        symbols.append(
            {
                "name": name,
                "kind": kind,
                "start_line": line,
                "end_line": line,
                "signature": f"def {name}({m.group(3)})",
            }
        )
    for m in DJANGO_URL_RE.finditer(content):
        line = content[: m.start()].count("\n") + 1
        symbols.append(
            {
                "name": m.group(1),
                "kind": "endpoint",
                "start_line": line,
                "end_line": line,
                "signature": f"path('{m.group(1)}')",
            }
        )
    for m in FLASK_ROUTE_RE.finditer(content):
        line = content[: m.start()].count("\n") + 1
        symbols.append(
            {
                "name": m.group(1),
                "kind": "endpoint",
                "start_line": line,
                "end_line": line,
                "signature": f"route('{m.group(1)}')",
            }
        )
    lang = "python"
    return AnalyzedFile(
        path=path,
        language=lang,
        role=infer_role(path, lang),
        loc=content.count("\n") + (1 if content else 0),
        imports=imports,
        symbols=symbols,
    )


def _js_analysis(path: str, content: str, language: str) -> AnalyzedFile:
    imports: list[str] = []
    for m in JS_IMPORT_RE.finditer(content):
        imports.append(m.group(1) or m.group(2))
    symbols: list[dict] = []
    for m in JS_FUNC_RE.finditer(content):
        name = m.group(1) or m.group(2) or m.group(3)
        if not name:
            continue
        line = content[: m.start()].count("\n") + 1
        kind = "class" if m.group(3) else "function"
        symbols.append(
            {
                "name": name,
                "kind": kind,
                "start_line": line,
                "end_line": line,
                "signature": name,
            }
        )
    return AnalyzedFile(
        path=path,
        language=language,
        role=infer_role(path, language),
        loc=content.count("\n") + (1 if content else 0),
        imports=imports,
        symbols=symbols,
    )


def analyze_file(path: str, abs_path: Path) -> AnalyzedFile:
    content = _read_text(abs_path)
    language = detect_language(path, content)
    if language == "python":
        return _python_analysis(path, content)
    if language in {"javascript", "typescript"}:
        return _js_analysis(path, content, language)
    return AnalyzedFile(
        path=path,
        language=language,
        role=infer_role(path, language),
        loc=content.count("\n") + (1 if content else 0),
    )


def resolve_import_to_path(import_name: str, from_path: str, all_paths: set[str]) -> str | None:
    """Best-effort resolve relative / module imports to project paths."""
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
            str(base / f"{rel}.jsx"),
            str(base / rel / "index.ts"),
            str(base / rel / "index.js"),
        ]
        for c in candidates:
            norm = c.replace("\\", "/")
            if norm in all_paths:
                return norm
        return None

    # Absolute-ish module path within project
    dotted = import_name.replace(".", "/")
    candidates = [
        f"{dotted}.py",
        f"{dotted}/__init__.py",
        f"{dotted}.ts",
        f"{dotted}.js",
        f"src/{dotted}.ts",
        f"src/{dotted}.js",
    ]
    for c in candidates:
        if c in all_paths:
            return c
    # suffix match
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
            target = resolve_import_to_path(imp, a.path, all_paths)
            if not target or target == a.path:
                continue
            key = (a.path, target)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "source": a.path,
                    "target": target,
                    "edge_type": "import",
                    "metadata": {"import": imp},
                }
            )
    return nodes, edges
