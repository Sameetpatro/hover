from django.contrib import admin

from architecture.models import ArchitectureSnapshot
from analysis.models import DependencyEdge, DependencyNode, Symbol
from indexing.models import ChunkEmbedding, CodeChunk
from jobs.models import AnalysisJob
from projects.models import Project, ProjectFile, Upload

admin.site.register(Project)
admin.site.register(Upload)
admin.site.register(ProjectFile)
admin.site.register(AnalysisJob)
admin.site.register(DependencyNode)
admin.site.register(DependencyEdge)
admin.site.register(Symbol)
admin.site.register(CodeChunk)
admin.site.register(ChunkEmbedding)
admin.site.register(ArchitectureSnapshot)
