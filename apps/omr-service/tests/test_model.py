import unittest

from app.solfa.model import Direction, Harmony, Measure, NoteEl, Pitch, ScoreModel


class TestModelSerialization(unittest.TestCase):
    def test_note_minimal_is_backward_compatible(self):
        """Une note simple ne sérialise que les champs historiques."""
        note = NoteEl(False, 4, "quarter", 0, Pitch("C", 0, 4, "d"))
        d = note.to_dict()
        self.assertEqual(
            set(d),
            {"isRest", "duration", "type", "dots", "pitch", "tieStart", "tieStop"},
        )

    def test_note_expression_fields_emitted_only_if_present(self):
        note = NoteEl(
            False, 4, "quarter", 0, Pitch("C", 0, 4, "d"),
            articulations=["staccato"], slur="start", fermata=True,
            ornaments=["trill"],
        )
        d = note.to_dict()
        self.assertEqual(d["articulations"], ["staccato"])
        self.assertEqual(d["slur"], "start")
        self.assertTrue(d["fermata"])
        self.assertEqual(d["ornaments"], ["trill"])

    def test_measure_directions_and_harmony(self):
        m = Measure(1)
        m.directions.append(Direction(0, "dynamics", "f", placement="below"))
        m.harmonies.append(Harmony(0, "C", "major"))
        m.repeat = "backward"
        d = m.to_dict()
        self.assertEqual(d["directions"][0]["value"], "f")
        self.assertEqual(d["harmonies"][0]["root"], "C")
        self.assertEqual(d["repeat"], "backward")
        # Une mesure vide reste minimale.
        self.assertEqual(set(Measure(2).to_dict()), {"number", "notes"})

    def test_score_exposes_mode_and_doh_octave(self):
        score = ScoreModel(
            tonic="C", fifths=0, beats=4, beat_type=4, divisions=4, clef="treble",
            mode="minor", doh_octave=3,
        )
        d = score.to_dict()
        self.assertEqual(d["mode"], "minor")
        self.assertEqual(d["dohOctave"], 3)


if __name__ == "__main__":
    unittest.main()
