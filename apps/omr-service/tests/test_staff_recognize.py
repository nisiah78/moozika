"""Tests intégration Audiveris (skip si service indisponible)."""
import unittest
from pathlib import Path

from app.pdf.document import pdf_to_score
from app.staff.recognize import _audiveris_available

SOLFEGE = Path(__file__).resolve().parents[3] / "docs" / "solfege"
BPI = SOLFEGE / "bpi-bp1340.pdf"


def _audiveris_up() -> bool:
    return _audiveris_available()


@unittest.skipUnless(BPI.is_file(), "docs/solfege/bpi-bp1340.pdf absente")
class TestStaffIntegration(unittest.TestCase):
    @unittest.skipUnless(_audiveris_up(), "Audiveris indisponible (docker compose up audiveris)")
    def test_bpi_staff_pdf_to_score(self):
        result = pdf_to_score(BPI.read_bytes(), filename=BPI.name)
        self.assertEqual(result.get("source"), "audiveris")
        self.assertIn("<score-partwise", result["musicxml"])
        self.assertGreater(len(result["voices"]), 0)
        self.assertTrue(result["voices"][0]["notation"])

    @unittest.skipUnless(_audiveris_up(), "Audiveris indisponible")
    def test_bpi_has_warnings_list(self):
        result = pdf_to_score(BPI.read_bytes(), filename=BPI.name)
        self.assertIsInstance(result.get("warnings"), list)


@unittest.skipUnless(BPI.is_file(), "docs/solfege/bpi-bp1340.pdf absente")
class TestStaffWithoutAudiveris(unittest.TestCase):
    def test_staff_pdf_errors_when_audiveris_down(self):
        if _audiveris_up():
            self.skipTest("Audiveris disponible — test non applicable")
        from app.pdf.document import PdfSolfaError
        with self.assertRaises(PdfSolfaError):
            pdf_to_score(BPI.read_bytes(), filename=BPI.name)


if __name__ == "__main__":
    unittest.main()
