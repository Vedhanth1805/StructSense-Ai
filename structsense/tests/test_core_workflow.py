"""Dependency-light regression tests for extraction, fusion, and model geometry."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from document_intelligence.parameter_extractor import PARAM_SPEC, ParameterExtractor
from document_intelligence.fusion import fuse_parameter_sources, validate_parameter_set, validated_values
from reporting.structure_model import build_frame, compare_configurations

class ParameterExtractionTests(unittest.TestCase):
    def test_sample_document_maps_existing_schema_and_traces_source(self):
        text = (ROOT / "data" / "mock_report.txt").read_text(encoding="utf-8")
        extracted = ParameterExtractor().extract("", text, "mock_report.txt")
        self.assertEqual(set(extracted["parameters"]), set(PARAM_SPEC))
        self.assertEqual(extracted["parameters"]["concrete_grade"]["value"], 40.0)
        self.assertEqual(extracted["parameters"]["column_reinforcement_ratio"]["value"], 0.035)
        self.assertEqual(extracted["parameters"]["concrete_grade"]["source_document"], "mock_report.txt")
        self.assertEqual(extracted["parameters"]["concrete_grade"]["validation_status"], "pending")

    def test_absent_values_stay_unavailable(self):
        extracted = ParameterExtractor().extract("", "No structural values are listed.", "empty.txt")
        self.assertEqual(extracted["parameters"], {})
        self.assertEqual(set(extracted["unavailable"]), set(PARAM_SPEC))
        self.assertEqual(extracted["interpretation"]["provider"], "local_rule_based")
        self.assertEqual(extracted["interpretation"]["status"], "not_configured")
        self.assertIn("LOCAL / RULE-BASED FALLBACK", extracted["interpretation"]["label"])

    def test_column_section_notation_normalizes_both_dimensions(self):
        extracted = ParameterExtractor().extract("", "Column section: 450 x 600 mm.", "plan.pdf")
        values = extracted["parameters"]
        self.assertEqual(values["column_width_mm"]["value"], 450.0)
        self.assertEqual(values["column_depth_mm"]["value"], 600.0)
        self.assertIn("450 x 600 mm", values["column_width_mm"]["source_text"])

    def test_discrete_parameters_reject_fractional_extractions(self):
        extracted = ParameterExtractor().extract("", "Number of floors: 4.5", "plan.pdf")
        self.assertNotIn("num_floors", extracted["parameters"])

    def test_groq_request_failure_is_labeled_and_local_extraction_survives(self):
        class FailedClient:
            def __init__(self, api_key):
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.fail))
            @staticmethod
            def fail(**kwargs):
                raise RuntimeError("test transport failure")

        with patch.dict(sys.modules, {"groq": SimpleNamespace(Groq=FailedClient)}):
            extracted = ParameterExtractor().extract("test-key", "A structural schedule without recognized labels", "schedule.pdf")
        status = extracted["interpretation"]
        self.assertEqual(status["status"], "request_failed")
        self.assertTrue(status["request_made"])
        self.assertEqual(status["failure_type"], "RuntimeError")
        self.assertIn("LOCAL / RULE-BASED FALLBACK", status["label"])
        self.assertEqual(extracted["parameters"], {})

class FusionAndValidationTests(unittest.TestCase):
    def test_conflicts_are_retained_for_engineer_review(self):
        fused = fuse_parameter_sources([
            {"parameters": {"concrete_grade": {"value": 30, "source_document": "a.pdf"}}},
            {"parameters": {"concrete_grade": {"value": 25, "source_document": "b.pdf"}}},
        ])
        self.assertEqual(len(fused["conflicts"]), 1)
        self.assertEqual(fused["parameters"]["concrete_grade"]["validation_status"], "conflict")
        self.assertEqual([r["value"] for r in fused["conflicts"][0]["values"]], [30, 25])

    def test_analysis_requires_engineer_validation(self):
        params = {"concrete_grade": {"value": 30, "validation_status": "pending"}}
        with self.assertRaises(ValueError):
            validated_values(params, ["concrete_grade"])
        corrected = validate_parameter_set(params, corrections={"concrete_grade": 25})
        self.assertEqual(validated_values(corrected, ["concrete_grade"])["concrete_grade"], 25.0)

class VisualizationTests(unittest.TestCase):
    def test_frame_geometry_uses_floor_count_and_discloses_assumptions(self):
        model = build_frame({"num_floors": 3, "column_width_mm": 400, "slab_thickness_mm": 150})
        self.assertEqual(model["floors"], 3)
        self.assertEqual(len(model["nodes"]), 4 * 9)
        self.assertEqual(len(model["slabs"]), 3 * 4)
        self.assertEqual(model["slabs"][0]["thickness_mm"], 150)
        self.assertIn("not FEA", model["classification"])
        self.assertEqual(model["grid_assumptions"]["bay_width_m"], 5.0)

    def test_base_to_stress_parameters_change_rendered_frame_geometry(self):
        base = build_frame({"num_floors": 5, "column_width_mm": 450, "column_depth_mm": 600,
            "beam_depth_mm": 500, "slab_thickness_mm": 150})
        stress = build_frame({"num_floors": 4, "column_width_mm": 300, "column_depth_mm": 450,
            "beam_depth_mm": 350, "slab_thickness_mm": 100})
        self.assertEqual(base["floors"], 5)
        self.assertEqual(stress["floors"], 4)
        for field in ("column_width_mm", "column_depth_mm", "beam_depth_mm", "slab_thickness_mm"):
            self.assertNotEqual(base[field], stress[field], field)
        self.assertEqual(stress["slabs"][0]["thickness_mm"], 100)
        self.assertEqual(stress["classification"], "Parametric structural visualization; not FEA")

    def test_configuration_diff_contains_only_changed_values(self):
        diff = compare_configurations({"concrete_grade": 30, "num_floors": 5},
                                      {"concrete_grade": 25, "num_floors": 5})
        self.assertEqual(diff, {"concrete_grade": {"A": 30, "B": 25}})

if __name__ == "__main__":
    unittest.main()
