"""Tests sur un vrai PDF de cantique sol-fa malgache (fixture)."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from app.pdf.document import pdf_to_document, pdf_to_score
from app.pdf.extract import extract_runs
from app.pdf.ocr import ocr_available

FIXTURE = Path(__file__).parent / "fixtures" / "jesoa-tsy-mba-mandao.pdf"
MIVAVAHA = Path(__file__).parent / "fixtures" / "mivavaha.pdf"
DOCS = Path(__file__).resolve().parents[3] / "docs"
KRISTY = DOCS / "kristy-velona.pdf"
LORD_BLESS = DOCS / "the-lord-bless-you-and-keep-you.pdf"


class TestRealPdf(unittest.TestCase):
    def test_header(self):
        doc = pdf_to_document(FIXTURE)
        self.assertEqual(doc.header.title, "JESOA TSY MBA MANDAO")
        self.assertEqual(doc.header.tonic, "D")
        self.assertEqual((doc.header.beats, doc.header.beat_type), (4, 4))
        self.assertEqual(doc.header.tempo, 75)

    def test_four_voices_26_measures(self):
        doc = pdf_to_document(FIXTURE)
        self.assertEqual(doc.voice_names, ["Soprano", "Alto", "Tenor", "Bass"])
        for name, voice in zip(doc.voice_names, doc.voices):
            measures = voice.count("|") + 1
            self.assertEqual(measures, 26, f"{name}: {measures} mesures")

    def test_soprano_incipit(self):
        # Mesure 1 soprano : « .m : m.s : t : t.l » en ré majeur.
        # m = fa# (degré 3), s = la, t = do#, l = si.
        doc = pdf_to_document(FIXTURE)
        first_bar = doc.voices[0].split("|")[0].strip()
        self.assertEqual(first_bar, ".m : m.s : t : t.l")

    def test_musicxml_satb(self):
        result = pdf_to_score(FIXTURE)
        xml = result["musicxml"]
        root = ET.fromstring(xml[xml.index("<score-partwise"):])
        self.assertEqual([p.text for p in root.iter("part-name")],
                         ["Soprano", "Alto", "Tenor", "Bass"])
        for part in root.findall("part"):
            self.assertEqual(len(part.findall("measure")), 26)
        # armure de ré majeur = 2 dièses
        self.assertEqual(root.find(".//attributes/key/fifths").text, "2")
        # tempo présent
        self.assertEqual(root.find(".//sound[@tempo]").get("tempo"), "75")

    def test_from_bytes(self):
        result = pdf_to_score(FIXTURE.read_bytes())
        self.assertEqual(len(result["voices"]), 4)


@unittest.skipUnless(KRISTY.is_file(), "fixture docs/kristy-velona.pdf absente")
class TestTypographicVariants(unittest.TestCase):
    """PDF typographiés qui n'utilisent pas les polices /TT* (ex. /F4, hex Tj)."""

    def test_kristy_extracts_text_without_ocr(self):
        runs = extract_runs(KRISTY.read_bytes())
        blob = " ".join(r.text for r in runs)
        self.assertIn("Kristy Velona", blob)
        self.assertTrue(any(":" in r.text or ";" in r.text for r in runs))

    def test_kristy_reads_four_voices(self):
        """kristy utilise ';' (temps) et '_' (tenue) : doit être lisible."""
        doc = pdf_to_document(KRISTY)
        self.assertEqual(len(doc.voices), 4)
        for voice in doc.voices:
            self.assertGreater(voice.count("|") + 1, 5)
        # Chaque voix se parse en MusicXML sans erreur.
        result = pdf_to_score(KRISTY)
        self.assertIn("<score-partwise", result["musicxml"])
        self.assertEqual(len(result["voices"]), 4)

    def test_lord_bless_hex_tj_extracts_text(self):
        if not LORD_BLESS.is_file():
            self.skipTest("fixture docs/the-lord-bless-you-and-keep-you.pdf absente")
        runs = extract_runs(LORD_BLESS.read_bytes())
        blob = "".join(r.text for r in runs)
        self.assertGreater(len(runs), 100)
        # Titre / syllabes décodés via ToUnicode + <hex> Tj
        self.assertTrue(any(ch in blob for ch in "drmfslt"), blob[:200])


@unittest.skipUnless(MIVAVAHA.is_file(), "fixture docs/mivavaha.pdf absente")
class TestScannedOcr(unittest.TestCase):
    """mivavaha.pdf est un SCAN (images JPEG, aucun texte) -> chemin OCR.

    Ne s'exécute que là où l'OCR est disponible (image Docker avec tesseract).
    Objectif : mesurer jusqu'où on lit un scan propre, pas viser l'exactitude.
    """

    def test_extraction_fails_needs_ocr(self):
        # Sans OCR, l'extraction texte doit échouer proprement (scan).
        from app.pdf.extract import ExtractError
        with self.assertRaises(ExtractError):
            extract_runs(MIVAVAHA.read_bytes())

    @unittest.skipUnless(ocr_available(), "OCR indisponible (tesseract/opencv/pymupdf)")
    def test_ocr_pipeline_produces_runs(self):
        from app.pdf.ocr import ocr_to_runs
        runs = ocr_to_runs(MIVAVAHA.read_bytes())
        # Le scan compte 6 systèmes SATB : on attend un volume de texte notable.
        self.assertGreater(len(runs), 50)

    @unittest.skipUnless(ocr_available(), "OCR indisponible (tesseract/opencv/pymupdf)")
    def test_ocr_end_to_end_best_effort(self):
        # Best-effort : le pipeline complet doit aboutir à un MusicXML.
        result = pdf_to_score(MIVAVAHA.read_bytes())
        self.assertIn("<score-partwise", result["musicxml"])
        self.assertGreaterEqual(len(result["voices"]), 1)

    @unittest.skipUnless(ocr_available(), "OCR indisponible (tesseract/opencv/pymupdf)")
    def test_ocr_mivavaha_four_voices_and_meter(self):
        """Band OCR : tonique A, mètre 4/4, ≥2 voix structurées."""
        result = pdf_to_score(MIVAVAHA.read_bytes())
        self.assertGreaterEqual(len(result["voices"]), 2, result["voices"])
        header = result["header"]
        self.assertEqual(header.get("tonic"), "A")
        ts = header.get("timeSignature") or {}
        self.assertEqual(ts.get("beats"), 4)
        self.assertEqual(ts.get("beatType"), 4)


if __name__ == "__main__":
    unittest.main()
