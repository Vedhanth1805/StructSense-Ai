"""Optional integration checks; runtime-dependent cases skip when dependencies are absent."""
import importlib.util
import unittest

from document_intelligence.ifc_ingester import IFCIngester


class IFCNormalizationTests(unittest.TestCase):
    def test_only_explicit_ifc_properties_are_normalized(self):
        objects = [
            {"type": "columns", "name": "C1", "global_id": "guid-1",
             "properties": {"Dimensions": {"Width": 0.45, "Depth": 0.60}}},
            {"type": "beams", "properties": {"Dimensions": {"Depth": 0.50}}},
            {"type": "slabs", "properties": {"Dimensions": {"Thickness": 0.15}}},
        ]
        values = IFCIngester._normalize(objects, unit_scale=1.0)
        self.assertEqual(values["column_width_mm"]["value"], 450.0)
        self.assertEqual(values["column_depth_mm"]["value"], 600.0)
        self.assertEqual(values["beam_depth_mm"]["value"], 500.0)
        self.assertEqual(values["slab_thickness_mm"]["value"], 150.0)
        self.assertIn("C1", values["column_width_mm"]["source_location"])
        self.assertNotIn("concrete_grade", values)


@unittest.skipUnless(importlib.util.find_spec("ifcopenshell"), "IfcOpenShell is required")
class RealIFCFileTests(unittest.TestCase):
    def test_demo_ifc_file_extracts_elements_and_metric_dimensions(self):
        from pathlib import Path
        sample = Path(__file__).resolve().parents[1] / "data" / "demo-structural-frame.ifc"
        result = IFCIngester().extract(str(sample))
        self.assertEqual(result["counts"]["columns"], 1)
        self.assertEqual(result["counts"]["beams"], 1)
        self.assertEqual(result["counts"]["slabs"], 1)
        self.assertEqual(result["counts"]["levels"], 1)
        self.assertEqual(result["parameters"]["column_width_mm"]["value"], 450.0)
        self.assertEqual(result["parameters"]["column_depth_mm"]["value"], 600.0)
        self.assertEqual(result["parameters"]["beam_depth_mm"]["value"], 500.0)
        self.assertEqual(result["parameters"]["slab_thickness_mm"]["value"], 150.0)


@unittest.skipUnless(importlib.util.find_spec("gymnasium") and importlib.util.find_spec("numpy"),
                     "Gymnasium and NumPy are required")
class StructuralEnvironmentTests(unittest.TestCase):
    def test_environment_reset_step_and_action_contract(self):
        from environment.building_env import ACTION_NAMES, BuildingStressEnv
        env = BuildingStressEnv(BuildingStressEnv._default_params())
        observation, reset_info = env.reset(seed=7)
        self.assertEqual(observation.shape, (18,))
        self.assertIn("base_risk", reset_info)
        for action in ACTION_NAMES:
            env.reset(seed=7)
            _, reward, terminated, truncated, result = env.step(action)
            self.assertIsInstance(reward, float)
            self.assertIsInstance(terminated, bool)
            self.assertIsInstance(truncated, bool)
            self.assertIn("passed", result)


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in
                         ("fitz", "pytesseract", "PIL")),
                     "PyMuPDF, pytesseract, and Pillow are required")
class PdfExtractionTests(unittest.TestCase):
    def test_text_pdf_skips_ocr_and_short_page_uses_fallback(self):
        from unittest.mock import patch
        from document_intelligence.pdf_ingester import PDFIngester

        class Page:
            number = 0
            def __init__(self, text):
                self.text = text
            def get_text(self):
                return self.text
            def find_tables(self):
                raise AttributeError("table extraction unavailable")

        ingester = PDFIngester()
        with patch.object(ingester, "_ocr_page", return_value="OCR") as ocr:
            text, method, _ = ingester._extract_page_text(Page("A searchable page with enough extracted text for the normal PDF path."))
            self.assertEqual(method, "pymupdf")
            ocr.assert_not_called()
        with patch.object(ingester, "_ocr_page", return_value="OCR recovered structural text"):
            text, method, _ = ingester._extract_page_text(Page("tiny"))
            self.assertEqual(method, "tesseract")
            self.assertIn("OCR recovered", text)

    def test_missing_tesseract_is_reported_as_unavailable(self):
        from unittest.mock import patch
        from document_intelligence.pdf_ingester import PDFIngester

        class Page:
            number = 0
            def get_text(self): return "tiny"
            def find_tables(self): raise AttributeError("table extraction unavailable")

        ingester = PDFIngester()
        def unavailable(_page):
            ingester.last_ocr_status = "unavailable"
            return ""
        with patch.object(ingester, "_ocr_page", side_effect=unavailable):
            text, method, _ = ingester._extract_page_text(Page())
        self.assertEqual(text, "tiny")
        self.assertEqual(method, "pymupdf")

        class ScannedPage(Page):
            def get_text(self): return ""
        with patch.object(ingester, "_ocr_page", side_effect=unavailable):
            text, method, _ = ingester._extract_page_text(ScannedPage())
        self.assertEqual(text, "")
        self.assertEqual(method, "tesseract_unavailable")


@unittest.skipUnless(importlib.util.find_spec("reportlab"), "ReportLab is required")
class PdfReportTests(unittest.TestCase):
    def test_pdf_report_generates_bytes_and_includes_limitations(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from reporting.service import generate_analysis_pdf

        project = SimpleNamespace(name="Demo")
        analysis = SimpleNamespace(id="demo-id", created_at=datetime.now(timezone.utc),
            scenario="all", input_parameters={}, result={"overall_risk_score": 20.0, "risk_label": "LOW",
                "scenario_results": {}, "limitations": "Not FEA."})
        pdf = generate_analysis_pdf(project, analysis, [], [], [], [])
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 500)


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in
                         ("gymnasium", "numpy", "torch", "matplotlib", "PIL")),
                     "Structural analysis and visualization dependencies are required")
class DemoVideoIntegrationTests(unittest.TestCase):
    def test_reproducible_demo_runs_analysis_and_exports_video_or_gif(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from environment.building_env import PARAM_KEYS
        from reporting.demo_video import (MODIFIED_PARAMETERS, ORIGINAL_PARAMETERS,
                                          generate_demo_video)

        self.assertEqual(set(PARAM_KEYS), set(ORIGINAL_PARAMETERS))
        self.assertEqual(set(PARAM_KEYS), set(MODIFIED_PARAMETERS))
        with tempfile.TemporaryDirectory(prefix="structsense-test-demo-") as folder:
            output = generate_demo_video(Path(folder))
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 10_000)
            if output.suffix == ".gif":
                with Image.open(output) as animation:
                    self.assertEqual(animation.format, "GIF")
                    self.assertEqual(animation.n_frames, 13)
                    self.assertEqual(animation.info.get("duration"), 4_000)
            else:
                import imageio_ffmpeg
                decoded = imageio_ffmpeg.read_frames(str(output))
                try:
                    metadata = next(decoded)
                finally:
                    decoded.close()
                self.assertEqual(metadata["codec"], "h264")
                self.assertEqual(metadata["size"], (1280, 720))
                self.assertGreaterEqual(metadata["duration"], 50)
                import subprocess
                subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(output),
                                "-f", "null", "-"], check=True, capture_output=True, timeout=60)
            fallback = generate_demo_video(Path(folder) / "gif-fallback", prefer_mp4=False)
            self.assertEqual(fallback.suffix, ".gif")
            with Image.open(fallback) as animation:
                self.assertEqual(animation.format, "GIF")
                self.assertEqual(animation.n_frames, 13)
                self.assertEqual(animation.info.get("duration"), 4_000)
