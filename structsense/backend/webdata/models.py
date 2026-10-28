"""Persistent web/data service entities and audit history."""
import uuid
from django.conf import settings
from django.db import models

class Project(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="structural_projects")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Document(models.Model):
    STATUS = [(x, x.replace("_", " ").title()) for x in ("uploaded", "processing", "processed", "failed")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    uploader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    file = models.FileField(upload_to="projects/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=8)
    file_size = models.PositiveBigIntegerField()
    processing_status = models.CharField(max_length=16, choices=STATUS, default="uploaded")
    processing_error = models.TextField(blank=True)
    extraction_metadata = models.JSONField(default=dict, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class DocumentSource(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="sources")
    locator = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=80)
    excerpt = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class ExtractedParameter(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="parameters")
    name = models.CharField(max_length=100)
    value = models.JSONField(null=True)
    unit = models.CharField(max_length=30, blank=True)
    extraction_method = models.CharField(max_length=80)
    confidence = models.FloatField(null=True, blank=True)
    confidence_kind = models.CharField(max_length=60, default="not provided")
    validation_status = models.CharField(max_length=24, default="pending")
    source_documents = models.ManyToManyField(Document, through="ParameterSource", related_name="extracted_parameters")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "name"], name="unique_project_parameter")]

class ParameterSource(models.Model):
    parameter = models.ForeignKey(ExtractedParameter, on_delete=models.CASCADE)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    value = models.JSONField(null=True)
    source_text = models.TextField(blank=True)
    source_location = models.CharField(max_length=255, blank=True)
    extraction_method = models.CharField(max_length=80)
    confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["parameter", "document"], name="unique_parameter_document_source")]

class ParameterConflict(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="conflicts")
    parameter_name = models.CharField(max_length=100)
    competing_values = models.JSONField(default=list)
    status = models.CharField(max_length=32, default="requires_engineer_review")
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    resolved_at = models.DateTimeField(null=True, blank=True)

class ParameterCorrection(models.Model):
    parameter = models.ForeignKey(ExtractedParameter, on_delete=models.CASCADE, related_name="corrections")
    original_value = models.JSONField(null=True)
    corrected_value = models.JSONField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class AnalysisRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="analyses")
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="completed")
    scenario = models.CharField(max_length=100, blank=True)
    input_parameters = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class StressScenario(models.Model):
    analysis = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="scenarios")
    name = models.CharField(max_length=120)
    inputs = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    risk_result = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class AnalysisResult(models.Model):
    analysis = models.OneToOneField(AnalysisRun, on_delete=models.CASCADE, related_name="summary")
    overall_risk = models.FloatField()
    risk_label = models.CharField(max_length=40)
    result_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class Report(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="reports")
    analysis = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="reports")
    format = models.CharField(max_length=8)
    file = models.FileField(upload_to="reports/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

class AuditEvent(models.Model):
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
