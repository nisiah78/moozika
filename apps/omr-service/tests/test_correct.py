"""Tests du correcteur post-OCR sol-fa."""
from __future__ import annotations

import unittest

from app.pdf.correct import (
    correct_glyph_runs,
    correct_ocr_runs,
    correct_rhythm_runs,
)
from app.pdf.extract import Run


def _r(text: str, x: float = 0.0, y: float = 100.0) -> Run:
    return Run(y=y, x=x, font="ocr", text=text)


class TestGlyphCorrection(unittest.TestCase):
    def test_digit_five_to_s(self):
        runs = correct_glyph_runs([_r("5")])
        self.assertEqual(runs[0].text, "s")

    def test_capital_l_to_l(self):
        runs = correct_glyph_runs([_r("L")])
        self.assertEqual(runs[0].text, "l")

    def test_brace_to_bar(self):
        runs = correct_glyph_runs([_r("}")])
        self.assertEqual(runs[0].text, "|")

    def test_semicolon_to_colon(self):
        runs = correct_glyph_runs([_r(";")])
        self.assertEqual(runs[0].text, ":")

    def test_valid_syllable_unchanged(self):
        runs = correct_glyph_runs([_r("d,"), _r("s'")])
        self.assertEqual([r.text for r in runs], ["d,", "s'"])

    def test_zero_to_d(self):
        runs = correct_glyph_runs([_r("0")])
        self.assertEqual(runs[0].text, "d")

    def test_chromatic_preserved(self):
        runs = correct_glyph_runs([_r("di"), _r("fi"), _r("se")])
        self.assertEqual([r.text for r in runs], ["di", "fi", "se"])


class TestRhythmCorrection(unittest.TestCase):
    def test_collapse_repeated_colons(self):
        runs = correct_rhythm_runs([_r("::::")])
        self.assertEqual(runs[0].text, ":")

    def test_collapse_repeated_bars(self):
        runs = correct_rhythm_runs([_r("|||")])
        self.assertEqual(runs[0].text, "|")

    def test_insert_missing_bar_on_large_gap(self):
        # Ligne avec ":" → voix ; grand trou X → barre insérée.
        row = [
            _r("d", x=10),
            _r(":", x=30),
            _r("r", x=50),
            _r("m", x=200),  # gap 150 ≥ 80
            _r(":", x=220),
            _r("f", x=240),
        ]
        out = correct_rhythm_runs(row)
        texts = [r.text for r in out]
        self.assertIn("|", texts)
        # La barre est entre r (50) et m (200).
        bar = next(r for r in out if r.text == "|")
        self.assertGreater(bar.x, 50)
        self.assertLess(bar.x, 200)

    def test_no_bar_without_time_seps(self):
        # Ligne sans ":" → pas d'insertion (pas une voix).
        row = [_r("Hello", x=10), _r("World", x=200)]
        out = correct_rhythm_runs(row)
        self.assertEqual([r.text for r in out], ["Hello", "World"])


class TestCorrectOcrRuns(unittest.TestCase):
    def test_pipeline_combines_layers(self):
        runs = correct_ocr_runs([_r("5"), _r("::::"), _r("L")])
        self.assertEqual([r.text for r in runs], ["s", ":", "l"])

    def test_expand_glued_measure(self):
        runs = correct_glyph_runs([_r("d.m:s|", x=10)])
        texts = [r.text for r in runs]
        self.assertIn(":", texts)
        self.assertIn("|", texts)
        self.assertTrue(any(t in ("d", "m", "s") for t in texts))


if __name__ == "__main__":
    unittest.main()
