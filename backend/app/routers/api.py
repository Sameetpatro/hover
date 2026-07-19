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
    Project,
    ProjectFile,
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


@router.get("/projects/", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.post("/projects/", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
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
