import uuid

from django.db import models

from projects.models import Project, ProjectFile


class DependencyNode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="nodes")
    file = models.ForeignKey(
        ProjectFile, on_delete=models.CASCADE, related_name="nodes", null=True, blank=True
    )
    key = models.CharField(max_length=1024)
    label = models.CharField(max_length=512)
    kind = models.CharField(max_length=64, default="module")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("project", "key")


class DependencyEdge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="edges")
    source = models.ForeignKey(
        DependencyNode, on_delete=models.CASCADE, related_name="out_edges"
    )
    target = models.ForeignKey(
        DependencyNode, on_delete=models.CASCADE, related_name="in_edges"
    )
    edge_type = models.CharField(max_length=64, default="import")
    metadata = models.JSONField(default=dict, blank=True)


class Symbol(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="symbols")
    file = models.ForeignKey(
        ProjectFile, on_delete=models.CASCADE, related_name="symbols"
    )
    name = models.CharField(max_length=512)
    kind = models.CharField(max_length=64)
    start_line = models.IntegerField(default=0)
    end_line = models.IntegerField(default=0)
    signature = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["project", "kind", "name"])]
