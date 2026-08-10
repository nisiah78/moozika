"""Regroupement des glyphes sol-fa (PDF à Tj caractère-par-caractère)."""
from __future__ import annotations

import unittest
from pathlib import Path

from app.pdf.extract import Run, extract_runs
from app.pdf.layout import build_document, merge_close_glyphs, row_to_measures
from app.solfa.lexer import LexError, tokenize
from app.pdf.document import pdf_to_score, PdfSolfaError

DOCS = Path(__file__).resolve().parents[3] / "docs"
LORD_BLESS = DOCS / "the-lord-bless-you-and-keep-you.pdf"


def _runs(*parts: tuple[float, str]) -> list[Run]:
    return [Run(y=100.0, x=x, font="F10", text=t) for x, t in parts]


class TestMergeCloseGlyphs(unittest.TestCase):
    def test_attaches_octave_comma_to_syllable(self):
        row = _runs((10, "d"), (18, ","), (40, ":"), (60, "-"))
        merged = merge_close_glyphs(row)
        self.assertEqual([r.text for r in merged], ["d,", ":", "-"])

    def test_attaches_dot_subdivision(self):
        row = _runs((10, "m"), (22, "."), (26, "r"), (50, "|"), (70, "d"))
        merged = merge_close_glyphs(row)
        self.assertEqual([r.text for r in merged], ["m.r", "|", "d"])

    def test_barline_splits_measures(self):
        row = merge_close_glyphs(
            _runs((10, "d"), (18, ","), (40, ":"), (60, "-"), (80, "|"), (100, "-"), (120, ":"), (140, "-"))
        )
        measures = row_to_measures(row)
        self.assertEqual(measures, [["d,", "-"], ["-", "-"]])


class TestCoordinateScale(unittest.TestCase):
    """Régression : les runs OCR/YOLO sont en pixels (300 dpi) alors que les
    seuils de layout.py sont en points (72 dpi). Sans normalisation, les écarts
    ~4× trop grands sur-découpent les systèmes (4 voix → 1-2) et fabriquent des
    barres/silences fantômes. `normalize_page_runs` ramène en points et corrige."""

    _SCALE = 300 / 72  # ≈ 4.17

    def _voice_row(self, y, x0=60.0):
        toks = ["d", ":", "r", ":", "m", ":", "f", "|",
                "s", ":", "l", ":", "t", ":", "d"]
        x = x0
        out = []
        for t in toks:
            out.append(Run(y=y, x=x, font="F10", text=t))
            x += 10 if t in (":", "|") else 16
        return out

    def _page_points(self):
        runs = [Run(y=730.0, x=20.0, font="F14", text="Do dia C 4/4")]
        y = 700.0
        for _sys in range(3):
            for _v in range(4):
                runs += self._voice_row(y)
                y -= 16.0            # écart inter-voix (points)
            y -= 54.0                # écart inter-système (points)
        return runs

    def test_points_scale_finds_four_voices(self):
        doc = build_document(self._page_points())
        self.assertEqual(doc.voice_names, ["Soprano", "Alto", "Tenor", "Bass"])

    def test_pixel_scale_breaks_voice_grouping(self):
        px = [Run(y=r.y * self._SCALE, x=r.x * self._SCALE, font=r.font, text=r.text)
              for r in self._page_points()]
        doc = build_document(px)
        # sans normalisation : le regroupement échoue (pas 4 voix SATB).
        self.assertNotEqual(doc.voice_names, ["Soprano", "Alto", "Tenor", "Bass"])

    def test_normalization_restores_four_voices(self):
        from app.pdf.ocr import normalize_page_runs
        px = [Run(y=r.y * self._SCALE, x=r.x * self._SCALE, font=r.font, text=r.text)
              for r in self._page_points()]
        doc = build_document(normalize_page_runs(px, self._SCALE))
        self.assertEqual(doc.voice_names, ["Soprano", "Alto", "Tenor", "Bass"])
        # et pas d'explosion de mesures (6 = 3 systèmes × 2 mesures).
        self.assertEqual([v.count("|") + 1 for v in doc.voices], [6, 6, 6, 6])


class TestBarlineNoiseFilter(unittest.TestCase):
    """Fix 2/4 : une bande dominée par des '|' (trait de mesure éclaté en y par
    l'OCR/YOLO) n'est PAS une voix — elle créait une 5e voix fantôme sur mivavaha."""

    def test_barline_noise_band_rejected(self):
        from app.pdf.layout import _is_voice_row
        # 4 barres (trait de mesure éclaté) + 1 note + 1 tenue égarées, aucun ':'.
        band = _runs((10, "|"), (60, "|"), (110, "|"), (160, "|"),
                     (90, "d"), (140, "-"))
        self.assertFalse(_is_voice_row(band))

    def test_real_voice_row_accepted(self):
        from app.pdf.layout import _is_voice_row
        row = _runs((10, "d"), (20, ":"), (30, "r"), (40, ":"),
                    (50, "m"), (60, ":"), (70, "f"), (80, "|"))
        self.assertTrue(_is_voice_row(row))

    def test_resting_voice_row_still_a_voice(self):
        from app.pdf.layout import _is_voice_row
        # voix au repos : grille de temps ':' + une barre -> reste une voix.
        row = _runs((10, ":"), (30, ":"), (50, ":"), (70, "|"),
                    (90, ":"), (110, ":"), (130, ":"), (150, "|"))
        self.assertTrue(_is_voice_row(row))


class TestHeaderMeterClamp(unittest.TestCase):
    """Fix 5 : une signature OCR aberrante (ex. 4/64) est rejetée → défaut 4/4."""

    def _hdr(self, text):
        from app.pdf.layout import parse_header
        return parse_header([[Run(y=700.0, x=20.0, font="F14", text=text)]])

    def test_aberrant_denominator_falls_back_to_default(self):
        h = self._hdr("Do dia C 4/64")   # OCR aberrant
        self.assertEqual((h.beats, h.beat_type), (4, 4))

    def test_plausible_simple_meter_accepted(self):
        h = self._hdr("Do dia C 3/4")
        self.assertEqual((h.beats, h.beat_type), (3, 4))

    def test_plausible_compound_meter_accepted(self):
        h = self._hdr("Do dia C 6/8")
        self.assertEqual((h.beats, h.beat_type), (6, 8))

    def test_absurd_beats_rejected(self):
        h = self._hdr("Do dia C 44/4")
        self.assertEqual((h.beats, h.beat_type), (4, 4))

    def test_extracts_title_composer_and_tonic(self):
        # Contrat de la passe Tesseract en-tête : titre + « Do dia A » + compositeur.
        from app.pdf.layout import parse_header
        rows = [
            [Run(y=760.0, x=300.0, font="text", text="MIVAVAHA")],
            [Run(y=740.0, x=40.0, font="text", text="Do dia A")],
            [Run(y=745.0, x=600.0, font="text", text="ANDRIAMIADAMAHATRATRA")],
        ]
        h = parse_header(rows)
        self.assertEqual(h.title, "MIVAVAHA")
        self.assertEqual(h.tonic, "A")
        self.assertEqual(h.composer, "ANDRIAMIADAMAHATRATRA")


class TestTonicOverride(unittest.TestCase):
    """Step 2 : forcer la tonique (scan sans en-tête lisible)."""

    JESOA = Path(__file__).resolve().parents[3] / "docs" / "jesoa-tsy-mba-mandao.pdf"

    @unittest.skipUnless(JESOA.is_file(), "fixture jesoa absente")
    def test_override_applied_end_to_end(self):
        from app.pdf.document import pdf_to_score
        res = pdf_to_score(self.JESOA, tonic_override="A")
        self.assertEqual(res["header"]["tonic"], "A")
        self.assertTrue(all(v["model"]["tonic"] == "A" for v in res["voices"]))


class TestPadCompoundMeterCapacity(unittest.TestCase):
    """Fix 6 : le padding en silences utilise la vraie capacité (classify_meter),
    pas beats*divisions (faux en mesure composée)."""

    def test_six_eight_padding_uses_twelve_not_twentyfour(self):
        from app.pdf.document import _pad_models_to_equal_length
        from app.solfa.model import Measure, NoteEl, Pitch, ScoreModel

        def model_68(nmeas):
            meas = [
                Measure(number=i + 1,
                        notes=[NoteEl(False, 2, "eighth", 0, Pitch("C", 0, 4, "d"))] * 6)
                for i in range(nmeas)
            ]
            return ScoreModel(tonic="C", fifths=0, beats=6, beat_type=8,
                              divisions=4, clef="treble", measures=meas)

        long_m, short_m = model_68(3), model_68(1)
        _pad_models_to_equal_length([long_m, short_m])
        self.assertEqual(len(short_m.measures), 3)             # aligné
        padded = short_m.measures[-1]
        # capacité 6/8 = 12 divisions (et non 6*4 = 24).
        self.assertEqual(sum(n.duration for n in padded.notes), 12)


class TestClefByTessiture(unittest.TestCase):
    """Fix 3 : les voix génériques (« Voix N ») reçoivent une clef selon leur
    tessiture ; la voix grave passe en clé de fa. Les noms SATB explicites gardent
    leur clef."""

    def _mk(self, name, step, octave):
        from app.solfa.model import Measure, NoteEl, Pitch, ScoreModel
        return ScoreModel(
            tonic="C", fifths=0, beats=4, beat_type=4, divisions=4, clef="treble",
            measures=[Measure(1, [NoteEl(False, 4, "quarter", 0,
                                          Pitch(step, 0, octave, "d"))])],
            part_name=name,
        )

    def test_generic_low_voice_gets_bass_clef(self):
        from app.pdf.document import _assign_clefs_by_tessiture
        low = self._mk("Voix 4", "C", 3)    # do3 -> médiane 36 < 48 -> fa
        high = self._mk("Voix 1", "G", 4)   # sol4 -> 55 -> sol
        _assign_clefs_by_tessiture([low, high])
        self.assertEqual(low.clef, "bass")
        self.assertEqual(high.clef, "treble")

    def test_named_voice_untouched(self):
        from app.pdf.document import _assign_clefs_by_tessiture
        named = self._mk("Bass", "C", 3)    # nom explicite -> non recalculé
        _assign_clefs_by_tessiture([named])
        self.assertEqual(named.clef, "treble")


class TestStripLeadingEmptyMeasures(unittest.TestCase):
    """Fix 1 : les mesures de tête muettes dans TOUTES les voix (artefact type
    « 2 mesures de silence » masquant une anacrouse) sont retirées."""

    def _rest(self, n):
        from app.solfa.model import Measure, NoteEl
        return Measure(n, [NoteEl(True, 16, "whole", 0)])

    def _note(self, n):
        from app.solfa.model import Measure, NoteEl, Pitch
        return Measure(n, [NoteEl(False, 16, "whole", 0, Pitch("C", 0, 4, "d"))])

    def _model(self, measures):
        from app.solfa.model import ScoreModel
        return ScoreModel(tonic="C", fifths=0, beats=4, beat_type=4, divisions=4,
                          clef="treble", measures=measures)

    def test_strips_leading_all_rest(self):
        from app.pdf.document import _strip_leading_empty_measures
        v1 = self._model([self._rest(1), self._rest(2), self._note(3)])
        v2 = self._model([self._rest(1), self._rest(2), self._note(3)])
        _strip_leading_empty_measures([v1, v2])
        self.assertEqual(len(v1.measures), 1)
        self.assertEqual(len(v2.measures), 1)
        self.assertEqual(v1.measures[0].number, 1)

    def test_keeps_when_a_voice_has_content(self):
        from app.pdf.document import _strip_leading_empty_measures
        v1 = self._model([self._note(1), self._rest(2)])   # v1 sonne en mes.1
        v2 = self._model([self._rest(1), self._rest(2)])
        _strip_leading_empty_measures([v1, v2])
        self.assertEqual(len(v1.measures), 2)  # rien retiré


class TestHymn244(unittest.TestCase):
    HYMN = Path(__file__).resolve().parents[3] / "docs" / "244.pdf"

    @unittest.skipUnless(HYMN.is_file(), "fixture docs/244.pdf absente")
    def test_sixteen_measures_db_major_measure6_is_lah(self):
        from app.pdf.document import pdf_to_document, pdf_to_score

        doc = pdf_to_document(self.HYMN)
        self.assertEqual(doc.header.tonic, "Db")
        self.assertEqual((doc.header.beats, doc.header.beat_type), (3, 4))
        self.assertEqual([v.count("|") + 1 for v in doc.voices], [16, 16, 16, 16])
        self.assertEqual(doc.voices[0].split("|")[5].strip(), "l : - : l")

        result = pdf_to_score(self.HYMN)
        self.assertEqual(result["voices"][0]["model"]["fifths"], -5)  # Db majeur
        m6 = result["voices"][0]["model"]["measures"][5]["notes"]
        pitched = [n for n in m6 if not n["isRest"]]
        self.assertTrue(pitched)
        # lah en Db = Sib
        self.assertEqual(pitched[0]["pitch"]["step"], "B")
        self.assertEqual(pitched[0]["pitch"]["alter"], -1)
        self.assertEqual(pitched[0]["pitch"]["syllable"], "l")


class TestLordBlessParse(unittest.TestCase):
    @unittest.skipUnless(LORD_BLESS.is_file(), "fixture absente")
    def test_no_orphan_octave_cell(self):
        """Repro 422 : cellule invalide ', ' (virgule d'octave orpheline)."""
        try:
            result = pdf_to_score(LORD_BLESS)
        except PdfSolfaError as exc:
            self.fail(f"pdf_to_score a levé PdfSolfaError: {exc}")
        self.assertGreaterEqual(len(result["voices"]), 1)
        for voice in result["voices"]:
            try:
                tokenize(voice["notation"])
            except LexError as exc:
                self.fail(f"{voice['name']}: {exc} dans {voice['notation'][:120]!r}")

    @unittest.skipUnless(LORD_BLESS.is_file(), "fixture absente")
    def test_satb_has_full_piece_not_just_intro(self):
        """Repro : OSMD ne montrait que 2 mesures (voix courtes / mauvais systèmes)."""
        import xml.etree.ElementTree as ET

        result = pdf_to_score(LORD_BLESS)
        self.assertEqual(
            [v["name"] for v in result["voices"]],
            ["Soprano", "Alto", "Tenor", "Bass"],
        )
        counts = [len(v["model"]["measures"]) for v in result["voices"]]
        self.assertTrue(all(c == counts[0] for c in counts), counts)
        self.assertGreaterEqual(counts[0], 20, f"trop peu de mesures: {counts}")

        root = ET.fromstring(result["musicxml"][result["musicxml"].index("<score-partwise"):])
        part_counts = [len(p.findall("measure")) for p in root.findall("part")]
        self.assertTrue(all(c == part_counts[0] for c in part_counts), part_counts)
        self.assertGreaterEqual(part_counts[0], 20)

    @unittest.skipUnless(LORD_BLESS.is_file(), "fixture absente")
    def test_header_gb_major_4_4_and_soprano_intro(self):
        """Do dia Gb, 4/4 ; mesures 1–~8 = Soprano seul (autres = silences)."""
        from app.pdf.document import pdf_to_document

        doc = pdf_to_document(LORD_BLESS)
        self.assertEqual(doc.header.tonic, "Gb")
        self.assertEqual((doc.header.beats, doc.header.beat_type), (4, 4))

        result = pdf_to_score(LORD_BLESS)
        self.assertEqual(result["header"]["tonic"], "Gb")
        sop = result["voices"][0]
        alto = result["voices"][1]
        self.assertEqual(sop["model"]["timeSignature"], {"beats": 4, "beatType": 4})
        self.assertEqual(sop["model"]["fifths"], -6)  # Gb majeur

        # Intro monodique : les premières mesures Alto sont des silences.
        for i in range(min(6, len(alto["model"]["measures"]))):
            notes = alto["model"]["measures"][i]["notes"]
            self.assertTrue(
                all(n["isRest"] for n in notes),
                f"Alto mesure {i+1} devrait être silence, got {notes}",
            )
        # Soprano chante tôt (contenu dans les 3 premières mesures) — la
        # mesure 1 est un silence, l'entrée se fait sur l'anacrouse « .m » (m2).
        early = [n for i in range(3) for n in sop["model"]["measures"][i]["notes"]]
        self.assertTrue(any(not n["isRest"] for n in early))

    @unittest.skipUnless(LORD_BLESS.is_file(), "fixture absente")
    def test_tenor_bass_rest_after_dotted_half_not_shifted(self):
        """Après la blanche pointée m18, T/B restent silencieux ; reprise plus tard."""
        from app.pdf.document import pdf_to_document

        doc = pdf_to_document(LORD_BLESS)
        tenor = [b.strip() for b in doc.voices[2].split("|")]
        bass = [b.strip() for b in doc.voices[3].split("|")]
        sop = [b.strip() for b in doc.voices[0].split("|")]

        def has_pitch(bar: str) -> bool:
            return any(c.isalpha() for c in bar.replace("-", ""))

        ti = next(i for i, b in enumerate(tenor) if b.startswith("t,") and "- : -" in b)
        bi = next(i for i, b in enumerate(bass) if b.startswith("m,") and "- : -" in b)
        self.assertEqual(ti, bi)

        for name, bars, i in (("Tenor", tenor, ti), ("Bass", bass, bi)):
            self.assertFalse(
                has_pitch(bars[i + 1]),
                f"{name} m{i+2} devrait être silence, got {bars[i+1]!r}",
            )
            self.assertFalse(
                has_pitch(bars[i + 2]),
                f"{name} m{i+3} devrait être silence, got {bars[i+2]!r}",
            )

        self.assertTrue(
            any(has_pitch(tenor[i]) for i in range(ti + 3, min(ti + 8, len(tenor)))),
            "Tenor sans reprise après silences",
        )
        self.assertTrue(has_pitch(sop[ti]) or has_pitch(sop[ti + 1]), "Soprano actif")

    @unittest.skipUnless(LORD_BLESS.is_file(), "fixture absente")
    def test_m18_tenor_bass_dotted_half_then_rest(self):
        """m18 T/B : blanche pointée (3 temps) + silence, pas ronde ni mesure vide."""
        from app.pdf.document import pdf_to_document, pdf_to_score

        doc = pdf_to_document(LORD_BLESS)
        result = pdf_to_score(LORD_BLESS)

        # Trouver la mesure « t, : - : - : » / « m, : - : - : ».
        for vi, startswith in ((2, "t,"), (3, "m,")):
            bars = [b.strip() for b in doc.voices[vi].split("|")]
            idx = next(i for i, b in enumerate(bars) if b.startswith(startswith) and "- : -" in b)
            self.assertTrue(
                bars[idx].rstrip().endswith(":") or bars[idx].endswith(": "),
                f"dernier temps silence attendu: {bars[idx]!r}",
            )
            notes = result["voices"][vi]["model"]["measures"][idx]["notes"]
            pitched = [n for n in notes if not n["isRest"]]
            rests = [n for n in notes if n["isRest"]]
            self.assertEqual(len(pitched), 1, pitched)
            self.assertEqual(pitched[0]["duration"], 12)  # blanche pointée
            self.assertEqual(pitched[0]["dots"], 1)
            self.assertTrue(rests)
            self.assertEqual(sum(n["duration"] for n in rests), 4)

    @unittest.skipUnless(LORD_BLESS.is_file(), "fixture absente")
    def test_m19_soprano_alto_both_mi_two_beats(self):
        """m19 S/A : mi mi sur les 2 premiers temps (tonique Gb → Sib)."""
        from app.pdf.document import pdf_to_document, pdf_to_score

        doc = pdf_to_document(LORD_BLESS)
        result = pdf_to_score(LORD_BLESS)
        sop_bars = [b.strip() for b in doc.voices[0].split("|")]
        idx = next(i for i, b in enumerate(sop_bars) if b.startswith("m : m : fi"))
        self.assertEqual(doc.voices[1].split("|")[idx].strip().split(":")[0].strip(), "m")
        self.assertEqual(doc.voices[1].split("|")[idx].strip().split(":")[1].strip(), "m")

        for vi in (0, 1):
            notes = result["voices"][vi]["model"]["measures"][idx]["notes"]
            first_two = []
            acc = 0
            for n in notes:
                if acc >= 8:
                    break
                if not n["isRest"]:
                    first_two.append(n)
                acc += n["duration"]
            self.assertGreaterEqual(len(first_two), 1)
            for n in first_two:
                self.assertEqual(n["pitch"]["syllable"], "m")
                self.assertEqual(n["pitch"]["step"], "B")
                self.assertEqual(n["pitch"]["alter"], -1)


    @unittest.skipUnless(LORD_BLESS.is_file(), "fixture absente")
    def test_ground_truth_incipit(self):
        """Vérité terrain fournie (docs/the-lord.md) : m1-8 Soprano + m13 SATB.

        Valide la grille x : erreur du « : » manquant (m3) absorbée par la
        position, voix A/T/B entrant tard alignées, tenues conservées.
        """
        from app.pdf.document import pdf_to_document

        doc = pdf_to_document(LORD_BLESS)
        self.assertEqual((doc.header.tonic, doc.header.beats, doc.header.beat_type),
                         ("Gb", 4, 4))

        def bars(v):
            return [[c.strip() for c in b.split(":")] for b in doc.voices[v].split("|")]

        soprano_m1_8 = [
            ["", "", "", ""],
            ["", "", "", ".m"],
            ["m", "-.m", "m.m", "r.m"],
            ["r", "d", "-", "-.d"],
            ["d", "t,.d", "r", "d"],
            ["s", "-.f", "m.r", "-.r"],
            ["l", "-.s", "f.m", "s.f"],
            ["f", "m", "-", "d.r"],
        ]
        self.assertEqual(bars(0)[:8], soprano_m1_8)

        # Mesure 13 : les 4 voix SATB (toutes présentes, alignées).
        m13 = [bars(v)[12] for v in range(4)]
        self.assertEqual(m13, [
            ["d", "t,.d", "r", "d"],
            ["d", "t,.d", "r", "d"],
            ["l", "l.l", "s", "s"],
            ["f", "f.f", "m", "m"],
        ])

        # Mesure 21 (début de système) : temps 1 = note, pas silence — vérifie
        # que l'origine résiste à un « | » parasite (bug corrigé).
        self.assertEqual(bars(0)[20], ["si", "-.di", "di", "ri"])
        self.assertEqual(bars(1)[20], ["di", "-.d", "ta,", "d.ta,"])

        # 44 mesures sans anacrouse (tolérance sur d'éventuels silences finaux).
        counts = [v.count("|") + 1 for v in doc.voices]
        self.assertTrue(all(c == counts[0] for c in counts), counts)
        self.assertGreaterEqual(counts[0], 44)

    @unittest.skipUnless(LORD_BLESS.is_file(), "fixture absente")
    def test_m10_soprano_dotted_half_atb_enter_on_anacrusis(self):
        """m10 : S mi blanche pointée + anacrouse ; ATB entrent à la levée (pas m9)."""
        from app.pdf.document import pdf_to_document, pdf_to_score

        doc = pdf_to_document(LORD_BLESS)
        result = pdf_to_score(LORD_BLESS)
        sop = [b.strip() for b in doc.voices[0].split("|")]
        idx = next(i for i, b in enumerate(sop) if b == "m : - : - : .m" or b.startswith("m : - : - : .m"))

        s_notes = result["voices"][0]["model"]["measures"][idx]["notes"]
        self.assertEqual(s_notes[0]["pitch"]["syllable"], "m")
        self.assertEqual(s_notes[0]["duration"], 12)
        self.assertEqual(s_notes[0]["dots"], 1)
        self.assertTrue(s_notes[1]["isRest"])
        self.assertEqual(s_notes[1]["duration"], 2)
        self.assertEqual(s_notes[2]["pitch"]["syllable"], "m")

        for vi, name in ((1, "Alto"), (2, "Tenor"), (3, "Bass")):
            bars = [b.strip() for b in doc.voices[vi].split("|")]
            # Pas d'entrée sur m9 (mesure avant) : seulement silences.
            prev = bars[idx - 1]
            self.assertFalse(
                any(c.isalpha() for c in prev.replace("-", "")),
                f"{name} m{idx} ne doit pas encore chanter: {prev!r}",
            )
            # Levée sur m10.
            self.assertIn(".m", bars[idx], f"{name} m{idx+1}: {bars[idx]!r}")
            # Descente sur m11.
            self.assertTrue(
                bars[idx + 1].startswith("m"),
                f"{name} m{idx+2} entrée: {bars[idx+1]!r}",
            )

    @unittest.skipUnless(LORD_BLESS.is_file(), "fixture absente")
    def test_holds_remain_half_notes_not_rests(self):
        """Les « - » après une note restent des tenues (blanche), pas des silences."""
        from app.pdf.document import pdf_to_document, pdf_to_score

        doc = pdf_to_document(LORD_BLESS)
        result = pdf_to_score(LORD_BLESS)
        sop = [b.strip() for b in doc.voices[0].split("|")]

        idx = next(i for i, b in enumerate(sop) if b.startswith("s : fi : -"))
        notes = result["voices"][0]["model"]["measures"][idx]["notes"]
        self.assertFalse(any(n["isRest"] for n in notes), notes)
        fi = [n for n in notes if not n["isRest"] and n["pitch"]["syllable"] == "fi"]
        self.assertTrue(fi)
        self.assertEqual(fi[0]["duration"], 12)
        self.assertEqual(fi[0]["dots"], 1)


if __name__ == "__main__":
    unittest.main()
