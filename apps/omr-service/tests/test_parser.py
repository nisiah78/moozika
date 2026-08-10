import unittest

from app.solfa.parser import ParseError, parse_solfa


class TestParser(unittest.TestCase):
    def test_twinkle_phrase(self):
        # "Twinkle twinkle little star" en do majeur : C C G G A A G(tenu).
        model = parse_solfa("d : d : s : s | l : l : s : -", tonic="C")
        self.assertEqual(model.beats, 4)
        self.assertEqual(len(model.measures), 2)

        m1 = model.measures[0]
        self.assertEqual([n.pitch.step for n in m1.notes], ["C", "C", "G", "G"])
        self.assertTrue(all(n.note_type == "quarter" for n in m1.notes))

        m2 = model.measures[1]
        # l, l puis s prolongé -> blanche.
        self.assertEqual([n.pitch.step for n in m2.notes], ["A", "A", "G"])
        self.assertEqual(m2.notes[-1].note_type, "half")

    def test_subdivision_two_beats(self):
        model = parse_solfa("d.r : m", tonic="C")
        self.assertEqual(model.beats, 2)
        notes = model.measures[0].notes
        self.assertEqual([n.note_type for n in notes], ["eighth", "eighth", "quarter"])
        self.assertEqual([n.pitch.step for n in notes], ["C", "D", "E"])

    def test_rest(self):
        model = parse_solfa("d : : m : m", tonic="C")
        notes = model.measures[0].notes
        self.assertTrue(notes[1].is_rest)
        self.assertIsNone(notes[1].pitch)

    def test_tie_across_barline(self):
        # d tenu sur la 4e temps de m1 et le 1er de m2 -> deux noires liées.
        model = parse_solfa("d : d : d : d | - : d : d : d", tonic="C")
        self.assertEqual(len(model.measures), 2)
        last_m1 = model.measures[0].notes[-1]
        first_m2 = model.measures[1].notes[0]
        self.assertTrue(last_m1.tie_start)
        self.assertTrue(first_m2.tie_stop)
        self.assertEqual(len(model.measures[1].notes), 4)

    def test_octave_marks(self):
        model = parse_solfa("d : d'", tonic="C")
        notes = model.measures[0].notes
        self.assertEqual(notes[0].pitch.octave, 4)
        self.assertEqual(notes[1].pitch.octave, 5)

    def test_leading_dot_anacrusis_is_rest_not_hold(self):
        """``.m`` = silence croche + mi ; pas une tenue du mi précédent."""
        model = parse_solfa("m : - : - : .m", tonic="C")
        notes = model.measures[0].notes
        self.assertEqual(notes[0].pitch.step, "E")
        self.assertEqual(notes[0].duration, 12)  # blanche pointée
        self.assertEqual(notes[0].dots, 1)
        self.assertTrue(notes[1].is_rest)
        self.assertEqual(notes[1].duration, 2)
        self.assertEqual(notes[2].pitch.step, "E")
        self.assertEqual(notes[2].duration, 2)

    def test_hold_dot_continues_previous(self):
        """``-.m`` = demi-temps de tenue puis mi."""
        model = parse_solfa("d : -.m", tonic="C")
        notes = model.measures[0].notes
        # d noire + tenue croche = noire pointée, puis m croche
        self.assertEqual(notes[0].pitch.step, "C")
        self.assertEqual(notes[0].duration, 6)
        self.assertEqual(notes[0].dots, 1)
        self.assertEqual(notes[1].pitch.step, "E")
        self.assertEqual(notes[1].duration, 2)

    def test_dotted_quarter_via_hold_dot(self):
        """``d : -.d`` = do tenu 1 temps ½ (noire pointée) puis do croche."""
        model = parse_solfa("d : -.d", tonic="C")
        notes = model.measures[0].notes
        self.assertEqual(notes[0].pitch.step, "C")
        self.assertEqual(notes[0].duration, 6)   # noire pointée
        self.assertEqual(notes[0].dots, 1)
        self.assertEqual(notes[1].pitch.step, "C")
        self.assertEqual(notes[1].duration, 2)   # croche

    def test_comma_quarter_rest(self):
        """``d : -.,d`` = do 1 temps ½ + silence de quart + do (quart)."""
        model = parse_solfa("d : -.,d", tonic="C")
        notes = model.measures[0].notes
        self.assertEqual(notes[0].duration, 6)   # noire pointée
        self.assertTrue(notes[1].is_rest)        # silence d'un quart de temps
        self.assertEqual(notes[1].duration, 1)   # double-croche
        self.assertEqual(notes[2].pitch.step, "C")
        self.assertEqual(notes[2].duration, 1)

    def test_trailing_comma_is_octave_not_rhythm(self):
        """``t,`` reste une octave grave, pas un séparateur rythmique."""
        model = parse_solfa("t, : d'", tonic="C")
        notes = model.measures[0].notes
        self.assertEqual((notes[0].pitch.step, notes[0].pitch.octave), ("B", 3))
        self.assertEqual((notes[1].pitch.step, notes[1].pitch.octave), ("C", 5))
        self.assertEqual(len(notes), 2)  # pas de silence parasite

    def test_compound_meter_mark_is_not_two_four(self):
        # ``(6/8)`` avec 6 croches → en-tête 6/8 (jamais 2/4).
        model = parse_solfa("(6/8) d : r : m ! f : s : l", tonic="C")
        self.assertEqual((model.beats, model.beat_type), (6, 8))
        self.assertEqual(model.measures[0].time_signature, (6, 8))
        self.assertEqual(sum(n.duration for n in model.measures[0].notes), 12)

    def test_variable_meter_chain_ten_eight_to_six_eight_to_four_four(self):
        notation = (
            "d : d : d : d : d : d : d : d : d : d | "
            "(6/8) d : d : d ! d : d : d | d : d : d ! d : d : d | "
            "(4/4) d : d : d : d | d : d : d : d | "
            "(6/8) d : d : d ! d : d : d | "
            "(4/4) d : d : d : d"
        )
        model = parse_solfa(notation, tonic="C", beats=10, beat_type=8)
        self.assertEqual((model.beats, model.beat_type), (10, 8))
        expected = [None, (6, 8), None, (4, 4), None, (6, 8), (4, 4)]
        for i, exp in enumerate(expected):
            self.assertEqual(model.measures[i].time_signature, exp, f"m{i+1}")
        # Mesure 6/8 : 6 pulsations de croche
        self.assertEqual(sum(n.duration for n in model.measures[1].notes), 12)

    def test_mid_score_key_change(self):
        """``(Doh=X)`` en cours de partition : re-résout les syllabes contre la
        nouvelle tonique (mouvable-do) et pose l'armure sur la mesure."""
        model = parse_solfa(
            "d : r : m : f | (Doh=G) d : r : m : f | (Doh=C) d : r : m : f",
            tonic="C",
        )
        # L'en-tête garde la tonique d'ouverture.
        self.assertEqual((model.tonic, model.fifths), ("C", 0))
        # Mesure 1 : Do majeur, pas d'annotation d'armure.
        self.assertIsNone(model.measures[0].key_tonic)
        self.assertEqual(
            [n.pitch.step for n in model.measures[0].notes], ["C", "D", "E", "F"]
        )
        # Mesure 2 : (Doh=G) → syllabes relatives à Sol + armure 1 dièse.
        self.assertEqual(model.measures[1].key_tonic, "G")
        self.assertEqual(model.measures[1].key_fifths, 1)
        self.assertEqual(
            [n.pitch.step for n in model.measures[1].notes], ["G", "A", "B", "C"]
        )
        # Mesure 3 : retour à (Doh=C).
        self.assertEqual(model.measures[2].key_tonic, "C")
        self.assertEqual(model.measures[2].key_fifths, 0)
        self.assertEqual(
            [n.pitch.step for n in model.measures[2].notes], ["C", "D", "E", "F"]
        )

    def test_errors(self):
        with self.assertRaises(ParseError):
            parse_solfa("", tonic="C")
        with self.assertRaises(ParseError):
            parse_solfa("d : x", tonic="C")  # syllabe inconnue
        with self.assertRaises(ParseError):
            parse_solfa("d : r", tonic="H")  # tonique inconnue


class TestLenientSubdivision(unittest.TestCase):
    """Subdivisions impaires (OCR/PDF) : tolérées par arrondi en mode lenient,
    rejetées en mode strict (saisie manuelle)."""

    def test_strict_rejects_odd_subdivision(self):
        # '..d' = 3 parts d'un temps de 4 divisions -> refus en strict.
        with self.assertRaises(ParseError):
            parse_solfa("d : ..d", tonic="C")

    def test_lenient_rounds_odd_subdivision(self):
        # '..d' toléré : réparti en [1, 2, 1] divisions (silence, silence, do).
        model = parse_solfa("d : ..d", tonic="C", lenient=True)
        notes = model.measures[0].notes
        # 1er temps : do (noire) ; 2e temps : deux silences + do (arrondi).
        self.assertEqual(notes[0].pitch.step, "C")
        self.assertEqual(notes[0].duration, 4)
        self.assertTrue(notes[1].is_rest and notes[2].is_rest)
        self.assertEqual(notes[-1].pitch.step, "C")
        # La mesure somme toujours à 2 temps x 4 = 8 divisions.
        self.assertEqual(sum(n.duration for n in notes), 8)

    def test_lenient_preserves_note_count_roughly(self):
        # Un triolet OCR 'd.r.m' (3 dans 4) ne doit pas crasher en lenient.
        model = parse_solfa("d.r.m : s", tonic="C", lenient=True)
        steps = [n.pitch.step for n in model.measures[0].notes if n.pitch]
        self.assertEqual(steps, ["C", "D", "E", "G"])

    def test_lenient_still_rejects_over_segmentation(self):
        # 5 attaques dans un temps de 4 divisions : non représentable au 16e.
        with self.assertRaises(ParseError):
            parse_solfa("d.r.m.f.s : s", tonic="C", lenient=True)


if __name__ == "__main__":
    unittest.main()
