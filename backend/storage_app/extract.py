"""Safe ZIP extraction utilities."""

from __future__ import annotations

import zipfile
from pathlib import Path

from django.conf import settings


SKIP_PREFIXES = (
    "__MACOSX/",
    ".",
)
SKIP_NAMES = {".DS_Store", "Thumbs.db"}
SKIP_DIR_PARTS = {"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv"}


def is_safe_member(member: zipfile.ZipInfo, dest_root: Path) -> bool:
    name = member.filename.replace("\\", "/")
    if name.startswith("/") or ".." in Path(name).parts:
        return False
    target = (dest_root / name).resolve()
    try:
        target.relative_to(dest_root.resolve())
    except ValueError:
        return False
    return True


def should_skip(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if any(normalized.startswith(p) for p in SKIP_PREFIXES if p != "."):
        return True
    parts = Path(normalized).parts
    if any(part in SKIP_DIR_PARTS for part in parts):
        return True
    if Path(normalized).name in SKIP_NAMES:
        return True
    if Path(normalized).name.startswith("."):
        return True
    return False


def extract_zip(zip_path: Path, dest_root: Path) -> list[dict]:
    dest_root.mkdir(parents=True, exist_ok=True)
    files: list[dict] = []
    max_bytes = settings.MAX_ZIP_BYTES
    max_files = settings.MAX_EXTRACTED_FILES
    total_uncompressed = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir() or should_skip(info.filename):
                continue
            if not is_safe_member(info, dest_root):
                continue
            total_uncompressed += info.file_size
            if total_uncompressed > max_bytes:
                raise ValueError("Extracted archive exceeds size limit")
            if len(files) >= max_files:
                raise ValueError("Extracted archive exceeds file count limit")

            zf.extract(info, dest_root)
            rel = info.filename.replace("\\", "/")
            abs_path = dest_root / rel
            if not abs_path.is_file():
                continue
            try:
                text = abs_path.read_text(encoding="utf-8", errors="ignore")
                loc = text.count("\n") + (1 if text else 0)
            except Exception:
                loc = 0
            files.append(
                {
                    "path": rel,
                    "size_bytes": abs_path.stat().st_size,
                    "loc": loc,
                }
            )
    return files
