"""FastAPI routes — same /api contract the React frontend expects."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.db import (
    AnalysisJob,
    ArchitectureSnapshot,
    DependencyEdge,
    DependencyNode,
    Feature,
    FeatureFlow,
    Project,
    ProjectFile,
    ProjectMeta,
    Symbol,
    Upload,
    get_db,
    utcnow,
)
from app.schemas import ArchitectureOut, CompleteUploadIn, JobOut, ProjectCreate, ProjectOut
from app.services.architecture import generate_architecture
from app.services.storage import save_bytes
from app.services.worker import enqueue_job

router = APIRouter(prefix="/api")


@router.api_route("/health", methods=["GET", "HEAD"])
@router.api_route("/health/", methods=["GET", "HEAD"])
def api_health():
    """API health — GET + HEAD for probes and the frontend."""
    return Response(content='{"status":"ok"}', media_type="application/json", status_code=200)


def clear_all_previous_data(db: Session, keep_project_id: str | None = None) -> None:
    """Wipes all previously analysed project data from database and disk storage."""
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
        ProjectChatMessage,
        ProjectFile,
        ProjectMeta,
        Symbol,
        Upload,
    )
    import shutil

    # 1. Clear database records
    if keep_project_id:
        db.query(ProjectChatMessage).filter(ProjectChatMessage.project_id != keep_project_id).delete()
        db.query(ProjectMeta).filter(ProjectMeta.project_id != keep_project_id).delete()
        db.query(FeatureFlow).filter(FeatureFlow.project_id != keep_project_id).delete()
        db.query(Feature).filter(Feature.project_id != keep_project_id).delete()
        db.query(ArchitectureSnapshot).filter(ArchitectureSnapshot.project_id != keep_project_id).delete()
        db.query(CodeChunk).filter(CodeChunk.project_id != keep_project_id).delete()
        db.query(Symbol).filter(Symbol.project_id != keep_project_id).delete()
        db.query(DependencyEdge).filter(DependencyEdge.project_id != keep_project_id).delete()
        db.query(DependencyNode).filter(DependencyNode.project_id != keep_project_id).delete()
        db.query(ProjectFile).filter(ProjectFile.project_id != keep_project_id).delete()
        db.query(AnalysisJob).filter(AnalysisJob.project_id != keep_project_id).delete()
        db.query(Upload).filter(Upload.project_id != keep_project_id).delete()
        db.query(Project).filter(Project.id != keep_project_id).delete()
    else:
        db.query(ProjectChatMessage).delete()
        db.query(ProjectMeta).delete()
        db.query(FeatureFlow).delete()
        db.query(Feature).delete()
        db.query(ArchitectureSnapshot).delete()
        db.query(CodeChunk).delete()
        db.query(Symbol).delete()
        db.query(DependencyEdge).delete()
        db.query(DependencyNode).delete()
        db.query(ProjectFile).delete()
        db.query(AnalysisJob).delete()
        db.query(Upload).delete()
        db.query(Project).delete()
    db.commit()

    # 2. Clear disk storage
    settings = get_settings()
    for folder in [settings.extract_root, settings.media_root]:
        dir_path = Path(folder)
        if dir_path.exists():
            for item in dir_path.iterdir():
                if keep_project_id and item.name.startswith(keep_project_id):
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                except Exception:
                    pass

    # 3. Clear in-memory agent tools cache
    try:
        from app.services.agents.tools import _ctx
        _ctx.clear()
    except Exception:
        pass


@router.post("/projects/reset/")
def reset_all_projects(db: Session = Depends(get_db)):
    """Clear all previously analysed files and start fresh."""
    clear_all_previous_data(db)
    return {"status": "ok", "message": "All previous analysed project data cleared"}


@router.get("/projects/", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.post("/projects/", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    # Automatically clear previously analysed data upon new project creation
    clear_all_previous_data(db)

    name = (body.name or "").strip() or "Untitled Project"
    project = Project(name=name, status="created")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}/", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Not found")
    return project


@router.post("/projects/{project_id}/uploads/", status_code=201)
async def create_upload(
    project_id: str,
    file: UploadFile = File(...),
    filename: str | None = Form(None),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Not found")

    name = filename or file.filename or "project.zip"
    key = f"projects/{project_id}/{uuid.uuid4().hex}_{Path(name).name}"
    data = await file.read()
    save_bytes(key, data)

    upload = Upload(
        project_id=project_id,
        s3_key=key,
        original_filename=name,
        size_bytes=len(data),
        status="uploaded",
    )
    db.add(upload)
    project.status = "uploading"
    project.updated_at = utcnow()
    db.commit()
    db.refresh(upload)
    return {"upload_id": upload.id, "s3_key": key, "direct": True}


@router.post("/projects/{project_id}/uploads/complete/", response_model=JobOut, status_code=202)
def complete_upload(project_id: str, body: CompleteUploadIn, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Not found")

    upload = None
    if body.upload_id:
        upload = db.get(Upload, body.upload_id)
    if not upload:
        upload = (
            db.query(Upload)
            .filter(Upload.project_id == project_id)
            .order_by(Upload.created_at.desc())
            .first()
        )
    if not upload or upload.project_id != project_id:
        raise HTTPException(400, "No upload found")

    upload.status = "uploaded"
    job = AnalysisJob(project_id=project_id, status="queued", stage="queued", progress=0.0)
    db.add(job)
    project.status = "queued"
    project.updated_at = utcnow()
    db.commit()
    db.refresh(job)

    enqueue_job(job.id)
    return job


@router.get("/jobs/{job_id}/", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Not found")
    return job


@router.get("/projects/{project_id}/tree/")
def project_tree(project_id: str, db: Session = Depends(get_db)):
    files = (
        db.query(ProjectFile)
        .filter(ProjectFile.project_id == project_id)
        .order_by(ProjectFile.path)
        .all()
    )
    return {
        "project_id": project_id,
        "files": [
            {
                "id": f.id,
                "path": f.path,
                "language": f.language,
                "size_bytes": f.size_bytes,
                "loc": f.loc,
                "role": f.role,
                "metadata": json.loads(f.metadata_json or "{}"),
            }
            for f in files
        ],
        "count": len(files),
    }


@router.get("/projects/{project_id}/graph/")
def project_graph(project_id: str, db: Session = Depends(get_db)):
    nodes = db.query(DependencyNode).filter(DependencyNode.project_id == project_id).all()
    edges = db.query(DependencyEdge).filter(DependencyEdge.project_id == project_id).all()
    return {
        "nodes": [
            {
                "id": n.id,
                "key": n.key,
                "label": n.label,
                "kind": n.kind,
                "metadata": json.loads(n.metadata_json or "{}"),
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": e.id,
                "source": e.source_key,
                "target": e.target_key,
                "edge_type": e.edge_type,
                "metadata": json.loads(e.metadata_json or "{}"),
            }
            for e in edges
        ],
    }


@router.get("/projects/{project_id}/symbols/")
def project_symbols(project_id: str, db: Session = Depends(get_db)):
    symbols = db.query(Symbol).filter(Symbol.project_id == project_id).limit(2000).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "kind": s.kind,
            "file": s.file_path,
            "start_line": s.start_line,
            "end_line": s.end_line,
            "signature": s.signature,
        }
        for s in symbols
    ]


@router.get("/projects/{project_id}/architecture/", response_model=ArchitectureOut)
def get_architecture(project_id: str, db: Session = Depends(get_db)):
    snap = (
        db.query(ArchitectureSnapshot)
        .filter(ArchitectureSnapshot.project_id == project_id)
        .order_by(ArchitectureSnapshot.version.desc())
        .first()
    )
    if not snap:
        raise HTTPException(404, "Architecture not generated yet")
    return ArchitectureOut(
        id=snap.id,
        version=snap.version,
        summary=snap.summary,
        data=json.loads(snap.data_json),
        created_at=snap.created_at,
    )


@router.post("/projects/{project_id}/architecture/generate/", response_model=ArchitectureOut, status_code=201)
def regenerate_architecture(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Not found")

    from app.db import CodeChunk

    files = db.query(ProjectFile).filter(ProjectFile.project_id == project_id).all()
    symbols = db.query(Symbol).filter(Symbol.project_id == project_id).all()
    edges = [
        {"source": e.source_key, "target": e.target_key}
        for e in db.query(DependencyEdge).filter(DependencyEdge.project_id == project_id).all()
    ]
    chunks = db.query(CodeChunk).filter(CodeChunk.project_id == project_id).all()
    data = generate_architecture(project, files, symbols, edges, chunks)

    latest = (
        db.query(ArchitectureSnapshot)
        .filter(ArchitectureSnapshot.project_id == project_id)
        .order_by(ArchitectureSnapshot.version.desc())
        .first()
    )
    version = (latest.version + 1) if latest else 1
    snap = ArchitectureSnapshot(
        project_id=project_id,
        version=version,
        summary=data.get("summary", ""),
        data_json=json.dumps(data),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return ArchitectureOut(
        id=snap.id,
        version=snap.version,
        summary=snap.summary,
        data=json.loads(snap.data_json),
        created_at=snap.created_at,
    )


# ---- DeepAgents endpoints ----


@router.get("/projects/{project_id}/features/")
def list_features(project_id: str, db: Session = Depends(get_db)):
    """List all features discovered by the Feature Agent."""
    features = (
        db.query(Feature)
        .filter(Feature.project_id == project_id)
        .order_by(Feature.created_at)
        .all()
    )
    return [
        {
            "id": f.id,
            "feature_key": f.feature_key,
            "name": f.name,
            "description": f.description,
            "method": f.method,
            "path": f.path,
            "entry_file": f.entry_file,
            "entry_function": f.entry_function,
            "category": f.category,
            "color": f.color,
        }
        for f in features
    ]


@router.get("/projects/{project_id}/features/{feature_id}/flow/")
def get_feature_flow(project_id: str, feature_id: str, db: Session = Depends(get_db)):
    """Get the complete flow graph + insights for a feature."""
    flow = (
        db.query(FeatureFlow)
        .filter(FeatureFlow.project_id == project_id, FeatureFlow.feature_id == feature_id)
        .first()
    )
    if not flow:
        raise HTTPException(404, "Flow not found")
    return {
        "id": flow.id,
        "feature_id": flow.feature_id,
        "nodes": json.loads(flow.nodes_json),
        "edges": json.loads(flow.edges_json),
        "insights": json.loads(flow.insights_json),
    }


@router.get("/projects/{project_id}/features/flows/")
def get_all_flows(project_id: str, db: Session = Depends(get_db)):
    """Get all feature flows for a project in one call."""
    features = (
        db.query(Feature)
        .filter(Feature.project_id == project_id)
        .order_by(Feature.created_at)
        .all()
    )
    flows = (
        db.query(FeatureFlow)
        .filter(FeatureFlow.project_id == project_id)
        .all()
    )
    flow_map = {f.feature_id: f for f in flows}
    result = []
    for feat in features:
        fl = flow_map.get(feat.id)
        result.append({
            "feature": {
                "id": feat.id,
                "feature_key": feat.feature_key,
                "name": feat.name,
                "description": feat.description,
                "method": feat.method,
                "path": feat.path,
                "color": feat.color,
                "category": feat.category,
            },
            "flow": {
                "nodes": json.loads(fl.nodes_json) if fl else [],
                "edges": json.loads(fl.edges_json) if fl else [],
                "insights": json.loads(fl.insights_json) if fl else [],
            } if fl else None,
        })
    return result


@router.get("/projects/{project_id}/metadata/")
def get_project_metadata(project_id: str, db: Session = Depends(get_db)):
    """Get tech stack, system design, and structural metadata."""
    meta = (
        db.query(ProjectMeta)
        .filter(ProjectMeta.project_id == project_id)
        .order_by(ProjectMeta.created_at.desc())
        .first()
    )
    if not meta:
        return {
            "tech_stack": [],
            "system_design": "",
            "patterns": [],
            "db_schema": [],
            "profile": {},
        }
    return {
        "tech_stack": json.loads(meta.tech_stack_json),
        "system_design": meta.system_design,
        "patterns": json.loads(meta.patterns_json),
        "db_schema": json.loads(meta.db_schema_json),
        "profile": json.loads(meta.profile_json),
    }


# ---- Codebase Chatbot with Memory ----

from app.schemas import ChatMessageIn, ChatMessageOut
from app.services.chat import answer_project_query, clear_conversation_history, get_conversation_history


@router.get("/projects/{project_id}/chat/", response_model=list[ChatMessageOut])
def get_chat_history(project_id: str, db: Session = Depends(get_db)):
    """Get previous chat messages for this project."""
    return get_conversation_history(db, project_id)


@router.post("/projects/{project_id}/chat/", response_model=ChatMessageOut)
def send_chat_message(project_id: str, body: ChatMessageIn, db: Session = Depends(get_db)):
    """Send a query to the Codebase AI Assistant (with tool use and conversation memory)."""
    try:
        return answer_project_query(db, project_id, body.message)
    except Exception as e:
        raise HTTPException(500, f"Chat processing failed: {str(e)}")


@router.delete("/projects/{project_id}/chat/")
def delete_chat_history(project_id: str, db: Session = Depends(get_db)):
    """Clear conversation history memory for this project."""
    clear_conversation_history(db, project_id)
    return {"message": "Chat history cleared"}

