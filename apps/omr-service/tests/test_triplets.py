"""Triolets sol-fa : format ``drm`` (3 syllabes collées)."""
import unittest

from app.solfa.lexer import is_triplet_beat, split_triplet_atoms
from app.solfa.parser import ParseError, parse_solfa
from app.solfa.musicxml import to_musicxml
from app.solfa.to_solfa import to_solfa


class TestTripletAtoms(unittest.TestCase):
    def test_drm(self):
        self.assertEqual(split_triplet_atoms("drm"), ["d", "r", "m"])
        self.assertTrue(is_triplet_beat("drm"))

    def test_with_octave(self):
        self.assertEqual(split_triplet_atoms("d,rm"), ["d,", "r", "m"])
        self.assertTrue(is_triplet_beat("d,rm"))

    def test_rejects_dotted(self):
        self.assertEqual(split_triplet_atoms("d.r.m"), [])
        self.assertFalse(is_triplet_beat("d.r.m"))


class TestParseTriplet(unittest.TestCase):
    def test_one_beat_triplet(self):
        model = parse_solfa("d : drm ! m : f", tonic="C", beats=4, beat_type=4)
        self.assertEqual(model.divisions, 12)  # grille ×3
        notes = model.measures[0].notes
        # d (12) + 3×triolet (4) + m (12) + f (12) = 48 = 4×12
        self.assertEqual(sum(n.duration for n in notes), 48)
        triplet_notes = [n for n in notes if n.time_modification is not None]
        self.assertEqual(len(triplet_notes), 3)
        self.assertEqual(
            [n.pitch.syllable for n in triplet_notes],
            ["d", "r", "m"],
        )
        for n in triplet_notes:
            self.assertEqual(n.time_modification, (3, 2))
            self.assertEqual(n.note_type, "eighth")
            self.assertEqual(n.duration, 4)

    def test_two_beat_triplet_with_meta(self):
        model = parse_solfa(
            "drm : f ! s",
            tonic="C",
            beats=4,
            beat_type=4,
            triplets=[{"startMeasure": 0, "startBeat": 0, "spanBeats": 2}],
        )
        self.assertEqual(model.divisions, 12)
        notes = model.measures[0].notes
        self.assertEqual(sum(n.duration for n in notes), 48)
        triplet_notes = [n for n in notes if n.time_modification is not None]
        self.assertEqual(len(triplet_notes), 3)
        for n in triplet_notes:
            self.assertEqual(n.duration, 8)
            self.assertEqual(n.note_type, "quarter")

    def test_musicxml_has_time_modification(self):
        model = parse_solfa("drm : s : l : t", tonic="C", beats=4, beat_type=4)
        xml = to_musicxml(model)
        self.assertIn("<time-modification>", xml)
        self.assertIn("<actual-notes>3</actual-notes>", xml)
        self.assertIn("<normal-notes>2</normal-notes>", xml)
        self.assertIn("<divisions>12</divisions>", xml)

    def test_unknown_glued_still_errors(self):
        with self.assertRaises(ParseError):
            parse_solfa("d : xyz ! m : f", tonic="C", beats=4, beat_type=4)

    def test_to_solfa_preserves_neighbor_measures(self):
        """Régression : divisions=12 ne doit pas transformer d:r:m:f en d:-:-:r."""
        notation = "d : r : m : f | s : drm ! t : d' | d : r : m : f"
        model = parse_solfa(
            notation,
            tonic="C",
            beats=4,
            beat_type=4,
            triplets=[{"startMeasure": 1, "startBeat": 1, "spanBeats": 1}],
        )
        text = to_solfa(model)
        bars = [b.strip() for b in text.split("|")]
        self.assertEqual(len(bars), 3)
        self.assertEqual(bars[0], "d : r : m : f")
        self.assertIn("drm", bars[1])
        self.assertEqual(bars[2], "d : r : m : f")
        # Round-trip modèle
        again = parse_solfa(
            text,
            tonic="C",
            beats=4,
            beat_type=4,
            triplets=[{"startMeasure": 1, "startBeat": 1, "spanBeats": 1}],
        )
        self.assertEqual(
            [n.pitch.syllable for n in again.measures[0].notes if n.pitch],
            ["d", "r", "m", "f"],
        )


if __name__ == "__main__":
    unittest.main()
