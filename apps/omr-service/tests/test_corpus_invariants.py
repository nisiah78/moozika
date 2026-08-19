"""Harnais golden-file (Phase 0) — verrouille la reconstruction du corpus né-numérique.

Chaque fichier a une ligne de vérité (voix, mètre, mesures). Les fichiers VERROUILLÉS
(état correct actuel) sont des assertions DURES ; les CIBLES pas encore atteintes
(TAFAHOANA, MPANJAKAN) sont marquées ``expectedFailure`` — elles basculeront en
« unexpected success » quand la reconstruction générale (Phases 1-3) atterrira,
signalant qu'il faut retirer le décorateur et les verrouiller à leur tour.

Invariants (loi de composition, cf. CLAUDE.md / music-theory.md §7.3) :
  I1 nb de voix              I2 mesures ÉGALES entre voix       I3 nb de mesures
  I4 mètre déclaré           I5 aucun temps invalide            I6 aucune voix muette
Le harnais est un GARDE (capture l'existant), pas le correctif : aucun code prod ici.
"""
import unittest
from pathlib import Path

try:
    from app.pdf.document import pdf_to_models
    _IMPORT_OK = True
except Exception:  # deps optionnelles manquantes (env minimal)
    _IMPORT_OK = False


def _find_docs() -> Path | None:
    """Repère ``docs/`` de façon robuste (local ET conteneur) en remontant depuis
    ce fichier jusqu'à trouver ``docs/11.pdf`` — évite le ``parents[N]`` fragile."""
    for parent in Path(__file__).resolve().parents:
        cand = parent / "docs"
        if (cand / "11.pdf").is_file():
            return cand
    return None


_DOCS = _find_docs()

# (clé, fichier, voix, (beats, beat_type), mesures, verrouillé)
#   verrouillé=True  → état correct actuel, assertions dures (non-régression).
#   verrouillé=False → CIBLE non atteinte, ``expectedFailure`` (repères fournis par
#                      l'utilisateur : TAFAHOANA 8 voix / 79 mes, MPANJAKAN 8 voix / 120 mes).
_CORPUS = [
    ("jesoa",     "jesoa-tsy-mba-mandao.pdf",                        4, (4, 4),  26, True),
    ("deux44",    "244.pdf",                                         4, (3, 4),  16, True),
    ("kristy",    "kristy-velona.pdf",                               4, (4, 4),  24, True),
    ("the_lord",  "the-lord-bless-you-and-keep-you.pdf",             4, (4, 4),  45, True),
    ("onze",      "11.pdf",                                          5, (2, 4),  64, True),
    ("tafahoana", "TAFAHOANA NY HATSARAM-PO SY NY FAHAMARINANA.pdf", 8, (4, 4),  79, False),
    ("mpanjakan", "MPANJAKAN'NY MPANJAKA FestMusClas 2026 ..pdf",    8, (2, 4), 120, False),
]

_CACHE: dict = {}


def _models_for(filename: str):
    if filename not in _CACHE:
        _CACHE[filename] = pdf_to_models((_DOCS / filename).read_bytes())
    return _CACHE[filename]


def _check_all(test, filename, voices, meter, measures):
    models = _models_for(filename)

    # I1 — nombre de voix.
    test.assertEqual(len(models), voices, f"I1 voix: {len(models)} != {voices}")

    counts = [len(m.measures) for m in models]
    # I2 — comptes de mesures égaux entre voix.
    test.assertLessEqual(len(set(counts)), 1, f"I2 mesures inégales entre voix: {counts}")
    # I3 — nombre de mesures.
    test.assertEqual(counts[0], measures, f"I3 mesures: {counts[0]} != {measures}")

    # I4 — mètre déclaré.
    test.assertEqual((models[0].beats, models[0].beat_type), meter, "I4 mètre")

    # I5 — aucun temps invalide : Σ durées == capacité de la mesure (jamais au-delà) ;
    #      une mesure de levée (implicit) peut être plus courte.
    div = models[0].divisions
    for mi, m in enumerate(models):
        for meas in m.measures:
            b = meas.time_signature[0] if meas.time_signature else m.beats
            bt = meas.time_signature[1] if meas.time_signature else m.beat_type
            cap = b * div * 4 // bt
            s = sum(n.duration for n in meas.notes)
            test.assertLessEqual(s, cap, f"I5 OVER voix{mi} mes{meas.number}: {s}>{cap}")
            if not meas.implicit:
                test.assertEqual(s, cap, f"I5 SHORT voix{mi} mes{meas.number}: {s}!={cap}")

    # I6 — aucune voix entièrement muette (une voix au repos partiel reste valide).
    for mi, m in enumerate(models):
        sung = any(not n.is_rest for meas in m.measures for n in meas.notes)
        test.assertTrue(sung, f"I6 voix{mi} entièrement muette")


@unittest.skipUnless(_IMPORT_OK and _DOCS is not None, "docs/ ou dépendances introuvables")
class CorpusInvariants(unittest.TestCase):
    """Méthodes générées dynamiquement (une par fichier), cf. bas de module."""


def _make_test(filename, voices, meter, measures, locked):
    def _method(self):
        _check_all(self, filename, voices, meter, measures)
    return _method if locked else unittest.expectedFailure(_method)


for _key, _file, _v, _meter, _meas, _locked in _CORPUS:
    setattr(
        CorpusInvariants,
        f"test_{_key}",
        _make_test(_file, _v, _meter, _meas, _locked),
    )


if __name__ == "__main__":
    unittest.main()
