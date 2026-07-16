from django.contrib import admin
from django.urls import path

from projects import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", views.health),
    path("api/projects/", views.project_list_create),
    path("api/projects/<uuid:project_id>/", views.project_detail),
    path("api/projects/<uuid:project_id>/uploads/", views.create_upload),
    path("api/projects/<uuid:project_id>/uploads/complete/", views.complete_upload),
    path("api/projects/<uuid:project_id>/jobs/", views.project_jobs),
    path("api/projects/<uuid:project_id>/tree/", views.project_tree),
    path("api/projects/<uuid:project_id>/graph/", views.project_graph),
    path("api/projects/<uuid:project_id>/symbols/", views.project_symbols),
    path("api/projects/<uuid:project_id>/architecture/", views.project_architecture),
    path(
        "api/projects/<uuid:project_id>/architecture/generate/",
        views.generate_project_architecture,
    ),
    path("api/jobs/<uuid:job_id>/", views.job_detail),
]
