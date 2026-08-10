"""Inc 6 : round-trip bout en bout via la fixture jesoa-tsy-mba-mandao.pdf.

Chaîne testée :
    pdf_to_score(FIXTURE)["musicxml"]
        → from_musicxml
        → to_solfa
        → parse_solfa (re-parse)

Comparé aux incipits attendus de test_pdf.py (soprano m1 : « .m : m.s : t : t.l »).
Aucune nouvelle fixture binaire n'est introduite.
"""
import re
import unittest
from pathlib import Path

from app.pdf.document import pdf_to_score
from app.solfa.from_musicxml import from_musicxml
from app.solfa.parser import parse_solfa
from app.solfa.to_solfa import to_solfa

FIXTURE = Path(__file__).parent / "fixtures" / "jesoa-tsy-mba-mandao.pdf"

# Annotations de tête émises par to_solfa (tempo/tonalité/navigation) : ``(♩=75)``,
# ``(Doh=F)``, ``[D.C.]``… Métadonnées à durée nulle, lues du modèle par l'UI et
# retirées ici pour comparer le CONTENU de notes. (Le mètre ``(N/M)`` reste testé
# à part car il change la grille rythmique.)
_DIRECTIVE_PREFIX_RE = re.compile(r"^((?:\([^)]*\)|\[[^\]]*\])\s*)+")


def _strip_directives(measure_text: str) -> str:
    return _DIRECTIVE_PREFIX_RE.sub("", measure_text).strip()


@unittest.skipUnless(FIXTURE.is_file(), "fixture jesoa-tsy-mba-mandao.pdf absente")
class TestJesoaRoundTrip(unittest.TestCase):
    """PDF → MusicXML → ScoreModel(s) → texte sol-fa.

    On vérifie :
      - que les 4 voix SATB sont récupérées ;
      - que chacune comporte 26 mesures ;
      - que la tonique est D (ré majeur) ;
      - que l'incipit soprano m1 correspond au texte extrait du PDF ;
      - que le texte produit est re-parseable sans erreur.
    """

    @classmethod
    def setUpClass(cls):
        result = pdf_to_score(FIXTURE)
        cls.models = from_musicxml(result["musicxml"])

    def test_four_voices_recovered(self):
        self.assertEqual(len(self.models), 4)

    def test_part_names_satb(self):
        names = [m.part_name for m in self.models]
        self.assertEqual(names, ["Soprano", "Alto", "Tenor", "Bass"])

    def test_twenty_six_measures_per_voice(self):
        for m in self.models:
            self.assertEqual(
                len(m.measures), 26,
                f"{m.part_name}: attendu 26 mesures, obtenu {len(m.measures)}",
            )

    def test_tonic_is_d(self):
        for m in self.models:
            self.assertEqual(m.tonic, "D",
                             f"{m.part_name}: tonique {m.tonic!r} ≠ D")

    def test_soprano_incipit_matches_pdf(self):
        """Mesure 1 soprano = « .m : m.s : t : t.l » (idem texte PDF extrait)."""
        soprano = next(m for m in self.models if m.part_name == "Soprano")
        text = to_solfa(soprano)
        # Le tempo initial peut être préfixé « (♩=…) » sur la 1re mesure : on
        # compare le contenu de notes, sans les annotations à durée nulle.
        m1 = _strip_directives(text.split(" | ")[0])
        self.assertEqual(
            m1,
            ".m : m.s : t : t.l",
            f"incipit soprano obtenu : {m1!r}",
        )

    def test_solfa_text_reparses_correctly(self):
        """Chaque voix produit un texte re-parseable donnant le même nb de mesures."""
        for model in self.models:
            text = to_solfa(model)
            reparsed = parse_solfa(
                text,
                tonic=model.tonic,
                doh_octave=model.doh_octave,
                beats=model.beats,
                beat_type=model.beat_type,
            )
            self.assertEqual(
                len(reparsed.measures),
                len(model.measures),
                f"{model.part_name}: {len(reparsed.measures)} mesures après "
                f"re-parse, attendu {len(model.measures)}",
            )

    def test_notes_preserved_first_measure(self):
        """Les hauteurs absolues (step + octave) sont préservées après round-trip."""
        soprano = next(m for m in self.models if m.part_name == "Soprano")
        text = to_solfa(soprano)
        reparsed = parse_solfa(
            text,
            tonic=soprano.tonic,
            doh_octave=soprano.doh_octave,
            beats=soprano.beats,
            beat_type=soprano.beat_type,
        )
        orig_notes = [
            (n.pitch.step, n.pitch.octave)
            for n in soprano.measures[0].notes
            if n.pitch
        ]
        reparsed_notes = [
            (n.pitch.step, n.pitch.octave)
            for n in reparsed.measures[0].notes
            if n.pitch
        ]
        self.assertEqual(
            orig_notes, reparsed_notes,
            f"notes m1 soprano : orig={orig_notes} reparsed={reparsed_notes}",
        )


if __name__ == "__main__":
    unittest.main()
