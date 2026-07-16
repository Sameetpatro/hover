import uuid

from django.db import models

from projects.models import Project


class ArchitectureSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="architectures"
    )
    version = models.PositiveIntegerField(default=1)
    data = models.JSONField(default=dict)
    summary = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version", "-created_at"]
        unique_together = ("project", "version")

    def __str__(self) -> str:
        return f"{self.project.name} v{self.version}"
