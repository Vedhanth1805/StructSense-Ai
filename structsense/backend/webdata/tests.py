"""Django integration tests for persistence, validation, analysis, and CSV export."""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework.test import APIClient

from .models import (AnalysisResult, AnalysisRun, AuditEvent, Document, DocumentSource,
                     ExtractedParameter, ParameterConflict, ParameterCorrection,
                     Project, StressScenario)


class ProjectApiWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="engineer", password="test-password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.project = Project.objects.create(owner=self.user, name="Integration project")

    def test_engineer_correction_persists_history_and_audit(self):
        parameter = ExtractedParameter.objects.create(
            project=self.project, name="concrete_grade", value=30.0,
            extraction_method="regex", validation_status="pending")
        response = self.client.post(
            f"/api/projects/{self.project.id}/review/",
            data=json.dumps({"parameters": {"concrete_grade": {
                "action": "correct", "value": 25, "reason": "verified drawing"}}}),
            content_type="application/json")
        self.assertEqual(response.status_code, 200)
        parameter.refresh_from_db()
        self.assertEqual(parameter.value, 25.0)
        self.assertEqual(parameter.validation_status, "corrected")
        self.assertEqual(ParameterCorrection.objects.get(parameter=parameter).original_value, 30.0)
        self.assertTrue(AuditEvent.objects.filter(project=self.project, action="parameter_correct").exists())

    def test_conflict_resolution_is_audited(self):
        parameter = ExtractedParameter.objects.create(project=self.project, name="concrete_grade",
            value=30.0, extraction_method="regex", validation_status="conflict")
        ParameterConflict.objects.create(project=self.project, parameter_name="concrete_grade",
            competing_values=[{"value": 30}, {"value": 25}])
        response = self.client.post(f"/api/projects/{self.project.id}/review/", data=json.dumps({
            "parameters": {"concrete_grade": {"action": "correct", "value": 25,
                "reason": "selected after engineer review"}}}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditEvent.objects.filter(project=self.project, action="conflict_resolved",
            details__parameter="concrete_grade").exists())

    def test_project_page_renders_namespaced_exports_reports_and_comparison(self):
        browser = Client()
        browser.force_login(self.user)
        base = AnalysisRun.objects.create(project=self.project, initiated_by=self.user,
            status="completed", scenario="Base", input_parameters={"concrete_grade": 30},
            result={"overall_risk_score": 20, "risk_label": "LOW",
                    "scenario_results": {"Normal Occupancy Load Test": {"passed": True}}})
        modified = AnalysisRun.objects.create(project=self.project, initiated_by=self.user,
            status="completed", scenario="Modified", input_parameters={"concrete_grade": 20},
            result={"overall_risk_score": 35, "risk_label": "LOW",
                    "scenario_results": {"Normal Occupancy Load Test": {"passed": False}}})
        response = browser.get(f"/projects/{self.project.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"/api/projects/{self.project.id}/export.csv")
        self.assertContains(response, f"/api/analyses/{base.id}/")
        self.assertContains(response, f"/api/analyses/{modified.id}/report/")
        self.assertContains(response, "Before and after analysis comparison")
        self.assertContains(response, "Normal Occupancy Load Test")
        self.assertTrue(AuditEvent.objects.filter(project=self.project, action="configurations_compared").exists())

    def test_project_page_displays_ocr_and_interpretation_status(self):
        document = Document.objects.create(project=self.project, uploader=self.user,
            file="projects/scanned.pdf", original_filename="scanned.pdf", file_type="pdf", file_size=10,
            processing_status="processed", extraction_metadata={"pages": [{"method": "tesseract_unavailable"}],
                "interpretation": {"label": "LOCAL / RULE-BASED FALLBACK — live Groq/LLaMA is not configured"}})
        DocumentSource.objects.create(document=document, locator="", method="tesseract_unavailable")
        browser = Client()
        browser.force_login(self.user)
        response = browser.get(f"/projects/{self.project.id}/")
        self.assertContains(response, "tesseract_unavailable")
        self.assertContains(response, "LOCAL / RULE-BASED FALLBACK")

    def test_successful_login_creates_global_audit_event(self):
        browser = Client()
        self.assertTrue(browser.login(username="engineer", password="test-password"))
        event = AuditEvent.objects.get(actor=self.user, action="login")
        self.assertIsNone(event.project)

    def test_analysis_requires_all_engineer_validated_parameters(self):
        response = self.client.post(f"/api/projects/{self.project.id}/analyses/", data={}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("unavailable_or_unvalidated", response.data)

    def test_analysis_result_and_scenario_history_are_persisted(self):
        from environment.building_env import BuildingStressEnv, PARAM_KEYS
        values = BuildingStressEnv._default_params()
        for name in PARAM_KEYS:
            ExtractedParameter.objects.create(project=self.project, name=name, value=values[name],
                extraction_method="engineer entered", validation_status="validated")
        result = {
            "analysis_timestamp": "2026-01-01T00:00:00+00:00",
            "scenario_results": {"Normal Occupancy Load Test": {"passed": True, "reward": 1.0}},
            "overall_risk_score": 27.5, "risk_label": "LOW", "element_risks": {},
            "risk_contributions": {}, "limitations": "Test result only.",
        }
        with patch("analysis.service.StructuralAnalysisService.analyze", return_value=result):
            response = self.client.post(f"/api/projects/{self.project.id}/analyses/", data={}, format="json")
        self.assertEqual(response.status_code, 201)
        run = AnalysisRun.objects.get(project=self.project)
        self.assertEqual(run.status, "completed")
        self.assertEqual(AnalysisResult.objects.get(analysis=run).overall_risk, 27.5)
        self.assertEqual(StressScenario.objects.get(analysis=run).name, "Normal Occupancy Load Test")
        self.assertTrue(AuditEvent.objects.filter(project=self.project, action="analysis_completed").exists())
        self.assertTrue(AuditEvent.objects.filter(project=self.project, action="scenario_analysis",
            details__scenario_count=1).exists())

    def test_csv_includes_parameters_before_analysis_exists(self):
        ExtractedParameter.objects.create(project=self.project, name="concrete_grade", value=30.0,
            extraction_method="engineer entered", validation_status="corrected")
        response = self.client.get(f"/api/projects/{self.project.id}/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("concrete_grade", response.content.decode("utf-8"))
        self.assertIn("30.0", response.content.decode("utf-8"))
