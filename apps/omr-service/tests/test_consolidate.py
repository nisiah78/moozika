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

    def test_generic_names_warn_about_estimated_satb(self):
        # "Voice v1".."v4" (placeholder Audiveris) : le nommage S/A/T/B qui suit
        # est une ESTIMATION par tessiture, pas une donnée lue — doit prévenir.
        warnings: list[str] = []
        kept = consolidate_omr_voices(
            _choral_and_piano(), include_piano=False, warnings=warnings
        )
        self.assertEqual([m.part_name for m in kept], ["Soprano", "Alto", "Tenor", "Bass"])
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("[part-name]"))

    def test_ttbb_named_by_real_identity_not_by_tessiture(self):
        # 2 voix de ténor + 2 de basse, RÉELLEMENT nommées (OCR Audiveris,
        # "Tenor2"/"Basse" identiques pour les 2 voix de chaque pupitre — un
        # seul libellé par portée, pas par voix). Ne doit JAMAIS ressortir
        # Soprano/Alto : l'identité lue prime sur le classement par tessiture.
        models = [
            _model("Tenor2", 50, 24),  # la plus aiguë des 2 voix de ténor
            _model("Tenor2", 30, 12),  # la plus grave des 2 voix de ténor
            _model("Basse", 20, 0),
            _model("Basse", 25, -12),
        ]
        kept = consolidate_omr_voices(models, include_piano=False)
        names = [m.part_name for m in kept]
        self.assertEqual(names, ["Tenor I", "Tenor II", "Bass I", "Bass II"])
        self.assertTrue(all(not n.startswith(("Soprano", "Alto")) for n in names))

    def test_mixed_real_and_generic_fills_remaining_by_tessiture(self):
        # Basse identifiée par un vrai nom ; les 3 autres restent génériques
        # ("Voice") -> comblées par tessiture parmi les labels ENCORE libres
        # (Soprano/Alto/Tenor), jamais en réutilisant "Bass".
        models = [
            _model("Voice v1", 50, 24),
            _model("Voice v2", 30, 12),
            _model("Voice v3", 20, 0),
            _model("Basse", 25, -12),
        ]
        kept = consolidate_omr_voices(models, include_piano=False)
        names = [m.part_name for m in kept]
        self.assertEqual(names, ["Soprano", "Alto", "Tenor", "Bass"])

    def test_real_names_do_not_warn(self):
        # Un vrai libellé lu sur la partition (ex. "Tenor 1") n'est PAS une
        # estimation : aucun avertissement, même si le nommage final SATB
        # renomme quand même par tessiture (comportement de _name_voices
        # inchangé, seul l'avertissement dépend de la fiabilité de la source).
        models = [
            _model("Tenor 1", 50, 24),
            _model("Tenor 2", 30, 12),
            _model("Baryton", 20, 0),
            _model("Basse", 25, -12),
        ]
        warnings: list[str] = []
        consolidate_omr_voices(models, include_piano=False, warnings=warnings)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
