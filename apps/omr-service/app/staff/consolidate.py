"""Nettoyage des voix OMR (Audiveris) avant affichage sol-fa."""
from __future__ import annotations

from typing import List

from ..solfa.model import ScoreModel

_PIANO_NAMES = frozenset({"piano", "keyboard", "orgue", "organ"})
_STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _part_base(name: str) -> str:
    return name.split(" v")[0].strip().lower()


def _is_piano(name: str) -> bool:
    return _part_base(name) in _PIANO_NAMES


def _pitch_height(step: str, alter: int, octave: int) -> int:
    return octave * 12 + _STEPS.get(step.upper(), 0) + alter


def _note_count(model: ScoreModel) -> int:
    return sum(
        1
        for meas in model.measures
        for n in meas.notes
        if not n.is_rest and n.pitch
    )


def _median_height(model: ScoreModel) -> float:
    hs = [
        _pitch_height(n.pitch.step, n.pitch.alter, n.pitch.octave)
        for meas in model.measures
        for n in meas.notes
        if n.pitch
    ]
    if not hs:
        return 0.0
    hs.sort()
    return hs[len(hs) // 2]


def _select_piano_lines(piano: List[ScoreModel], *, min_notes: int = 8) -> List[ScoreModel]:
    """Piano → au plus une ligne par main : la voix la plus fournie de chaque
    portée (aiguë = main droite, grave = main gauche). Les accords de piano ont
    déjà été réduits à leur note supérieure (le piano n'est pas scindé)."""
    lines: List[ScoreModel] = []
    for clef, label in (("treble", "Piano (main droite)"), ("bass", "Piano (main gauche)")):
        cands = [m for m in piano if m.clef == clef and _note_count(m) >= min_notes]
        if cands:
            best = max(cands, key=_note_count)
            best.part_name = label
            lines.append(best)
    return lines


def consolidate_omr_voices(
    models: List[ScoreModel], *, max_voices: int = 4, include_piano: bool = True
) -> List[ScoreModel]:
    """Réduit le bruit OMR → lignes choral exploitables (SATB si 4 voix), plus
    éventuellement les lignes de piano (une par main) si ``include_piano``."""
    choral = [m for m in models if not _is_piano(m.part_name)]
    piano = [m for m in models if _is_piano(m.part_name)]
    if not choral:
        choral = list(models)
        piano = []

    min_notes = max(8, max((_note_count(m) for m in choral), default=0) // 20)
    kept_choral = [m for m in choral if _note_count(m) >= min_notes]
    if not kept_choral:
        kept_choral = sorted(choral, key=_note_count, reverse=True)[:max_voices]

    kept_choral.sort(key=_note_count, reverse=True)
    kept = kept_choral[:max_voices]
    kept.sort(key=_median_height, reverse=True)

    satb = ("Soprano", "Alto", "Tenor", "Bass")
    for model, name in zip(kept, satb):
        model.part_name = name

    if include_piano and piano:
        kept.extend(_select_piano_lines(piano))
    return kept
