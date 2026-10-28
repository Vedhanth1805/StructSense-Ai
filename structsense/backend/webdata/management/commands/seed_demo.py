"""Create a reproducible, fully processed local demonstration project."""
from __future__ import annotations

import os
import secrets
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from reportlab.pdfgen import canvas

from webdata.models import (AnalysisResult, AnalysisRun, AuditEvent, Document,
                            ExtractedParameter, ParameterConflict, ParameterCorrection,
                            Project, StressScenario)


class Command(BaseCommand):
    help = "Create a demo login, PDF sources, resolved conflict, validated base/modified analyses, and audit history."

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get("STRUCTSENSE_DEMO_USERNAME", "structsense-demo")
        password = os.environ.get("STRUCTSENSE_DEMO_PASSWORD")
        user, created = User.objects.get_or_create(username=username, defaults={"email": "demo@localhost"})
        if created:
            password = password or secrets.token_urlsafe(18)
            user.set_password(password)
            user.save(update_fields=["password"])

        project, _ = Project.objects.get_or_create(owner=user, name="StructSense AI Major Project Demo",
            defaults={"description": "Reproducible base/stress demo with PDF sources, a resolved M30/M25 conflict, real PPO and structural checks."})

        base = {
            "concrete_grade": 30.0, "steel_grade": 500.0, "column_width_mm": 450.0,
            "column_depth_mm": 600.0, "num_floors": 5.0, "floor_load_kn_m2": 5.0,
            "soil_bearing_capacity_kn_m2": 200.0, "foundation_depth_m": 1.5,
            "seismic_zone": 2.0, "wind_speed_kmph": 100.0, "rainfall_mm_annual": 800.0,
            "building_age_years": 10.0, "shear_wall_present": 1.0, "foundation_type": 1.0,
            "column_reinforcement_ratio": 0.02, "beam_depth_mm": 500.0,
            "slab_thickness_mm": 150.0, "location_risk_index": 0.3,
        }
        modified = {**base, "concrete_grade": 20.0, "steel_grade": 415.0,
                    "column_width_mm": 300.0, "column_depth_mm": 450.0,
                    "beam_depth_mm": 350.0, "slab_thickness_mm": 100.0,
                    "floor_load_kn_m2": 8.0}

        self._ensure_pdf(project, user, "demo-structure-base.pdf", self._base_text(), "base")
        self._ensure_pdf(project, user, "demo-structure-alternate.pdf",
                         "Alternate structural schedule: Concrete grade M25. This source intentionally conflicts with the base drawing.", "alternate")

        conflict = ParameterConflict.objects.filter(project=project, parameter_name="concrete_grade").first()
        if conflict and conflict.status == "requires_engineer_review":
            parameter = project.parameters.get(name="concrete_grade")
            ParameterCorrection.objects.get_or_create(parameter=parameter, corrected_value=30.0,
                defaults={"original_value": parameter.value, "user": user,
                          "reason": "Demo conflict review: selected M30 from the base structural schedule."})
            parameter.value, parameter.validation_status = 30.0, "corrected"
            parameter.save(update_fields=["value", "validation_status", "updated_at"])
            conflict.status, conflict.resolved_by, conflict.resolved_at = "resolved", user, timezone.now()
            conflict.save(update_fields=["status", "resolved_by", "resolved_at"])
            AuditEvent.objects.create(project=project, actor=user, action="parameter_correct",
                details={"parameter": "concrete_grade", "value": 30.0, "reason": "Selected base schedule after M30/M25 conflict review"})

        for key, value in base.items():
            parameter, _ = ExtractedParameter.objects.get_or_create(project=project, name=key,
                defaults={"value": value, "unit": "", "extraction_method": "demo configuration", "validation_status": "validated"})
            if parameter.validation_status not in ("corrected", "validated"):
                parameter.value, parameter.validation_status = value, "validated"
                parameter.save(update_fields=["value", "validation_status", "updated_at"])

        self._record_analysis(project, user, "DEMO BASE CONFIGURATION", base, include_ppo=True)

        from document_intelligence.parameter_extractor import PARAM_SPEC
        for key, value in modified.items():
            parameter = project.parameters.get(name=key)
            if parameter.value != value:
                ParameterCorrection.objects.get_or_create(parameter=parameter, corrected_value=value,
                    defaults={"original_value": parameter.value, "user": user,
                              "reason": "Reproducible modified/stress demonstration configuration."})
            parameter.value = value
            parameter.validation_status = "corrected" if key in modified and value != base[key] else "validated"
            parameter.unit = PARAM_SPEC[key]["unit"]
            parameter.save(update_fields=["value", "validation_status", "unit", "updated_at"])
        self._record_analysis(project, user, "DEMO MODIFIED / STRESS CONFIGURATION", modified, include_ppo=False)
        AuditEvent.objects.get_or_create(project=project, actor=user, action="demo_project_ready",
            defaults={"details": {"project_id": project.id, "conflict": "M30 vs M25", "analysis_runs": 2}})

        self.stdout.write(self.style.SUCCESS("Demo project ready: %s (id=%s)" % (project.name, project.id)))
        self.stdout.write("Login username: %s" % username)
        if created:
            self.stdout.write("Login password: %s" % password)
        elif password:
            self.stdout.write("Existing account retained; password was not changed.")
        self.stdout.write("Project URL: /projects/%s/" % project.id)

    def _ensure_pdf(self, project, user, filename, text, tag):
        if project.documents.filter(original_filename=filename).exists():
            return
        from webdata.ui import process_document_record
        pdf = BytesIO()
        page = canvas.Canvas(pdf)
        y = 790
        for line in text.splitlines():
            page.drawString(42, y, line[:110])
            y -= 24
        page.save()
        payload = pdf.getvalue()
        document = Document(project=project, uploader=user, original_filename=filename,
                            file_type="pdf", file_size=len(payload))
        document.file.save(filename, ContentFile(payload), save=True)
        process_document_record(document, user)
        AuditEvent.objects.create(project=project, actor=user, action="demo_document_added",
            details={"document_id": document.id, "role": tag, "filename": filename})

    @staticmethod
    def _base_text():
        return """StructSense AI demonstration structural schedule
Concrete grade: M30
Steel grade: Fe500
Columns 450 x 600 mm
Number of floors: 5
Floor load: 5 kN/m2
Soil bearing capacity: 200 kN/m2
Foundation depth: 1.5 m
Seismic zone: 2
Wind speed: 100 km/h
Annual rainfall: 800 mm
Building age: 10 years
Shear walls present
Raft foundation
Column reinforcement ratio: 2%
Beam depth: 500 mm
Slab thickness: 150 mm
Location risk index: 0.3"""

    @staticmethod
    def _record_analysis(project, user, label, params, include_ppo):
        if project.analyses.filter(scenario=label, status="completed").exists():
            return
        from analysis.service import StructuralAnalysisService
        run = AnalysisRun.objects.create(project=project, initiated_by=user, status="running",
            scenario=label, input_parameters=params, result={})
        try:
            result = StructuralAnalysisService().analyze(params, include_ppo=include_ppo,
                ppo_timesteps=1024)
            run.status, run.result = "completed", result
            run.save(update_fields=["status", "result"])
            AnalysisResult.objects.create(analysis=run, overall_risk=result["overall_risk_score"],
                risk_label=result["risk_label"], result_data=result)
            for name, detail in result["scenario_results"].items():
                StressScenario.objects.create(analysis=run, name=name, inputs=params, result=detail)
            AuditEvent.objects.create(project=project, actor=user, action="analysis_completed",
                details={"analysis_id": str(run.id), "scenario": label,
                         "ppo_included": include_ppo, "risk": result["overall_risk_score"]})
        except Exception as exc:
            run.status, run.result = "failed", {"error": str(exc)[:1000]}
            run.save(update_fields=["status", "result"])
            raise
