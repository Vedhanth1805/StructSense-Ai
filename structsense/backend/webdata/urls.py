from django.urls import path
from . import views

urlpatterns = [
    path("projects/", views.projects, name="projects"),
    path("projects/<int:project_id>/", views.project_detail, name="project-detail"),
    path("projects/<int:project_id>/documents/", views.documents, name="documents"),
    path("documents/<int:document_id>/process/", views.process_document, name="process-document"),
    path("projects/<int:project_id>/parameters/", views.parameters, name="parameters"),
    path("projects/<int:project_id>/review/", views.review_parameters, name="review-parameters"),
    path("projects/<int:project_id>/analyses/", views.analyses, name="analyses"),
    path("analyses/<uuid:analysis_id>/", views.analysis_detail, name="analysis-detail"),
    path("projects/<int:project_id>/export.csv", views.export_csv, name="export-csv"),
    path("projects/<int:project_id>/dashboard/", views.dashboard, name="dashboard"),
    path("projects/<int:project_id>/model/", views.project_model, name="project-model"),
    path("projects/<int:project_id>/compare/", views.compare, name="compare"),
    path("analyses/<uuid:analysis_id>/report/", views.analysis_report, name="analysis-report"),
]
