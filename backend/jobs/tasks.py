"""Celery pipeline: extract → analyze → chunk → embed → architecture."""

from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def _update_job(job_id, *, stage=None, progress=None, status=None, error=None):
    from jobs.models import AnalysisJob
    from projects.models import Project

    job = AnalysisJob.objects.select_related("project").get(id=job_id)
    if stage is not None:
        job.stage = stage
    if progress is not None:
        job.progress = progress
    if status is not None:
        job.status = status
    if error is not None:
        job.error = error
    job.save()

    project = job.project
    if status == AnalysisJob.Status.FAILED:
        project.status = Project.Status.FAILED
        project.save(update_fields=["status", "updated_at"])
    elif stage == "ready" or status == AnalysisJob.Status.SUCCEEDED:
        project.status = Project.Status.READY
        project.save(update_fields=["status", "updated_at"])
    elif status == AnalysisJob.Status.RUNNING:
        project.status = Project.Status.PROCESSING
        project.save(update_fields=["status", "updated_at"])
    return job


@shared_task(bind=True, name="jobs.run_analysis_pipeline")
def run_analysis_pipeline(self, job_id: str):
    from analysis.models import DependencyEdge, DependencyNode, Symbol
    from analysis.pipeline import analyze_file, build_graph
    from architecture.generator import generate_architecture
    from architecture.models import ArchitectureSnapshot
    from indexing.chunker import chunk_file
    from indexing.embeddings import embed_texts
    from indexing.models import ChunkEmbedding, CodeChunk
    from jobs.models import AnalysisJob
    from projects.models import Project, ProjectFile, Upload
    from storage_app.extract import extract_zip
    from storage_app.s3 import download_to_path, sha256_file

    job = AnalysisJob.objects.select_related("project").get(id=job_id)
    project = job.project
    job.celery_task_id = self.request.id or ""
    job.status = AnalysisJob.Status.RUNNING
    job.stage = AnalysisJob.Stage.EXTRACTING
    job.progress = 0.05
    job.save()
    project.status = Project.Status.PROCESSING
    project.save(update_fields=["status", "updated_at"])

    try:
        upload = project.uploads.order_by("-created_at").first()
        if not upload:
            raise ValueError("No upload found for project")

        work_dir = Path(settings.EXTRACT_ROOT) / str(project.id)
        work_dir.mkdir(parents=True, exist_ok=True)
        zip_path = work_dir / "source.zip"
        extract_dir = work_dir / "src"
        if extract_dir.exists():
            import shutil

            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        download_to_path(upload.s3_key, zip_path)
        upload.checksum = sha256_file(zip_path)
        upload.size_bytes = zip_path.stat().st_size
        upload.status = Upload.Status.COMPLETE
        upload.save()

        _update_job(job_id, stage=AnalysisJob.Stage.EXTRACTING, progress=0.15)
        extracted = extract_zip(zip_path, extract_dir)

        # Collapse single top-level folder
        children = [p for p in extract_dir.iterdir() if p.name != "__MACOSX"]
        root = extract_dir
        if len(children) == 1 and children[0].is_dir():
            root = children[0]

        # Re-map paths relative to root
        file_records = []
        for item in extracted:
            abs_path = extract_dir / item["path"]
            try:
                rel = str(abs_path.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = item["path"]
            file_records.append({**item, "path": rel, "abs": root / rel})

        with transaction.atomic():
            ProjectFile.objects.filter(project=project).delete()
            ProjectFile.objects.bulk_create(
                [
                    ProjectFile(
                        project=project,
                        path=fr["path"],
                        size_bytes=fr["size_bytes"],
                        loc=fr["loc"],
                    )
                    for fr in file_records
                ]
            )

        # Detect + analyze
        _update_job(job_id, stage=AnalysisJob.Stage.DETECTING, progress=0.3)
        path_map = {pf.path: pf for pf in ProjectFile.objects.filter(project=project)}
        analyzed = []
        for fr in file_records:
            abs_path = fr["abs"]
            if not abs_path.is_file():
                continue
            result = analyze_file(fr["path"], abs_path)
            analyzed.append(result)
            pf = path_map.get(fr["path"])
            if pf:
                pf.language = result.language
                pf.role = result.role
                pf.loc = result.loc
                pf.metadata = {"imports": result.imports[:50]}
                pf.save(update_fields=["language", "role", "loc", "metadata"])

        _update_job(job_id, stage=AnalysisJob.Stage.ANALYZING, progress=0.45)
        nodes, edges = build_graph(analyzed)

        with transaction.atomic():
            DependencyEdge.objects.filter(project=project).delete()
            DependencyNode.objects.filter(project=project).delete()
            Symbol.objects.filter(project=project).delete()

            node_objs = {}
            for n in nodes:
                pf = path_map.get(n["key"])
                obj = DependencyNode.objects.create(
                    project=project,
                    file=pf,
                    key=n["key"],
                    label=n["label"],
                    kind=n["kind"],
                    metadata=n.get("metadata") or {},
                )
                node_objs[n["key"]] = obj

            DependencyEdge.objects.bulk_create(
                [
                    DependencyEdge(
                        project=project,
                        source=node_objs[e["source"]],
                        target=node_objs[e["target"]],
                        edge_type=e.get("edge_type", "import"),
                        metadata=e.get("metadata") or {},
                    )
                    for e in edges
                    if e["source"] in node_objs and e["target"] in node_objs
                ]
            )

            symbol_objs = []
            for a in analyzed:
                pf = path_map.get(a.path)
                if not pf:
                    continue
                for s in a.symbols:
                    symbol_objs.append(
                        Symbol(
                            project=project,
                            file=pf,
                            name=s["name"],
                            kind=s["kind"],
                            start_line=s.get("start_line", 0),
                            end_line=s.get("end_line", 0),
                            signature=s.get("signature", ""),
                            metadata={},
                        )
                    )
            Symbol.objects.bulk_create(symbol_objs, batch_size=500)

        # Chunk
        _update_job(job_id, stage=AnalysisJob.Stage.CHUNKING, progress=0.6)
        with transaction.atomic():
            ChunkEmbedding.objects.filter(project=project).delete()
            CodeChunk.objects.filter(project=project).delete()
            chunks_to_create = []
            for a in analyzed:
                pf = path_map.get(a.path)
                if not pf:
                    continue
                abs_path = root / a.path
                if not abs_path.is_file():
                    continue
                for ch in chunk_file(a, abs_path):
                    chunks_to_create.append(
                        CodeChunk(
                            project=project,
                            file=pf,
                            symbol_name=ch["symbol_name"],
                            language=ch["language"],
                            start_line=ch["start_line"],
                            end_line=ch["end_line"],
                            content=ch["content"],
                            metadata=ch.get("metadata") or {},
                        )
                    )
            CodeChunk.objects.bulk_create(chunks_to_create, batch_size=500)

        # Embed
        _update_job(job_id, stage=AnalysisJob.Stage.EMBEDDING, progress=0.75)
        chunks = list(CodeChunk.objects.filter(project=project))
        texts = [
            f"File: {c.file.path}\nSymbol: {c.symbol_name}\n{c.content}" for c in chunks
        ]
        vectors = embed_texts(texts) if texts else []
        ChunkEmbedding.objects.bulk_create(
            [
                ChunkEmbedding(chunk=c, project=project, embedding=v)
                for c, v in zip(chunks, vectors)
            ],
            batch_size=200,
        )

        _update_job(job_id, stage=AnalysisJob.Stage.INDEXED, progress=0.85)

        # Architecture
        _update_job(job_id, stage=AnalysisJob.Stage.GENERATING, progress=0.9)
        data = generate_architecture(project)
        latest = (
            ArchitectureSnapshot.objects.filter(project=project)
            .order_by("-version")
            .first()
        )
        version = (latest.version + 1) if latest else 1
        ArchitectureSnapshot.objects.create(
            project=project,
            version=version,
            data=data,
            summary=data.get("summary", ""),
        )

        _update_job(
            job_id,
            stage=AnalysisJob.Stage.READY,
            progress=1.0,
            status=AnalysisJob.Status.SUCCEEDED,
        )
        return {"project_id": str(project.id), "job_id": str(job_id)}
    except Exception as exc:
        logger.exception("Pipeline failed for job %s", job_id)
        _update_job(
            job_id,
            stage=AnalysisJob.Stage.FAILED,
            status=AnalysisJob.Status.FAILED,
            error=str(exc),
            progress=1.0,
        )
        raise
