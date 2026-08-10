"""Tests générateur synthétique + classifieur de glyphes."""
from __future__ import annotations

import importlib.util
import unittest

from app.pdf.synth import GLYPH_CLASSES

_HAS_PIL = importlib.util.find_spec("PIL") is not None
_HAS_NUMPY = importlib.util.find_spec("numpy") is not None
_HAS_CV2 = importlib.util.find_spec("cv2") is not None


@unittest.skipUnless(_HAS_PIL and _HAS_NUMPY, "Pillow+numpy requis")
class TestSynth(unittest.TestCase):
    def test_generate_page_has_annotations(self):
        from app.pdf.synth import generate_solfa_page

        img, ann = generate_solfa_page(
            ["d : r : m : f | s : l : t : d'"],
            noise_level=0.0,
            seed=1,
        )
        self.assertGreater(len(ann), 5)
        labels = {a.label for a in ann}
        self.assertTrue(labels & {"d", "r", "m", "f", ":", "|"})
        # Image RGB.
        self.assertEqual(len(img.shape), 3)

    def test_four_voices_annotations(self):
        from app.pdf.synth import generate_solfa_page

        voices = [
            "d : r : m : f",
            "s : l : t : d",
            "m : f : s : l",
            "d, : r, : m, : f,",
        ]
        img, ann = generate_solfa_page(voices, noise_level=0.0, seed=2)
        voice_ids = {a.voice_index for a in ann}
        self.assertEqual(voice_ids, {0, 1, 2, 3})

    def test_page_to_png_bytes(self):
        from app.pdf.synth import generate_solfa_page, page_to_png_bytes

        img, _ = generate_solfa_page(["d : r"], noise_level=0.0, seed=0)
        png = page_to_png_bytes(img)
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_render_glyph_crop_shape(self):
        from app.pdf.synth import render_glyph_crop

        crop = render_glyph_crop("d", size=32)
        self.assertEqual(crop.shape, (32, 32))

    def test_glyph_dataset(self):
        from app.pdf.synth import generate_glyph_dataset

        images, labels = generate_glyph_dataset(
            ["d", ":", "|"], n_per_class=3, size=16, seed=0
        )
        self.assertEqual(len(labels), 9)
        self.assertEqual(images.shape, (9, 16, 16))


@unittest.skipUnless(_HAS_CV2 and _HAS_PIL and _HAS_NUMPY, "opencv+Pillow+numpy requis")
class TestClassifier(unittest.TestCase):
    def test_template_predicts_d(self):
        from app.pdf.classifier import TemplateGlyphClassifier
        from app.pdf.synth import render_glyph_crop

        clf = TemplateGlyphClassifier(n_per_class=4, size=32, seed=0)
        crop = render_glyph_crop("d", size=32)
        lab, conf = clf.predict(crop)
        self.assertEqual(lab, "d")
        self.assertGreater(conf, 0.5)

    def test_extract_components_on_synth_band(self):
        import cv2

        from app.pdf.classifier import classify_band_glyphs
        from app.pdf.synth import generate_solfa_page

        img, _ = generate_solfa_page(["d : r : m"], noise_level=0.0, seed=3)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preds = classify_band_glyphs(binary)
        self.assertGreater(len(preds), 0)
        labels = {p.label for p in preds}
        # Au moins une syllabe reconnue.
        self.assertTrue(labels & set(GLYPH_CLASSES))


if __name__ == "__main__":
    unittest.main()
