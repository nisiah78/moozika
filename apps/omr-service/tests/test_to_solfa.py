"""Tests pour `to_solfa.py` : ScoreModel → texte sol-fa.

Test principal : round-trip `parse_solfa(n) → to_solfa → re-parse → modèle identique`.
On réutilise le corpus de test_parser.py (toutes les notations y sont exercées).
"""
import unittest

from app.solfa.parser import parse_solfa
from app.solfa.to_solfa import to_solfa
from app.solfa.from_musicxml import from_musicxml
from app.solfa.musicxml import to_musicxml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _notes(model, measure_idx=0):
    """Liste des NoteEl d'une mesure."""
    return model.measures[measure_idx].notes


def _roundtrip(notation, tonic="C", doh_octave=4, beats=None, beat_type=4, **kw):
    """parse → to_solfa → re-parse. Renvoie (m1, canonical_text, m2)."""
    kw2 = {"tonic": tonic, "doh_octave": doh_octave, **kw}
    m1 = parse_solfa(notation, **kw2)
    text = to_solfa(m1)
    # Signature explicite pour que parse_solfa n'ait pas à la déduire
    # (la 1ère mesure du canonical a toujours le bon nb de temps).
    m2 = parse_solfa(text, tonic=tonic, doh_octave=doh_octave)
    return m1, text, m2


def _assert_models_equal(tc, m1, m2):
    """Compare deux modèles note par note (durée, hauteur, repos)."""
    tc.assertEqual(len(m1.measures), len(m2.measures),
                   "nombre de mesures différent")
    for mi in range(len(m1.measures)):
        n1s = _notes(m1, mi)
        n2s = _notes(m2, mi)
        tc.assertEqual(len(n1s), len(n2s),
                       f"mesure {mi+1}: nb de notes différent")
        for ni, (n1, n2) in enumerate(zip(n1s, n2s)):
            msg = f"mesure {mi+1} note {ni}"
            tc.assertEqual(n1.is_rest, n2.is_rest, msg + " is_rest")
            tc.assertEqual(n1.duration, n2.duration, msg + " duration")
            if not n1.is_rest:
                tc.assertEqual(n1.pitch.step, n2.pitch.step, msg + " step")
                tc.assertEqual(n1.pitch.alter, n2.pitch.alter, msg + " alter")
                tc.assertEqual(n1.pitch.octave, n2.pitch.octave, msg + " octave")


# ---------------------------------------------------------------------------
# Round-trip : corpus de test_parser.py
# ---------------------------------------------------------------------------

class TestRoundTripCorpus(unittest.TestCase):
    """Toutes les notations du corpus test_parser → to_solfa → re-parse = identique."""

    def _rt(self, notation, **kw):
        m1, text, m2 = _roundtrip(notation, **kw)
        _assert_models_equal(self, m1, m2)
        return text  # pour d'éventuelles assertions supplémentaires

    def test_twinkle(self):
        self._rt("d : d : s : s | l : l : s : -")

    def test_subdivision_two_beats(self):
        text = self._rt("d.r : m")
        self.assertIn("d.r", text)
        self.assertIn("m", text)

    def test_rest(self):
        text = self._rt("d : : m : m")
        # le temps vide (silence) produit une cellule vide entre deux ' : '
        self.assertIn(" :  : ", text)

    def test_tie_across_barline(self):
        # La continuation en début de m2 doit produire un '-' de début.
        text = self._rt("d : d : d : d | - : d : d : d")
        parts = text.split(" | ")
        self.assertEqual(len(parts), 2)
        # m2 doit commencer par '-' (hold/continuation)
        self.assertTrue(parts[1].lstrip().startswith("-"))

    def test_octave_marks(self):
        text = self._rt("d : d'")
        self.assertIn("d'", text)

    def test_leading_dot_anacrusis_is_rest(self):
        self._rt("m : - : - : .m")

    def test_hold_dot_continues_previous(self):
        # d noire pointée + m croche en 2/4.
        self._rt("d : -.m")

    def test_dotted_quarter_via_hold_dot(self):
        self._rt("d : -.d")

    def test_comma_quarter_rest(self):
        # Canonical peut différer de -.,d (→ -,-.,d) mais le modèle est identique.
        self._rt("d : -.,d")

    def test_trailing_comma_is_octave_not_rhythm(self):
        text = self._rt("t, : d'")
        self.assertIn("t,", text)
        self.assertIn("d'", text)


# ---------------------------------------------------------------------------
# Contenu textuel (format canonique)
# ---------------------------------------------------------------------------

class TestCanonicalForm(unittest.TestCase):
    """Vérifications sur la forme textuelle produite."""

    def test_beats_joined_by_colon(self):
        m = parse_solfa("d : r : m : f", tonic="C")
        text = to_solfa(m)
        self.assertEqual(text.count(" : "), 3)

    def test_measures_joined_by_pipe(self):
        m = parse_solfa("d : r : m : f | s : l : t : d'", tonic="C")
        text = to_solfa(m)
        self.assertEqual(text.count(" | "), 1)

    def test_half_note_renders_as_note_then_hold(self):
        m = parse_solfa("s : -", tonic="C")
        text = to_solfa(m)
        self.assertEqual(text, "s : -")

    def test_whole_note_four_four(self):
        m = parse_solfa("d : - : - : -", tonic="C")
        text = to_solfa(m)
        self.assertEqual(text, "d : - : - : -")

    def test_eighth_pair_uses_dot(self):
        m = parse_solfa("d.r : m", tonic="C")
        text = to_solfa(m)
        beat0 = text.split(" : ")[0]
        self.assertEqual(beat0, "d.r")

    def test_rest_beat_empty(self):
        m = parse_solfa("d : : m : m", tonic="C")
        text = to_solfa(m)
        beats = text.split(" : ")
        self.assertEqual(beats[1], "")  # 2e temps = silence = vide

    def test_sharps_rendered(self):
        # fi = fa dièse en Do majeur (degré 4 haussé)
        m = parse_solfa("fi : s", tonic="C")
        text = to_solfa(m)
        self.assertIn("fi", text)

    def test_flats_rendered(self):
        m = parse_solfa("ta : l", tonic="C")
        text = to_solfa(m)
        self.assertIn("ta", text)


# ---------------------------------------------------------------------------
# En-tête (include_header)
# ---------------------------------------------------------------------------

class TestHeader(unittest.TestCase):
    def test_header_contains_doh(self):
        m = parse_solfa("d : r", tonic="G")
        text = to_solfa(m, include_header=True)
        self.assertIn("doh = G", text)

    def test_header_contains_time_sig(self):
        m = parse_solfa("d : r", tonic="C")
        text = to_solfa(m, include_header=True)
        self.assertIn("2/4", text)

    def test_header_contains_tempo_when_set(self):
        m = parse_solfa("d : r", tonic="C", tempo=75)
        text = to_solfa(m, include_header=True)
        self.assertIn("75", text)

    def test_no_header_by_default(self):
        m = parse_solfa("d : r", tonic="C")
        text = to_solfa(m)
        self.assertNotIn("doh", text)

    def test_notation_on_second_line_with_header(self):
        m = parse_solfa("d : r", tonic="C")
        text = to_solfa(m, include_header=True)
        lines = text.split("\n")
        self.assertEqual(len(lines), 2)
        # 2e ligne = notation re-parseable
        m2 = parse_solfa(lines[1], tonic="C")
        _assert_models_equal(self, m, m2)


# ---------------------------------------------------------------------------
# Round-trip via MusicXML (aller-retour complet)
# ---------------------------------------------------------------------------

class TestRoundTripViaMusicXml(unittest.TestCase):
    """parse_solfa → MusicXML → from_musicxml → to_solfa → re-parse ≡ original."""

    def _full_rt(self, notation, tonic="C"):
        original = parse_solfa(notation, tonic=tonic)
        xml = to_musicxml(original)
        read_back = from_musicxml(xml)[0]
        text = to_solfa(read_back)
        reparse = parse_solfa(text, tonic=tonic)
        _assert_models_equal(self, original, reparse)

    def test_simple_melody(self):
        self._full_rt("d : r : m : f | s : l : t : d'")

    def test_half_note(self):
        self._full_rt("s : -")

    def test_rests(self):
        self._full_rt("d : : m : m")

    def test_dotted(self):
        self._full_rt("d : -.m")

    def test_sharps(self):
        self._full_rt("fi : s : la : t")

    def test_different_tonic(self):
        self._full_rt("d : r : m : f", tonic="G")


# ---------------------------------------------------------------------------
# 6/8 chorale (6 croches, comme 10/8)
# ---------------------------------------------------------------------------

class TestSixEightChoraleToSolfa(unittest.TestCase):
    """Round-trip 6/8 en grille à 6 croches (``| 1 : 2 : 3 ! 4 : 5 : 6 |``)."""

    def test_six_eight_round_trip(self):
        m1 = parse_solfa("d : r : m ! f : s : l", tonic="C", beats=6, beat_type=8)
        text = to_solfa(m1)
        m2 = parse_solfa(text, tonic="C", beats=6, beat_type=8)
        _assert_models_equal(self, m1, m2)
        import re
        bar = text.split("|")[0].strip()
        n_pulses = len(re.split(r"\s*[:!]\s*", bar))
        self.assertEqual(n_pulses, 6)

    def test_six_eight_holds(self):
        m1 = parse_solfa("d : - : m ! f : - : l", tonic="C", beats=6, beat_type=8)
        text = to_solfa(m1)
        m2 = parse_solfa(text, tonic="C", beats=6, beat_type=8)
        _assert_models_equal(self, m1, m2)


# ---------------------------------------------------------------------------
# Subdivisions : uniquement des points (jamais de ',' rythmique)
# ---------------------------------------------------------------------------

class TestDotOnlySubdivision(unittest.TestCase):
    """Le rendu n'utilise que '.' pour subdiviser ; le ',' reste réservé à
    l'octave grave. Les silences de sous-temps utilisent '0'."""

    def test_four_sixteenths_use_dots_not_commas(self):
        m = parse_solfa("d.r.m.f : s : l : t", tonic="C")
        text = to_solfa(m)
        self.assertEqual(text.split(" : ")[0], "d.r.m.f")
        # aucune virgule (ni rythme ni octave ici)
        self.assertNotIn(",", text)
        _assert_models_equal(self, m, parse_solfa(text, tonic="C"))

    def test_grave_note_keeps_octave_comma_only(self):
        # s, (soh grave) : la seule virgule doit être la marque d'octave.
        m = parse_solfa("s, : s,.s,.s,.s,", tonic="C")
        text = to_solfa(m)
        self.assertNotIn(",,", text)          # pas de collision rythme+octave
        self.assertIn("s,", text)
        _assert_models_equal(self, m, parse_solfa(text, tonic="C"))

    def test_subbeat_rest_uses_zero_and_roundtrips(self):
        # noire + double-croche + silence de double-croche dans un temps.
        m = parse_solfa("m : d.r.m.0", tonic="C")
        text = to_solfa(m)
        # le silence interne (après contenu) est rendu par '0', pas un vide
        self.assertIn("0", text.split(" : ")[1])
        _assert_models_equal(self, m, parse_solfa(text, tonic="C"))

    def test_leading_rest_stays_empty(self):
        # silence en tête de temps -> forme « .m » (vide), pas « 0.m ».
        m = parse_solfa("m : - : - : .m", tonic="C")
        text = to_solfa(m)
        self.assertIn(".m", text)
        self.assertNotIn("0", text)


# ---------------------------------------------------------------------------
# Option grille au 8e (min_cell)
# ---------------------------------------------------------------------------

class TestEighthGridOption(unittest.TestCase):
    """min_cell=2 recale sur la croche et allège le rendu (absorbe le jitter)."""

    def test_eighth_grid_collapses_sixteenth_jitter(self):
        # quatre doubles-croches d d d d -> à la croche : d d (2 croches).
        m = parse_solfa("d.d.d.d : r.r.r.r", tonic="C")
        coarse = to_solfa(m, min_cell=2)
        # chaque temps ne contient plus qu'une subdivision (deux croches)
        self.assertEqual(coarse.split(" : ")[0], "d.d")
        self.assertEqual(coarse.split(" : ")[1], "r.r")

    def test_eighth_grid_keeps_measure_length(self):
        m = parse_solfa("d.r.m.f : s : l : t", tonic="C")
        coarse = to_solfa(m, min_cell=2)
        reparse = parse_solfa(coarse, tonic="C")
        # même nombre de mesures et durée totale conservée (4 temps = 16 div)
        self.assertEqual(len(reparse.measures), 1)
        self.assertEqual(
            sum(n.duration for n in reparse.measures[0].notes), 16
        )

    def test_full_resolution_is_default(self):
        m = parse_solfa("d.r.m.f : s : l : t", tonic="C")
        b0_full = to_solfa(m).split(" : ")[0]
        b0_eighth = to_solfa(m, min_cell=2).split(" : ")[0]
        self.assertEqual(b0_full, "d.r.m.f")   # min_cell=1 par défaut (16e)
        # 8e : on garde les notes SUR la grille (positions 0 et 2 = d et m).
        self.assertEqual(b0_eighth, "d.m")


if __name__ == "__main__":
    unittest.main()
