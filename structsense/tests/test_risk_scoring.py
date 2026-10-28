"""Regression checks for the aggregate formula and persistent DSW checkpoint."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from risk.risk_module import NeuralDSW, StructuralRiskScorer, load_or_train_dsw


BASE = {
    "concrete_grade": 30.0, "steel_grade": 500.0, "column_width_mm": 450.0,
    "column_depth_mm": 600.0, "num_floors": 5.0, "floor_load_kn_m2": 5.0,
    "soil_bearing_capacity_kn_m2": 200.0, "foundation_depth_m": 1.5,
    "seismic_zone": 2.0, "wind_speed_kmph": 100.0, "rainfall_mm_annual": 800.0,
    "building_age_years": 10.0, "shear_wall_present": 1.0, "foundation_type": 1.0,
    "column_reinforcement_ratio": 0.02, "beam_depth_mm": 500.0,
    "slab_thickness_mm": 150.0, "location_risk_index": 0.3,
}
STRESS = {**BASE, "concrete_grade": 20.0, "steel_grade": 415.0,
          "column_width_mm": 300.0, "column_depth_mm": 450.0,
          "floor_load_kn_m2": 8.0, "beam_depth_mm": 350.0,
          "slab_thickness_mm": 100.0}
VELACHERY = {
    "concrete_grade": 25.0, "steel_grade": 415.0, "column_width_mm": 350.0,
    "column_depth_mm": 500.0, "num_floors": 12.0, "floor_load_kn_m2": 4.0,
    "soil_bearing_capacity_kn_m2": 180.0, "foundation_depth_m": 3.0,
    "seismic_zone": 3.0, "wind_speed_kmph": 120.0, "rainfall_mm_annual": 1400.0,
    "building_age_years": 5.0, "shear_wall_present": 1.0, "foundation_type": 1.0,
    "column_reinforcement_ratio": 0.015, "beam_depth_mm": 480.0,
    "slab_thickness_mm": 130.0, "location_risk_index": 0.4,
}


class AggregateFormulaTests(unittest.TestCase):
    def test_material_geometry_and_load_changes_affect_aggregate(self):
        scorer = StructuralRiskScorer()
        base = scorer.aggregate_components(raw_params=BASE)
        stress = scorer.aggregate_components(raw_params=STRESS)
        station = scorer.aggregate_components(raw_params=VELACHERY)

        self.assertEqual(base["formula_version"], "six-factor-plus-element-mean-v1")
        self.assertAlmostEqual(base["aggregate_risk"], 0.5091, places=4)
        self.assertAlmostEqual(stress["aggregate_risk"], 0.5675, places=4)
        self.assertAlmostEqual(station["aggregate_risk"], 0.5489, places=4)
        self.assertNotEqual(base["aggregate_risk"], stress["aggregate_risk"])
        self.assertNotEqual(base["aggregate_risk"], station["aggregate_risk"])
        self.assertNotEqual(stress["aggregate_risk"], station["aggregate_risk"])


class PersistentDswTests(unittest.TestCase):
    def test_checkpoint_is_saved_loaded_and_cached_as_one_instance(self):
        import numpy as np

        with tempfile.TemporaryDirectory(prefix="structsense-dsw-") as directory:
            path = Path(directory) / "shared-dsw.pt"
            first = load_or_train_dsw(path, n_samples=128, epochs=2, seed=19)
            self.assertTrue(path.is_file())
            self.assertEqual(first.training_metadata["status"], "trained_and_saved")

            second = load_or_train_dsw(path, n_samples=128, epochs=2, seed=19)
            self.assertIs(first, second)
            restored = NeuralDSW()
            restored.load(str(path))
            sample = np.linspace(0.0, 1.0, 18, dtype=np.float32)
            self.assertAlmostEqual(first.predict_weight(sample), restored.predict_weight(sample), places=7)


class DswPpoIntegrationTests(unittest.TestCase):
    def test_dsw_output_changes_failure_reward_and_is_recorded_for_ppo(self):
        from environment.building_env import BuildingStressEnv

        class FixedDsw:
            def __init__(self, weight):
                self.weight = weight
            def predict_weight(self, state):
                return self.weight

        severe = {**BASE, "concrete_grade": 15.0, "steel_grade": 250.0,
                  "column_width_mm": 200.0, "column_depth_mm": 200.0,
                  "num_floors": 20.0, "floor_load_kn_m2": 15.0}
        results = []
        for weight in (0.1, 0.9):
            env = BuildingStressEnv(severe, dsw_model=FixedDsw(weight))
            env.reset(seed=13)
            _, reward, _, _, info = env.step(0)
            self.assertFalse(info["passed"])
            self.assertAlmostEqual(info["dsw_safety_weight"], weight, places=6)
            self.assertAlmostEqual(info["reward_risk_weight"],
                                   info["risk_weight"] * (0.5 + weight), places=3)
            results.append(reward)
        self.assertLess(results[1], results[0])

    def test_ppo_training_records_dsw_values_consumed_by_environment(self):
        import tempfile
        from unittest.mock import patch
        from agent.ppo_agent import PPOStructuralAgent

        class FixedDsw:
            def predict_weight(self, state):
                return 0.8

        with tempfile.TemporaryDirectory(prefix="structsense-ppo-dsw-") as model_dir:
            with patch.object(PPOStructuralAgent, "MODEL_DIR", model_dir):
                agent = PPOStructuralAgent(BASE, dsw_model=FixedDsw())
                metrics = agent.train(timesteps=512)
        self.assertTrue(metrics["dsw_in_reward"])
        self.assertGreater(metrics["dsw_weight_samples"], 0)
        self.assertAlmostEqual(metrics["mean_dsw_safety_weight"], 0.8, places=5)


class Nh48HarnessTests(unittest.TestCase):
    def test_jsonl_pdf_harness_reports_extraction_metrics_without_paper_claim(self):
        import fitz
        import tempfile
        from evaluation.nh48_benchmark import evaluate_records

        with tempfile.TemporaryDirectory(prefix="structsense-nh48-harness-") as directory:
            pdf_path = Path(directory) / "sample.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "Concrete grade M30. Steel grade Fe500. Number of floors: 5. "
                             "Structural evaluation sample document with stated parameters.")
            document.save(pdf_path)
            document.close()
            report = evaluate_records([{
                "document_id": "test-only-sample",
                "document_path": "sample.pdf",
                "ground_truth_parameters": {"concrete_grade": 30, "steel_grade": 500, "num_floors": 5},
            }], Path(directory))
        self.assertEqual(report["document_count"], 1)
        self.assertEqual(report["correct_field_count"], 3)
        self.assertEqual(report["field_accuracy"], 1.0)
        self.assertIn("not a reproduction", report["limitations"])


if __name__ == "__main__":
    unittest.main()
