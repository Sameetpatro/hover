import uuid

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from analysis.models import DependencyEdge, DependencyNode, Symbol
from architecture.generator import generate_architecture
from architecture.models import ArchitectureSnapshot
from jobs.models import AnalysisJob
from jobs.tasks import run_analysis_pipeline
from projects.models import Project, ProjectFile, Upload
from projects.serializers import (
    AnalysisJobSerializer,
    ArchitectureSnapshotSerializer,
    ProjectFileSerializer,
    ProjectSerializer,
)
from storage_app.s3 import (
    ensure_bucket,
    presigned_put_url,
    rewrite_presigned_for_browser,
    upload_fileobj,
)


@api_view(["GET", "POST"])
def project_list_create(request):
    if request.method == "GET":
        qs = Project.objects.all().order_by("-created_at")
        return Response(ProjectSerializer(qs, many=True).data)

    name = request.data.get("name") or "Untitled Project"
    project = Project.objects.create(name=name, status=Project.Status.CREATED)
    return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def project_detail(request, project_id):
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)
    return Response(ProjectSerializer(project).data)


@api_view(["POST"])
def create_upload(request, project_id):
    """Create upload record + optional presigned URL, or accept direct multipart file."""
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    ensure_bucket()
    filename = request.data.get("filename") or "project.zip"
    key = f"projects/{project.id}/{uuid.uuid4().hex}_{filename}"

    # Direct multipart upload path
    uploaded = request.FILES.get("file")
    if uploaded is not None:
        filename = getattr(uploaded, "name", None) or filename
        key = f"projects/{project.id}/{uuid.uuid4().hex}_{filename}"
        # Ensure stream is at start
        try:
            uploaded.seek(0)
        except Exception:
            pass
        upload_fileobj(key, uploaded)
        upload = Upload.objects.create(
            project=project,
            s3_key=key,
            original_filename=filename,
            size_bytes=getattr(uploaded, "size", 0) or 0,
            status=Upload.Status.UPLOADED,
        )
        project.status = Project.Status.UPLOADING
        project.save(update_fields=["status", "updated_at"])
        return Response(
            {
                "upload_id": str(upload.id),
                "s3_key": key,
                "direct": True,
            },
            status=201,
        )

    upload = Upload.objects.create(
        project=project,
        s3_key=key,
        original_filename=filename,
        status=Upload.Status.PENDING,
    )
    project.status = Project.Status.UPLOADING
    project.save(update_fields=["status", "updated_at"])

    url = rewrite_presigned_for_browser(presigned_put_url(key))
    return Response(
        {
            "upload_id": str(upload.id),
            "s3_key": key,
            "presigned_url": url,
            "direct_upload": url is None or settings.USE_LOCAL_STORAGE,
        },
        status=201,
    )


@api_view(["POST"])
def complete_upload(request, project_id):
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    upload_id = request.data.get("upload_id")
    upload = None
    if upload_id:
        upload = project.uploads.filter(id=upload_id).first()
    if not upload:
        upload = project.uploads.order_by("-created_at").first()
    if not upload:
        return Response({"detail": "No upload found"}, status=400)

    upload.status = Upload.Status.UPLOADED
    upload.save(update_fields=["status"])

    job = AnalysisJob.objects.create(
        project=project,
        status=AnalysisJob.Status.QUEUED,
        stage=AnalysisJob.Stage.QUEUED,
        progress=0.0,
    )
    project.status = Project.Status.QUEUED
    project.save(update_fields=["status", "updated_at"])

    async_result = run_analysis_pipeline.delay(str(job.id))
    job.celery_task_id = async_result.id or ""
    job.save(update_fields=["celery_task_id"])

    return Response(AnalysisJobSerializer(job).data, status=202)


@api_view(["GET"])
def job_detail(request, job_id):
    try:
        job = AnalysisJob.objects.select_related("project").get(id=job_id)
    except AnalysisJob.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)
    return Response(AnalysisJobSerializer(job).data)


@api_view(["GET"])
def project_jobs(request, project_id):
    jobs = AnalysisJob.objects.filter(project_id=project_id).order_by("-created_at")
    return Response(AnalysisJobSerializer(jobs, many=True).data)


@api_view(["GET"])
def project_tree(request, project_id):
    files = ProjectFile.objects.filter(project_id=project_id).order_by("path")
    return Response(
        {
            "project_id": str(project_id),
            "files": ProjectFileSerializer(files, many=True).data,
            "count": files.count(),
        }
    )


@api_view(["GET"])
def project_graph(request, project_id):
    nodes = DependencyNode.objects.filter(project_id=project_id)
    edges = DependencyEdge.objects.filter(project_id=project_id).select_related(
        "source", "target"
    )
    return Response(
        {
            "nodes": [
                {
                    "id": str(n.id),
                    "key": n.key,
                    "label": n.label,
                    "kind": n.kind,
                    "metadata": n.metadata,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": str(e.id),
                    "source": e.source.key,
                    "target": e.target.key,
                    "edge_type": e.edge_type,
                    "metadata": e.metadata,
                }
                for e in edges
            ],
        }
    )


@api_view(["GET"])
def project_symbols(request, project_id):
    symbols = Symbol.objects.filter(project_id=project_id).select_related("file")[:2000]
    return Response(
        [
            {
                "id": str(s.id),
                "name": s.name,
                "kind": s.kind,
                "file": s.file.path,
                "start_line": s.start_line,
                "end_line": s.end_line,
                "signature": s.signature,
            }
            for s in symbols
        ]
    )


@api_view(["GET"])
def project_architecture(request, project_id):
    snap = (
        ArchitectureSnapshot.objects.filter(project_id=project_id)
        .order_by("-version")
        .first()
    )
    if not snap:
        return Response({"detail": "Architecture not generated yet"}, status=404)
    return Response(ArchitectureSnapshotSerializer(snap).data)


@api_view(["POST"])
def generate_project_architecture(request, project_id):
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    data = generate_architecture(project)
    latest = (
        ArchitectureSnapshot.objects.filter(project=project).order_by("-version").first()
    )
    version = (latest.version + 1) if latest else 1
    snap = ArchitectureSnapshot.objects.create(
        project=project,
        version=version,
        data=data,
        summary=data.get("summary", ""),
    )
    return Response(ArchitectureSnapshotSerializer(snap).data, status=201)


@api_view(["GET"])
def health(request):
    return Response({"status": "ok", "service": "hover"})
