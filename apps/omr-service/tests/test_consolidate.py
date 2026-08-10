import unittest

from app.solfa.model import Measure, NoteEl, Pitch, ScoreModel
from app.staff.consolidate import consolidate_omr_voices


def _model(name: str, notes: int, height: int, clef: str = "treble") -> ScoreModel:
    pitch = Pitch("C", 0, 4 + height // 12, "d")
    meas = [Measure(number=1, notes=[NoteEl(False, 4, "quarter", 0, pitch)] * max(1, notes))]
    return ScoreModel(
        tonic="C", fifths=0, beats=4, beat_type=4, divisions=4,
        clef=clef, measures=meas, part_name=name,
    )


def _choral_and_piano():
    return [
        _model("Voice v1", 50, 24),
        _model("Voice v2", 30, 12),
        _model("Voice v3", 20, 6),
        _model("Piano v1", 40, 0, clef="treble"),   # main droite
        _model("Piano v2", 35, -12, clef="bass"),    # main gauche
        _model("Voice v4", 25, 0),
    ]


class TestConsolidateOmr(unittest.TestCase):
    def test_choral_is_satb_by_tessiture(self):
        kept = consolidate_omr_voices(_choral_and_piano(), include_piano=False)
        self.assertEqual(len(kept), 4)
        self.assertEqual([m.part_name for m in kept],
                         ["Soprano", "Alto", "Tenor", "Bass"])
        self.assertTrue(all(not m.part_name.startswith("Piano") for m in kept))

    def test_piano_recovered_as_two_hands(self):
        kept = consolidate_omr_voices(_choral_and_piano())  # include_piano=True
        names = [m.part_name for m in kept]
        self.assertEqual(names[:4], ["Soprano", "Alto", "Tenor", "Bass"])
        self.assertIn("Piano (main droite)", names)
        self.assertIn("Piano (main gauche)", names)
        self.assertEqual(len(kept), 6)

    def test_piano_hand_picks_clef(self):
        kept = consolidate_omr_voices(_choral_and_piano())
        rh = next(m for m in kept if m.part_name == "Piano (main droite)")
        lh = next(m for m in kept if m.part_name == "Piano (main gauche)")
        self.assertEqual(rh.clef, "treble")
        self.assertEqual(lh.clef, "bass")


if __name__ == "__main__":
    unittest.main()
