import uuid

from django.db import models

from projects.models import Project, ProjectFile


class CodeChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="chunks")
    file = models.ForeignKey(
        ProjectFile, on_delete=models.CASCADE, related_name="chunks"
    )
    symbol_name = models.CharField(max_length=512, blank=True, default="")
    language = models.CharField(max_length=64, blank=True, default="")
    start_line = models.IntegerField(default=0)
    end_line = models.IntegerField(default=0)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["project", "language"])]


class ChunkEmbedding(models.Model):
    """Embeddings stored as JSON for portability; pgvector optional at query layer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chunk = models.OneToOneField(
        CodeChunk, on_delete=models.CASCADE, related_name="embedding"
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="embeddings"
    )
    embedding = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
