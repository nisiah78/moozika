import unittest

from app.solfa.model import NoteEl, Pitch
from app.solfa.parser import parse_solfa
from app.solfa.rhythm import (
    Event,
    Meter,
    MeterError,
    RhythmError,
    classify_meter,
    infer_meter_from_content,
    layout_measure,
    merge_tied,
    split_duration,
)


def _p(step, octave=4):
    return Pitch(step=step, alter=0, octave=octave, syllable=step.lower())


def _kinds(beats):
    """[[('note',pitch)|('hold',None)|('rest',None)]] -> [[kind]]."""
    return [[tok[0] for tok in beat] for beat in beats]


class TestSplitDuration(unittest.TestCase):
    def test_simple_values(self):
        self.assertEqual(split_duration(4), [(4, "quarter", 0)])
        self.assertEqual(split_duration(2), [(2, "eighth", 0)])
        self.assertEqual(split_duration(1), [(1, "16th", 0)])
        self.assertEqual(split_duration(8), [(8, "half", 0)])
        self.assertEqual(split_duration(16), [(16, "whole", 0)])

    def test_dotted(self):
        self.assertEqual(split_duration(6), [(6, "quarter", 1)])
        self.assertEqual(split_duration(3), [(3, "eighth", 1)])
        self.assertEqual(split_duration(12), [(12, "half", 1)])

    def test_tied_decomposition(self):
        # 5 = noire + double-croche (liées en amont).
        self.assertEqual(split_duration(5), [(4, "quarter", 0), (1, "16th", 0)])
        # tout se somme à la durée demandée.
        for d in range(1, 40):
            self.assertEqual(sum(v for v, _, _ in split_duration(d)), d)

    def test_invalid(self):
        with self.assertRaises(RhythmError):
            split_duration(0)


class TestClassifyMeter(unittest.TestCase):
    def test_simple(self):
        m = classify_meter(4, 4)
        self.assertEqual((m.beats, m.beat_divisions, m.compound), (4, 4, False))
        self.assertEqual(m.measure_divisions, 16)
        self.assertEqual(classify_meter(3, 4).beats, 3)
        self.assertEqual(classify_meter(2, 4).measure_divisions, 8)

    def test_compound(self):
        # 9/8 / 12/8 restent composés (noire pointée).
        m = classify_meter(9, 8)
        self.assertEqual((m.beats, m.beat_divisions, m.compound), (3, 6, True))
        self.assertEqual(m.measure_divisions, 18)
        self.assertEqual(classify_meter(12, 8).beats, 4)

    def test_six_eight_chorale_grid(self):
        # 6/8 fihirana = 6 croches (comme 10/8), pas 2 noires pointées.
        m = classify_meter(6, 8)
        self.assertEqual((m.beats, m.beat_divisions, m.compound), (6, 2, False))
        self.assertEqual(m.measure_divisions, 12)

    def test_unsupported(self):
        for num, den in [(2, 2), (7, 8), (3, 8)]:
            with self.assertRaises(MeterError):
                classify_meter(num, den)

    def test_10_8_and_5_4(self):
        m10 = classify_meter(10, 8)
        self.assertEqual(m10.measure_divisions, 20)
        self.assertEqual(m10.beats, 10)
        self.assertEqual(classify_meter(5, 4).measure_divisions, 20)


class TestInferMeter(unittest.TestCase):
    def test_prefers_preferred_when_fits(self):
        self.assertEqual(infer_meter_from_content(12, (6, 8)), (6, 8))

    def test_upgrades_when_content_exceeds_preferred(self):
        self.assertEqual(infer_meter_from_content(24, (6, 8)), (12, 8))

    def test_prefers_10_8_for_twenty_divisions(self):
        self.assertEqual(infer_meter_from_content(20, (6, 8)), (10, 8))


class TestMergeTied(unittest.TestCase):
    def test_coalesces_tie_chain(self):
        # noire liée à une double-croche (5 divisions) -> un seul événement.
        notes = [
            NoteEl(False, 4, "quarter", 0, _p("C"), tie_start=True),
            NoteEl(False, 1, "16th", 0, _p("C"), tie_stop=True),
        ]
        events = merge_tied(notes)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].kind, events[0].duration), ("note", 5))

    def test_continuation_from_previous_measure(self):
        # tie_stop en tête sans attaque -> 'cont' (rendu par un '-').
        notes = [NoteEl(False, 4, "quarter", 0, _p("C"), tie_stop=True)]
        events = merge_tied(notes)
        self.assertEqual(events[0].kind, "cont")

    def test_rest_and_note(self):
        notes = [NoteEl(True, 4, "quarter", 0), NoteEl(False, 4, "quarter", 0, _p("E"))]
        events = merge_tied(notes)
        self.assertEqual([e.kind for e in events], ["rest", "note"])


class TestLayoutMeasure(unittest.TestCase):
    def test_simple_four_quarters(self):
        m = classify_meter(4, 4)
        events = [Event("note", 4, _p(s)) for s in "CDEF"]
        beats = layout_measure(events, m)
        self.assertEqual(_kinds(beats), [["note"]] * 4)

    def test_half_note_is_note_then_hold(self):
        m = classify_meter(4, 4)
        events = [Event("note", 8, _p("G")), Event("note", 8, _p("A"))]
        beats = layout_measure(events, m)
        self.assertEqual(
            _kinds(beats), [["note"], ["hold"], ["note"], ["hold"]]
        )

    def test_binary_subdivision(self):
        m = classify_meter(2, 4)
        events = [Event("note", 2, _p("C")), Event("note", 2, _p("D")),
                  Event("note", 4, _p("E"))]
        beats = layout_measure(events, m)
        self.assertEqual(_kinds(beats), [["note", "note"], ["note"]])

    def test_ternary_subdivision_compound(self):
        m = classify_meter(9, 8)
        # temps 1 = trois croches ; temps 2 = noire pointée ; temps 3 = noire pointée.
        events = [Event("note", 2, _p(s)) for s in "CDE"]
        events.append(Event("note", 6, _p("F")))
        events.append(Event("note", 6, _p("G")))
        beats = layout_measure(events, m)
        self.assertEqual(_kinds(beats), [["note", "note", "note"], ["note"], ["note"]])

    def test_six_eight_six_eighth_cells(self):
        m = classify_meter(6, 8)
        events = [Event("note", 2, _p(s)) for s in "CDEFGA"]
        beats = layout_measure(events, m)
        self.assertEqual(len(beats), 6)
        self.assertEqual(_kinds(beats), [["note"]] * 6)

    def test_leading_rest_then_note(self):
        m = classify_meter(2, 4)
        events = [Event("rest", 2), Event("note", 2, _p("E")),
                  Event("note", 4, _p("F"))]
        beats = layout_measure(events, m)
        self.assertEqual(_kinds(beats), [["rest", "note"], ["note"]])


class TestSixEightChorale(unittest.TestCase):
    def test_six_eight_six_eighths(self):
        # 6/8 : six croches — ``d : r : m ! f : s : l``.
        model = parse_solfa("d : r : m ! f : s : l", tonic="C", beats=6, beat_type=8)
        self.assertEqual((model.beats, model.beat_type), (6, 8))
        notes = model.measures[0].notes
        self.assertEqual(len(notes), 6)
        self.assertTrue(all(n.note_type == "eighth" for n in notes))
        self.assertEqual([n.pitch.step for n in notes], list("CDEFGA"))

    def test_six_eight_quarter_pairs(self):
        # ``d : -`` absorbe une croche de tenue → noire ; ×3 dans la mesure.
        model = parse_solfa("d : - : m : - : s : -", tonic="C", beats=6, beat_type=8)
        notes = model.measures[0].notes
        self.assertEqual([n.note_type for n in notes], ["quarter", "quarter", "quarter"])
        self.assertEqual(sum(n.duration for n in notes), 12)


if __name__ == "__main__":
    unittest.main()
