"""Tests détection PDF sol-fa vs portée (solfège occidental)."""
import unittest
from pathlib import Path

from app.pdf.detect import classify_runs, detect_pdf_kind, pdf_kind_message
from app.pdf.document import PdfSolfaError, pdf_to_document
from app.solfa.from_musicxml import MusicXmlError, from_musicxml

FIXTURES = Path(__file__).parent / "fixtures"
SOLFEGE = Path(__file__).resolve().parents[3] / "docs" / "solfege"
JESOA = FIXTURES / "jesoa-tsy-mba-mandao.pdf"


class TestDetectPdfKind(unittest.TestCase):
    @unittest.skipUnless(JESOA.is_file(), "fixture jesoa absente")
    def test_jesoa_is_solfa_text(self):
        self.assertEqual(detect_pdf_kind(JESOA.read_bytes()), "solfa_text")

    @unittest.skipUnless(
        (SOLFEGE / "bpi-bp1340.pdf").is_file(), "docs/solfege/bpi-bp1340.pdf absente"
    )
    def test_bpi_is_staff_notation(self):
        self.assertEqual(
            detect_pdf_kind((SOLFEGE / "bpi-bp1340.pdf").read_bytes()),
            "staff_notation",
        )

    @unittest.skipUnless(
        (SOLFEGE / "jubilate-deo-peter-anglea.pdf").is_file(),
        "docs/solfege/jubilate absente",
    )
    def test_jubilate_is_scanned(self):
        self.assertEqual(
            detect_pdf_kind((SOLFEGE / "jubilate-deo-peter-anglea.pdf").read_bytes()),
            "scanned",
        )


class TestPdfImportErrors(unittest.TestCase):
    @unittest.skipUnless(
        (SOLFEGE / "bpi-bp1340.pdf").is_file(), "docs/solfege/bpi-bp1340.pdf absente"
    )
    def test_staff_pdf_raises_without_audiveris(self):
        from app.staff.recognize import _audiveris_available
        from app.pdf.document import pdf_to_score
        if _audiveris_available():
            self.skipTest("Audiveris disponible")
        with self.assertRaises(PdfSolfaError) as ctx:
            pdf_to_score((SOLFEGE / "bpi-bp1340.pdf").read_bytes(), filename="bpi-bp1340.pdf")
        self.assertIn("Audiveris", str(ctx.exception))

    @unittest.skipUnless(
        (SOLFEGE / "bpi-bp1340.pdf").is_file(), "docs/solfege/bpi-bp1340.pdf absente"
    )
    def test_staff_pdf_via_musicxml_raises_not_partwise(self):
        with self.assertRaises(MusicXmlError) as ctx:
            from_musicxml(SOLFEGE / "bpi-bp1340.pdf")
        msg = str(ctx.exception)
        self.assertNotIn("introuvable", msg.lower())  # message explicite, pas l'ancien
        self.assertIn("Audiveris", msg)


class TestClassifyRuns(unittest.TestCase):
    def test_empty_runs_unknown(self):
        self.assertEqual(classify_runs([]), "unknown")

    def test_staff_message_mentions_mxl(self):
        self.assertIn(".mxl", pdf_kind_message("staff_notation"))


if __name__ == "__main__":
    unittest.main()
