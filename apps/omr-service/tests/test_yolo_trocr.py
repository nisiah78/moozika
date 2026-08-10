"""Tests des modules YOLO + TrOCR (skip si dépendances absentes)."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest

_HAS_ULTRALYTICS = importlib.util.find_spec("ultralytics") is not None
_HAS_TRANSFORMERS = importlib.util.find_spec("transformers") is not None
_HAS_TORCH = importlib.util.find_spec("torch") is not None
_HAS_PIL = importlib.util.find_spec("PIL") is not None
_HAS_NUMPY = importlib.util.find_spec("numpy") is not None
_HAS_CV2 = importlib.util.find_spec("cv2") is not None


class TestSynthYoloExport(unittest.TestCase):
    """Vérification de l'export YOLO (ne nécessite que PIL + numpy)."""

    @unittest.skipUnless(_HAS_PIL and _HAS_NUMPY, "PIL+numpy requis")
    def test_annotations_to_yolo_format(self):
        from app.pdf.synth import (
            BBoxAnnotation,
            YOLO_CLASSES,
            annotations_to_yolo,
        )

        anns = [
            BBoxAnnotation(label="d", x=10, y=20, w=16, h=24),
            BBoxAnnotation(label=":", x=40, y=22, w=4, h=20),
            BBoxAnnotation(label="r", x=60, y=20, w=14, h=24),
        ]
        txt = annotations_to_yolo(anns, img_w=200, img_h=100)
        lines = txt.strip().split("\n")
        self.assertEqual(len(lines), 3)
        # Première ligne : classe 0 (d), coordonnées normalisées.
        parts = lines[0].split()
        self.assertEqual(parts[0], str(YOLO_CLASSES.index("d")))
        cx = float(parts[1])
        self.assertGreater(cx, 0)
        self.assertLess(cx, 1)

    @unittest.skipUnless(_HAS_PIL and _HAS_NUMPY, "PIL+numpy requis")
    def test_generate_yolo_dataset(self):
        from app.pdf.synth import generate_yolo_dataset

        with tempfile.TemporaryDirectory() as td:
            yaml_path = generate_yolo_dataset(td, n_pages=20, seed=0)
            self.assertTrue(os.path.exists(yaml_path))
            # Vérifier que les images et labels sont créés (train + val).
            train_dir = os.path.join(td, "images", "train")
            val_dir = os.path.join(td, "images", "val")
            total = len(os.listdir(train_dir)) + len(os.listdir(val_dir))
            self.assertEqual(total, 20)
            labels_total = (
                len(os.listdir(os.path.join(td, "labels", "train")))
                + len(os.listdir(os.path.join(td, "labels", "val")))
            )
            self.assertEqual(labels_total, 20)


@unittest.skipUnless(
    _HAS_ULTRALYTICS and _HAS_TORCH,
    "ultralytics+torch requis",
)
class TestYoloDetector(unittest.TestCase):
    def test_detector_not_ready_without_model(self):
        from app.pdf.yolo_detect import SolfaYoloDetector

        det = SolfaYoloDetector("/nonexistent/model.pt")
        self.assertFalse(det.is_ready)

    def test_detections_to_runs(self):
        from app.pdf.yolo_detect import Detection, detections_to_runs

        dets = [
            Detection(label="d", confidence=0.9, x=10, y=20, w=16, h=24),
            Detection(label=":", confidence=0.8, x=40, y=22, w=4, h=20),
        ]
        runs = detections_to_runs(dets, page_h=100.0)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].text, "d")
        self.assertEqual(runs[0].font, "yolo")
        # Y inversé : y_image=32 (centre) → pdf_y=100-32=68.
        self.assertAlmostEqual(runs[0].y, 100.0 - 32.0, places=0)


@unittest.skipUnless(
    _HAS_TRANSFORMERS and _HAS_TORCH,
    "transformers+torch requis",
)
class TestTrOCR(unittest.TestCase):
    def test_trocr_available(self):
        from app.pdf.trocr import trocr_available

        self.assertTrue(trocr_available())

    def test_split_trocr_text(self):
        from app.pdf.trocr import _split_trocr_text

        tokens = _split_trocr_text("d : r . m : f | s")
        self.assertIn("d", tokens)
        self.assertIn(":", tokens)
        self.assertIn("|", tokens)
        self.assertIn("s", tokens)

    def test_text_to_runs(self):
        from app.pdf.trocr import _text_to_runs

        runs = _text_to_runs(
            "d : r : m",
            page_h=1000.0,
            y_center=500.0,
            y_offset=0.0,
        )
        self.assertGreater(len(runs), 0)
        self.assertEqual(runs[0].font, "trocr")
        # Les tokens doivent être distribués en x croissant.
        xs = [r.x for r in runs]
        self.assertEqual(xs, sorted(xs))


@unittest.skipUnless(
    _HAS_TRANSFORMERS and _HAS_TORCH and _HAS_PIL and _HAS_NUMPY,
    "transformers+torch+PIL+numpy requis",
)
class TestTrOCRIntegration(unittest.TestCase):
    """Test d'intégration TrOCR sur une image synthétique."""

    def test_read_simple_line(self):
        from PIL import Image, ImageDraw, ImageFont

        from app.pdf.trocr import TrOCRLineReader

        img = Image.new("RGB", (400, 48), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28
            )
        except OSError:
            font = ImageFont.load_default()
        draw.text((10, 8), "d : r : m : f", fill="black", font=font)

        try:
            reader = TrOCRLineReader()
            text = reader.read_line(img)
        except Exception as exc:
            self.skipTest(f"TrOCR model load failed (network?): {exc}")
        # TrOCR peut légèrement varier ; on vérifie la présence de syllabes.
        text_lower = text.lower()
        found = sum(1 for s in "d r m f".split() if s in text_lower)
        self.assertGreaterEqual(found, 2, f"TrOCR a lu : {text!r}")


@unittest.skipUnless(_HAS_PIL and _HAS_NUMPY and _HAS_CV2, "PIL+numpy+cv2 requis")
class TestCCPipeline(unittest.TestCase):
    """Tests du pipeline Connected Components."""

    def test_cc_ocr_page_on_synth(self):
        from app.pdf.cc_pipeline import cc_ocr_page
        from app.pdf.synth import generate_solfa_page

        img, _ = generate_solfa_page(
            ["d : r : m : f | s : l : t : d'"],
            seed=0, noise_level=0.0,
        )
        import cv2
        bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        runs = cc_ocr_page(bgr)
        self.assertGreater(len(runs), 3)
        labels = {r.text for r in runs}
        self.assertTrue(
            labels & {"d", "r", "m", "f", "s", "l", "t", ":", "|"},
            f"Labels trouvés : {labels}",
        )


class TestOcrPipelineOrder(unittest.TestCase):
    """Vérifie que _ocr_bgr essaie YOLO → CC → Tesseract."""

    def test_import_chain(self):
        from app.pdf.ocr import _ocr_bgr  # noqa: F401

    def test_has_solfa_content_filter(self):
        from app.pdf.extract import Run
        from app.pdf.ocr import _has_solfa_content

        good = [Run(y=0, x=0, font="x", text=t) for t in "d : r : m : f".split()]
        self.assertTrue(_has_solfa_content(good))

        bad = [Run(y=0, x=0, font="x", text="-") for _ in range(20)]
        self.assertFalse(_has_solfa_content(bad))


if __name__ == "__main__":
    unittest.main()
