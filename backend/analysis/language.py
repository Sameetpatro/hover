"""Language detection and role heuristics."""

from __future__ import annotations

from pathlib import Path

EXT_LANGUAGE = {
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
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".sh": "shell",
    ".dockerfile": "dockerfile",
}


def detect_language(path: str, content: str = "") -> str:
    p = Path(path)
    name = p.name.lower()
    if name == "dockerfile" or name.startswith("dockerfile"):
        return "dockerfile"
    if name == "makefile":
        return "makefile"
    lang = EXT_LANGUAGE.get(p.suffix.lower(), "")
    if lang:
        return lang
    if content.lstrip().startswith("#!"):
        shebang = content.split("\n", 1)[0].lower()
        if "python" in shebang:
            return "python"
        if "node" in shebang or "bash" in shebang or "sh" in shebang:
            return "shell"
    return "unknown"


def infer_role(path: str, language: str) -> str:
    lower = path.lower().replace("\\", "/")
    name = Path(lower).name
    if any(
        x in lower
        for x in (
            "migration",
            "models.py",
            "schema",
            "entity",
            "/db/",
            "repository",
            "prisma",
        )
    ):
        return "db"
    if any(
        x in lower
        for x in (
            "controller",
            "views.py",
            "urls.py",
            "routes",
            "api/",
            "handlers",
            "endpoint",
        )
    ):
        return "api"
    if any(
        x in lower
        for x in ("component", "pages/", "views/", "frontend", "ui/", ".tsx", ".jsx")
    ):
        return "ui"
    if any(x in lower for x in ("worker", "celery", "task", "job", "queue", "consumer")):
        return "worker"
    if any(
        x in lower
        for x in (
            "config",
            "settings",
            ".env",
            "docker",
            "package.json",
            "requirements",
            "pyproject",
        )
    ):
        return "config"
    if language in {"html", "css", "scss"}:
        return "ui"
    if name in {"main.py", "app.py", "index.ts", "index.js", "manage.py", "server.js"}:
        return "entry"
    return "logic"
