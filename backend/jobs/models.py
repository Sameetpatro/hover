import uuid

from django.db import models

from projects.models import Project


class AnalysisJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    class Stage(models.TextChoices):
        QUEUED = "queued", "Queued"
        EXTRACTING = "extracting", "Extracting"
        DETECTING = "detecting", "Detecting languages"
        ANALYZING = "analyzing", "Static analysis"
        CHUNKING = "chunking", "Chunking"
        EMBEDDING = "embedding", "Embedding"
        INDEXED = "indexed", "Indexed"
        GENERATING = "generating", "Generating architecture"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="jobs")
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.QUEUED
    )
    stage = models.CharField(
        max_length=32, choices=Stage.choices, default=Stage.QUEUED
    )
    progress = models.FloatField(default=0.0)
    error = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Job {self.id} [{self.stage}]"
