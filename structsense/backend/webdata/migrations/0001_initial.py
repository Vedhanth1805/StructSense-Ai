import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="structural_projects", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="projects/%Y/%m/")),
                ("original_filename", models.CharField(max_length=255)),
                ("file_type", models.CharField(max_length=8)),
                ("file_size", models.PositiveBigIntegerField()),
                ("processing_status", models.CharField(choices=[("uploaded", "Uploaded"), ("processing", "Processing"), ("processed", "Processed"), ("failed", "Failed")], default="uploaded", max_length=16)),
                ("processing_error", models.TextField(blank=True)),
                ("extraction_metadata", models.JSONField(blank=True, default=dict)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to="webdata.project")),
                ("uploader", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="DocumentSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("locator", models.CharField(blank=True, max_length=255)),
                ("method", models.CharField(max_length=80)),
                ("excerpt", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sources", to="webdata.document")),
            ],
        ),
        migrations.CreateModel(
            name="ExtractedParameter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("value", models.JSONField(null=True)),
                ("extraction_method", models.CharField(max_length=80)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("confidence_kind", models.CharField(default="not provided", max_length=60)),
                ("validation_status", models.CharField(default="pending", max_length=24)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="parameters", to="webdata.project")),
            ],
        ),
        migrations.CreateModel(
            name="ParameterSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.JSONField(null=True)),
                ("source_text", models.TextField(blank=True)),
                ("extraction_method", models.CharField(max_length=80)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="webdata.document")),
                ("parameter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="webdata.extractedparameter")),
            ],
        ),
        migrations.AddField(
            model_name="extractedparameter",
            name="source_documents",
            field=models.ManyToManyField(related_name="extracted_parameters", through="webdata.ParameterSource", to="webdata.document"),
        ),
        migrations.CreateModel(
            name="ParameterConflict",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("parameter_name", models.CharField(max_length=100)),
                ("competing_values", models.JSONField(default=list)),
                ("status", models.CharField(default="requires_engineer_review", max_length=32)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conflicts", to="webdata.project")),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="ParameterCorrection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_value", models.JSONField(null=True)),
                ("corrected_value", models.JSONField()),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("parameter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="corrections", to="webdata.extractedparameter")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="AnalysisRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(default="completed", max_length=20)),
                ("scenario", models.CharField(blank=True, max_length=100)),
                ("input_parameters", models.JSONField(default=dict)),
                ("result", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("initiated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="analyses", to="webdata.project")),
            ],
        ),
        migrations.CreateModel(
            name="StressScenario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("inputs", models.JSONField(default=dict)),
                ("result", models.JSONField(default=dict)),
                ("risk_result", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("analysis", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scenarios", to="webdata.analysisrun")),
            ],
        ),
        migrations.CreateModel(
            name="AnalysisResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("overall_risk", models.FloatField()),
                ("risk_label", models.CharField(max_length=40)),
                ("result_data", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("analysis", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="summary", to="webdata.analysisrun")),
            ],
        ),
        migrations.CreateModel(
            name="Report",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("format", models.CharField(max_length=8)),
                ("file", models.FileField(upload_to="reports/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("analysis", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reports", to="webdata.analysisrun")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reports", to="webdata.project")),
            ],
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=100)),
                ("details", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_events", to="webdata.project")),
            ],
        ),
        migrations.AddConstraint(
            model_name="extractedparameter",
            constraint=models.UniqueConstraint(fields=("project", "name"), name="unique_project_parameter"),
        ),
        migrations.AddConstraint(
            model_name="parametersource",
            constraint=models.UniqueConstraint(fields=("parameter", "document"), name="unique_parameter_document_source"),
        ),
    ]
