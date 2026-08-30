"""Full analysis pipeline: 8-Stage LangGraph workflow with DeepAgents."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import (
    AnalysisJob,
    ArchitectureSnapshot,
    CodeChunk,
    DependencyEdge,
    DependencyNode,
    Feature,
    FeatureFlow,
    Project,
    ProjectFile,
    ProjectMeta,
    SessionLocal,
    Symbol,
    Upload,
    utcnow,
)
from app.services.agents.orchestrator import run_deep_analysis
from app.services.storage import download_to, sha256_file

logger = logging.getLogger(__name__)


def _update_job(
    db: Session,
    job: AnalysisJob,
    *,
    stage: str,
    progress: float,
    status: str = "running",
    error: str = "",
) -> None:
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


def run_pipeline(job_id: str) -> None:
    """Executes the full 8-stage LangGraph pipeline with DeepAgents."""
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
            raise ValueError("No upload found for project")

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

        def progress_cb(stage: str, progress: float) -> None:
            _update_job(db, job, stage=stage, progress=progress)

        # Execute the 8-Stage LangGraph Pipeline
        logger.info("🚀 Launching 8-Stage LangGraph Pipeline for %s", project.name)
        result = run_deep_analysis(
            project_id=project.id,
            project_name=project.name,
            project_root=str(extract_dir),
            zip_path=str(zip_path),
            extract_dir=str(extract_dir),
            on_progress=progress_cb,
        )

        _update_job(db, job, stage="storing", progress=0.92)

        # 1. Store Project Files, Symbols, Edges & Code Chunks
        db.query(ProjectFile).filter(ProjectFile.project_id == project.id).delete()
        db.query(Symbol).filter(Symbol.project_id == project.id).delete()
        db.query(DependencyEdge).filter(DependencyEdge.project_id == project.id).delete()
        db.query(DependencyNode).filter(DependencyNode.project_id == project.id).delete()
        db.query(CodeChunk).filter(CodeChunk.project_id == project.id).delete()

        # Re-fetch files & symbols from disk if needed or store from stage 2
        from app.services.agents.tools import _ctx
        files_data = _ctx.get("files", [])
        symbols_data = _ctx.get("symbols", [])
        edges_data = _ctx.get("edges", [])
        chunk_rows = _ctx.get("chunk_rows", [])

        for f in files_data:
            db.add(
                ProjectFile(
                    project_id=project.id,
                    path=f.get("path", ""),
                    language=f.get("language", ""),
                    size_bytes=f.get("size_bytes", 0),
                    loc=f.get("loc", 0),
                    role=f.get("role", "other"),
                    metadata_json=json.dumps({"imports": f.get("imports", [])}),
                )
            )

        for s in symbols_data:
            db.add(
                Symbol(
                    project_id=project.id,
                    file_path=s.get("file_path", ""),
                    name=s.get("name", ""),
                    kind=s.get("kind", "symbol"),
                    start_line=s.get("start_line", 0),
                    end_line=s.get("end_line", 0),
                    signature=s.get("signature", ""),
                )
            )

        for e in edges_data:
            db.add(
                DependencyEdge(
                    project_id=project.id,
                    source_key=e.get("source", ""),
                    target_key=e.get("target", ""),
                    edge_type=e.get("edge_type", "import"),
                    metadata_json=json.dumps({}),
                )
            )

        for c in chunk_rows:
            emb = c.get("embedding", [])
            db.add(
                CodeChunk(
                    project_id=project.id,
                    file_path=c.get("file_path", ""),
                    symbol_name=c.get("symbol_name", ""),
                    language=c.get("language", ""),
                    start_line=c.get("start_line", 0),
                    end_line=c.get("end_line", 0),
                    content=c.get("content", ""),
                    metadata_json=json.dumps({}),
                    embedding_json=json.dumps(emb) if isinstance(emb, list) else str(emb),
                )
            )
        db.commit()

        # 2. Store Architecture Snapshot
        arch_data = result.get("architecture_data", {})
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
                summary=arch_data.get("summary", ""),
                data_json=json.dumps(arch_data),
            )
        )

        # 3. Store Discovered Features
        db.query(FeatureFlow).filter(FeatureFlow.project_id == project.id).delete()
        db.query(Feature).filter(Feature.project_id == project.id).delete()
        db.query(ProjectMeta).filter(ProjectMeta.project_id == project.id).delete()
        db.commit()

        feature_map: dict[str, str] = {}
        for feat in result.get("features", []):
            db_feat = Feature(
                project_id=project.id,
                feature_key=feat.get("id", ""),
                name=feat.get("name", ""),
                description=feat.get("description", ""),
                method=feat.get("method", ""),
                path=feat.get("path", ""),
                entry_file=feat.get("entry_file", ""),
                entry_function=feat.get("entry_function", ""),
                category=feat.get("category", "general"),
                color=feat.get("color", "#60a5fa"),
            )
            db.add(db_feat)
            db.flush()
            feature_map[feat.get("id", "")] = db_feat.id

        # 4. Store Feature Flows & Insights
        insights_by_feat: dict[str, list] = {}
        for ins in result.get("insights", []):
            fid = ins.get("feature_id", "")
            insights_by_feat.setdefault(fid, []).append(ins)

        for flow in result.get("feature_flows", []):
            agent_feat_id = flow.get("feature_id", "")
            db_feat_id = feature_map.get(agent_feat_id, "")
            if not db_feat_id:
                continue
            flow_insights = insights_by_feat.get(agent_feat_id, [])
            db.add(
                FeatureFlow(
                    project_id=project.id,
                    feature_id=db_feat_id,
                    nodes_json=json.dumps(flow.get("nodes", [])),
                    edges_json=json.dumps(flow.get("edges", [])),
                    insights_json=json.dumps(flow_insights),
                )
            )

        # 5. Store Metadata & Tech Stack
        metadata = result.get("metadata", {})
        profile = result.get("profile", {})
        db.add(
            ProjectMeta(
                project_id=project.id,
                profile_json=json.dumps(profile),
                tech_stack_json=json.dumps(metadata.get("tech_stack", [])),
                system_design=metadata.get("system_design", ""),
                patterns_json=json.dumps(metadata.get("patterns", [])),
                db_schema_json=json.dumps(metadata.get("db_schema", [])),
            )
        )
        db.commit()

        _update_job(db, job, stage="ready", progress=1.0, status="succeeded")
        logger.info("✅ 8-Stage Pipeline successfully processed and persisted for %s", project.id)

    except Exception as exc:
        logger.exception("8-Stage Pipeline failed for %s", job_id)
        job = db.get(AnalysisJob, job_id)
        if job:
            _update_job(db, job, stage="failed", progress=1.0, status="failed", error=str(exc))
    finally:
        db.close()
