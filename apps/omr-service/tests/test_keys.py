import unittest

from app.solfa.keys import (
    CHROMATIC_REVERSE,
    DIATONIC,
    TONIC_MAP,
    fifths_of,
    resolve_pitch,
    syllable_of_pitch,
    tonic_from_fifths,
)


class TestPitchResolution(unittest.TestCase):
    def test_c_major_diatonic(self):
        # En do majeur, doh=C4, soh=G4, te=B4.
        self.assertEqual(_pc(resolve_pitch("d", 0, "C", 4)), ("C", 0, 4))
        self.assertEqual(_pc(resolve_pitch("s", 0, "C", 4)), ("G", 0, 4))
        self.assertEqual(_pc(resolve_pitch("t", 0, "C", 4)), ("B", 0, 4))

    def test_f_major_wraps_octave(self):
        # En fa majeur : doh=F4 ; soh=C5 ; te=E5.
        self.assertEqual(_pc(resolve_pitch("d", 0, "F", 4)), ("F", 0, 4))
        self.assertEqual(_pc(resolve_pitch("s", 0, "F", 4)), ("C", 0, 5))
        self.assertEqual(_pc(resolve_pitch("t", 0, "F", 4)), ("E", 0, 5))

    def test_key_signature_alters(self):
        # fa majeur : fah = Bb (armure 1 bémol).
        self.assertEqual(_pc(resolve_pitch("f", 0, "F", 4)), ("B", -1, 4))
        # sib majeur : doh = Bb.
        self.assertEqual(_pc(resolve_pitch("d", 0, "Bb", 4)), ("B", -1, 4))

    def test_chromatic(self):
        # fe = fa dièse en do majeur.
        self.assertEqual(_pc(resolve_pitch("fe", 0, "C", 4)), ("F", 1, 4))
        # ta = si bémol en do majeur.
        self.assertEqual(_pc(resolve_pitch("ta", 0, "C", 4)), ("B", -1, 4))

    def test_octave_marks(self):
        self.assertEqual(_pc(resolve_pitch("d", 1, "C", 4)), ("C", 0, 5))
        self.assertEqual(_pc(resolve_pitch("d", -1, "C", 4)), ("C", 0, 3))

    def test_fifths(self):
        self.assertEqual(fifths_of("C"), 0)
        self.assertEqual(fifths_of("G"), 1)
        self.assertEqual(fifths_of("F"), -1)
        self.assertEqual(fifths_of("bb"), -2)


class TestSyllableOfPitch(unittest.TestCase):
    """Inverse de resolve_pitch : hauteur absolue -> syllabe mouvable-do."""

    # Syllabes canoniques (diatoniques + chromatiques du dialecte malgache).
    CANONICAL = list(DIATONIC.keys()) + list(CHROMATIC_REVERSE.values())

    def test_roundtrip_all_tonics_syllables_octaves(self):
        """Pour toute tonique × syllabe canonique × registre, resolve puis
        invert redonne exactement la syllabe et le décalage d'octave d'origine."""
        for tonic in TONIC_MAP:
            for core in self.CANONICAL:
                for shift in (-2, -1, 0, 1, 2):
                    for doh_octave in (3, 4, 5):
                        p = resolve_pitch(core, shift, tonic, doh_octave)
                        got = syllable_of_pitch(
                            p.step, p.alter, p.octave, tonic, doh_octave
                        )
                        self.assertEqual(
                            got,
                            (core, shift),
                            f"{tonic} {core}{'+' * max(shift, 0)}"
                            f"{'-' * max(-shift, 0)} @o{doh_octave}",
                        )

    def test_enharmonic_fallback(self):
        # mi♯ = fa (même octave).
        self.assertEqual(syllable_of_pitch("E", 1, 4, "C", 4), ("f", 0))
        # fa♭ = mi (même octave).
        self.assertEqual(syllable_of_pitch("F", -1, 4, "C", 4), ("m", 0))
        # ti♯ = doh une octave au-dessus (B♯4 ≈ C5).
        self.assertEqual(syllable_of_pitch("B", 1, 4, "C", 4), ("d", 1))
        # do♭ = te une octave en dessous (C♭4 ≈ B3).
        self.assertEqual(syllable_of_pitch("C", -1, 4, "C", 4), ("t", -1))

    def test_double_alteration_raises(self):
        # Double dièse hors gamme -> non représentable.
        with self.assertRaises(KeyError):
            syllable_of_pitch("F", 2, 4, "C", 4)

    def test_tonic_from_fifths(self):
        self.assertEqual(tonic_from_fifths(0), "C")
        self.assertEqual(tonic_from_fifths(2), "D")
        self.assertEqual(tonic_from_fifths(-1), "F")
        self.assertEqual(tonic_from_fifths(-2), "Bb")

    def test_la_based_minor(self):
        # La mineur partage l'armure de Do majeur (fifths=0) -> doh = C.
        # La tonique mineure A tombe alors sur le degré 6 (« l »).
        doh = tonic_from_fifths(0)
        self.assertEqual(doh, "C")
        self.assertEqual(syllable_of_pitch("A", 0, 4, doh, 4), ("l", 0))
        # Sensible haussée (sol♯) = « si » (degré 5 haussé).
        self.assertEqual(syllable_of_pitch("G", 1, 4, doh, 4), ("si", 0))


def _pc(pitch):
    return (pitch.step, pitch.alter, pitch.octave)


if __name__ == "__main__":
    unittest.main()
