"""Full analysis pipeline: extract → analyze → chunk → embed → architecture."""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import (
    AnalysisJob,
    ArchitectureSnapshot,
    CodeChunk,
    DependencyEdge,
    DependencyNode,
    Project,
    ProjectFile,
    SessionLocal,
    Symbol,
    Upload,
    utcnow,
)
from app.services import analysis as an
from app.services.architecture import generate_architecture
from app.services.rag import embed_texts
from app.services.storage import download_to, safe_join, sha256_file

logger = logging.getLogger(__name__)

SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv"}


def _update_job(db: Session, job: AnalysisJob, *, stage: str, progress: float, status: str = "running", error: str = "") -> None:
    job.stage = stage
    job.progress = progress
    job.status = status
    job.error = error
    job.updated_at = utcnow()
    project = db.get(Project, job.project_id)
    if project:
        if status == "failed":
            project.status = "failed"
        elif stage == "ready" or status == "succeeded":
            project.status = "ready"
        else:
            project.status = "processing"
        project.updated_at = utcnow()
    db.commit()


def _should_skip(path: str) -> bool:
    parts = Path(path.replace("\\", "/")).parts
    if any(p in SKIP_DIRS for p in parts):
        return True
    name = Path(path).name
    if name.startswith(".") or name in {".DS_Store", "Thumbs.db"}:
        return True
    if path.replace("\\", "/").startswith("__MACOSX/"):
        return True
    return False


def _extract_zip(zip_path: Path, dest: Path) -> list[dict]:
    settings = get_settings()
    dest.mkdir(parents=True, exist_ok=True)
    files: list[dict] = []
    total = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir() or _should_skip(info.filename):
                continue
            target = safe_join(dest, info.filename)
            if target is None:
                continue
            total += info.file_size
            if total > settings.max_zip_bytes:
                raise ValueError("Extracted archive exceeds size limit")
            if len(files) >= settings.max_extracted_files:
                raise ValueError("Extracted archive exceeds file count limit")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
            try:
                text = target.read_text(encoding="utf-8", errors="ignore")
                loc = text.count("\n") + (1 if text else 0)
            except Exception:
                loc = 0
            files.append({"path": info.filename.replace("\\", "/"), "size": target.stat().st_size, "loc": loc, "abs": target})
    return files


def run_pipeline(job_id: str) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)
        if not job:
            return
        project = db.get(Project, job.project_id)
        if not project:
            return

        _update_job(db, job, stage="extracting", progress=0.05)
        upload = (
            db.query(Upload)
            .filter(Upload.project_id == project.id)
            .order_by(Upload.created_at.desc())
            .first()
        )
        if not upload:
            raise ValueError("No upload found")

        work = Path(settings.extract_root) / project.id
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        zip_path = work / "source.zip"
        extract_dir = work / "src"
        extract_dir.mkdir()

        download_to(upload.s3_key, zip_path)
        upload.checksum = sha256_file(zip_path)
        upload.size_bytes = zip_path.stat().st_size
        upload.status = "complete"
        db.commit()

        _update_job(db, job, stage="extracting", progress=0.15)
        extracted = _extract_zip(zip_path, extract_dir)

        children = [p for p in extract_dir.iterdir() if p.name != "__MACOSX"]
        root = extract_dir
        if len(children) == 1 and children[0].is_dir():
            root = children[0]

        records = []
        for item in extracted:
            abs_path = item["abs"]
            try:
                rel = str(abs_path.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = item["path"]
            records.append({**item, "path": rel, "abs": root / rel})

        # detect + analyze
        _update_job(db, job, stage="detecting", progress=0.3)
        db.query(ProjectFile).filter(ProjectFile.project_id == project.id).delete()
        analyzed = []
        for fr in records:
            if not fr["abs"].is_file():
                continue
            result = an.analyze_file(fr["path"], fr["abs"])
            analyzed.append(result)
            db.add(
                ProjectFile(
                    project_id=project.id,
                    path=result.path,
                    language=result.language,
                    size_bytes=fr["size"],
                    loc=result.loc,
                    role=result.role,
                    metadata_json=json.dumps({"imports": result.imports[:50]}),
                )
            )
        db.commit()

        _update_job(db, job, stage="analyzing", progress=0.45)
        nodes, edges = an.build_graph(analyzed)
        db.query(DependencyEdge).filter(DependencyEdge.project_id == project.id).delete()
        db.query(DependencyNode).filter(DependencyNode.project_id == project.id).delete()
        db.query(Symbol).filter(Symbol.project_id == project.id).delete()
        for n in nodes:
            db.add(
                DependencyNode(
                    project_id=project.id,
                    key=n["key"],
                    label=n["label"],
                    kind=n["kind"],
                    metadata_json=json.dumps(n.get("metadata") or {}),
                )
            )
        for e in edges:
            db.add(
                DependencyEdge(
                    project_id=project.id,
                    source_key=e["source"],
                    target_key=e["target"],
                    edge_type=e.get("edge_type", "import"),
                    metadata_json=json.dumps(e.get("metadata") or {}),
                )
            )
        for a in analyzed:
            for s in a.symbols:
                db.add(
                    Symbol(
                        project_id=project.id,
                        file_path=a.path,
                        name=s.name,
                        kind=s.kind,
                        start_line=s.start_line,
                        end_line=s.end_line,
                        signature=s.signature,
                    )
                )
        db.commit()

        # chunk + embed (LangChain embeddings via OpenRouter)
        _update_job(db, job, stage="chunking", progress=0.6)
        db.query(CodeChunk).filter(CodeChunk.project_id == project.id).delete()
        chunk_defs = []
        for a in analyzed:
            abs_path = root / a.path
            if not abs_path.is_file():
                continue
            for ch in an.chunk_file(a, abs_path):
                chunk_defs.append((a.path, ch))
        db.commit()

        _update_job(db, job, stage="embedding", progress=0.75)
        texts = [
            f"File: {path}\nSymbol: {ch.get('symbol_name','')}\n{ch['content']}"
            for path, ch in chunk_defs
        ]
        vectors = embed_texts(texts) if texts else []
        for i, (path, ch) in enumerate(chunk_defs):
            emb = vectors[i] if i < len(vectors) else []
            db.add(
                CodeChunk(
                    project_id=project.id,
                    file_path=path,
                    symbol_name=ch.get("symbol_name", ""),
                    language=ch.get("language", ""),
                    start_line=ch.get("start_line", 0),
                    end_line=ch.get("end_line", 0),
                    content=ch["content"],
                    metadata_json=json.dumps(ch.get("metadata") or {}),
                    embedding_json=json.dumps(emb),
                )
            )
        db.commit()

        _update_job(db, job, stage="indexed", progress=0.85)
        _update_job(db, job, stage="generating", progress=0.9)

        files = db.query(ProjectFile).filter(ProjectFile.project_id == project.id).all()
        symbols = db.query(Symbol).filter(Symbol.project_id == project.id).all()
        edge_rows = db.query(DependencyEdge).filter(DependencyEdge.project_id == project.id).all()
        edges_data = [{"source": e.source_key, "target": e.target_key} for e in edge_rows]
        chunks = db.query(CodeChunk).filter(CodeChunk.project_id == project.id).all()
        data = generate_architecture(project, files, symbols, edges_data, chunks)

        latest = (
            db.query(ArchitectureSnapshot)
            .filter(ArchitectureSnapshot.project_id == project.id)
            .order_by(ArchitectureSnapshot.version.desc())
            .first()
        )
        version = (latest.version + 1) if latest else 1
        db.add(
            ArchitectureSnapshot(
                project_id=project.id,
                version=version,
                summary=data.get("summary", ""),
                data_json=json.dumps(data),
            )
        )
        db.commit()

        _update_job(db, job, stage="ready", progress=1.0, status="succeeded")
    except Exception as exc:
        logger.exception("pipeline failed for %s", job_id)
        job = db.get(AnalysisJob, job_id)
        if job:
            _update_job(db, job, stage="failed", progress=1.0, status="failed", error=str(exc))
    finally:
        db.close()
