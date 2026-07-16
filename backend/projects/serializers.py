from rest_framework import serializers

from architecture.models import ArchitectureSnapshot
from jobs.models import AnalysisJob
from projects.models import Project, ProjectFile, Upload


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "name", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "created_at", "updated_at"]


class UploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Upload
        fields = [
            "id",
            "project",
            "s3_key",
            "original_filename",
            "size_bytes",
            "checksum",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class AnalysisJobSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(source="project.id", read_only=True)

    class Meta:
        model = AnalysisJob
        fields = [
            "id",
            "project_id",
            "status",
            "stage",
            "progress",
            "error",
            "created_at",
            "updated_at",
        ]


class ProjectFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectFile
        fields = ["id", "path", "language", "size_bytes", "loc", "role", "metadata"]


class ArchitectureSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchitectureSnapshot
        fields = ["id", "version", "summary", "data", "created_at"]
