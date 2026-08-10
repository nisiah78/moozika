"""Tests du pipeline OCR (conversion Tesseract → runs + fallback document)."""
from __future__ import annotations

import unittest
from unittest import mock

from app.pdf.extract import ExtractError, Run
from app.pdf.ocr import (
    OcrError,
    detect_voice_bands,
    ocr_available,
    tesseract_data_to_runs,
)


class TestDetectVoiceBands(unittest.TestCase):
    @unittest.skipUnless(
        __import__("importlib").util.find_spec("numpy") is not None,
        "numpy requis",
    )
    def test_two_separated_bands(self):
        import numpy as np

        # Image 100×40 : deux bandes sombres séparées par un gap de 20.
        img = np.full((100, 40), 255, dtype=np.uint8)
        img[10:25, :] = 0
        img[50:65, :] = 0
        bands = detect_voice_bands(img, min_gap=15, density=0.5, min_height=5)
        self.assertEqual(len(bands), 2)
        self.assertEqual(bands[0], (10, 25))
        self.assertEqual(bands[1], (50, 65))

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("numpy") is not None,
        "numpy requis",
    )
    def test_close_bands_merge(self):
        import numpy as np

        img = np.full((80, 40), 255, dtype=np.uint8)
        img[10:20, :] = 0
        img[25:35, :] = 0  # gap=5 < min_gap=15 → fusion
        bands = detect_voice_bands(img, min_gap=15, density=0.5, min_height=5)
        self.assertEqual(len(bands), 1)
        self.assertEqual(bands[0], (10, 35))

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("numpy") is not None,
        "numpy requis",
    )
    def test_tall_band_split_by_valleys(self):
        import numpy as np

        # Deux pics de texte séparés par une vallée, dans une région active continue.
        img = np.full((120, 100), 255, dtype=np.uint8)
        img[10:40, :] = 0   # pic 1
        img[45:55, 40:60] = 0  # faible encre dans la vallée (reste sous seuil local)
        img[60:90, :] = 0   # pic 2
        bands = detect_voice_bands(
            img, min_gap=50, density=0.3, min_height=8, max_height=40
        )
        # Sans split : une seule bande 10-90 ; avec split : ≥2.
        self.assertGreaterEqual(len(bands), 2)

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("numpy") is not None,
        "numpy requis",
    )
    def test_empty_image(self):
        import numpy as np

        img = np.full((50, 50), 255, dtype=np.uint8)
        self.assertEqual(detect_voice_bands(img), [])


class TestTesseractDataToRuns(unittest.TestCase):
    def test_positions_and_pdf_y_axis(self):
        # page_h = max(top+height) = 30 ; centre du premier mot = 20 → y = 10.
        data = {
            "text": ["d", ":", "r"],
            "left": [10, 40, 70],
            "top": [10, 12, 10],
            "height": [20, 16, 20],
            "conf": [90, 88, 91],
        }
        runs = tesseract_data_to_runs(data)
        self.assertEqual([r.text for r in runs], ["d", ":", "r"])
        self.assertEqual(runs[0].x, 10.0)
        self.assertAlmostEqual(runs[0].y, 30.0 - 20.0, places=1)
        self.assertEqual(runs[0].font, "ocr")

    def test_skips_empty_and_negative_conf(self):
        data = {
            "text": ["", "d", "x"],
            "left": [0, 1, 2],
            "top": [0, 0, 0],
            "height": [10, 10, 10],
            "conf": [90, 90, -1],
        }
        runs = tesseract_data_to_runs(data)
        self.assertEqual([r.text for r in runs], ["d"])

    def test_y_offset_stacks_pages(self):
        data = {
            "text": ["s"],
            "left": [0],
            "top": [0],
            "height": [10],
            "conf": [95],
        }
        runs = tesseract_data_to_runs(data, y_offset=50.0)
        self.assertEqual(runs[0].y, 50.0 + (10.0 - 5.0))


class TestOcrFallback(unittest.TestCase):
    def test_document_falls_back_to_ocr_when_no_text(self):
        from app.pdf import document as doc_mod

        fake_runs = [
            Run(y=100, x=10, font="ocr", text="Doh = C"),
            Run(y=100, x=80, font="ocr", text="4/4"),
            Run(y=80, x=10, font="ocr", text="d"),
            Run(y=80, x=30, font="ocr", text=":"),
            Run(y=80, x=50, font="ocr", text="r"),
            Run(y=80, x=70, font="ocr", text=":"),
            Run(y=80, x=90, font="ocr", text="m"),
            Run(y=80, x=110, font="ocr", text=":"),
            Run(y=80, x=130, font="ocr", text="f"),
        ]
        with mock.patch.object(doc_mod, "extract_runs", side_effect=ExtractError("scanné")):
            with mock.patch.object(doc_mod, "ocr_to_runs", return_value=fake_runs) as ocr:
                doc = doc_mod.pdf_to_document(b"%PDF-1.4 fake scanned")
        ocr.assert_called_once()
        self.assertEqual(doc.header.tonic, "C")
        self.assertEqual((doc.header.beats, doc.header.beat_type), (4, 4))
        self.assertEqual(len(doc.voices), 1)
        self.assertIn("d : r : m : f", doc.voices[0])

    def test_ocr_error_surfaces_as_pdf_solfa_error(self):
        from app.pdf import document as doc_mod
        from app.pdf.document import PdfSolfaError

        with mock.patch.object(doc_mod, "extract_runs", side_effect=ExtractError("scanné")):
            with mock.patch.object(doc_mod, "ocr_to_runs", side_effect=OcrError("tesseract ko")):
                with self.assertRaises(PdfSolfaError) as ctx:
                    doc_mod.pdf_to_document(b"%PDF-1.4")
        self.assertIn("OCR", str(ctx.exception))


@unittest.skipUnless(ocr_available(), "dépendances OCR / tesseract absentes")
class TestOcrIntegration(unittest.TestCase):
    def test_ocr_simple_png_syllables(self):
        """Rend une ligne sol-fa en image et vérifie que Tesseract la lit."""
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont

        from app.pdf.ocr import ocr_to_runs

        img = Image.new("RGB", (600, 80), "white")
        draw = ImageDraw.Draw(img)
        # Police bitmap par défaut : assez grande pour Tesseract.
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        except OSError:
            font = ImageFont.load_default()
        draw.text((20, 20), "d : r : m : f", fill="black", font=font)
        buf = __import__("io").BytesIO()
        img.save(buf, format="PNG")
        runs = ocr_to_runs(buf.getvalue())
        blob = " ".join(r.text for r in runs).lower()
        # Tolérant : OCR peut coller ou omettre des espaces.
        for syl in "d r m f".split():
            self.assertIn(syl, blob)


if __name__ == "__main__":
    unittest.main()
