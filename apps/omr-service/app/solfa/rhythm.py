"""Rythme : durées <-> valeurs notées, et disposition en cellules sol-fa.

L'unité de division est **le double-croche (16e) = 1**, quelle que soit la
mesure. `divisions` MusicXML (par noire) vaut donc toujours 4.

  noire = 4, croche = 2, double-croche = 1, blanche = 8, etc.

Un **temps** (pulsation, unité du « : » en sol-fa) contient :
  - 4 divisions en mesure **simple** (temps = noire) ;
  - 6 divisions en mesure **composée** (temps = noire pointée = 3 croches).

Une durée qui ne correspond pas à une seule valeur notée est décomposée en
plusieurs valeurs reliées par des liaisons (ties). Les triolets utilisent
``time_modification`` et une grille ×3 (noire = 12 divisions).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from math import gcd
from typing import List, Optional, Tuple

from .model import NoteEl, Pitch

# Divisions par temps en mesure simple (temps = noire). Permet croches et
# doubles-croches. Garde le nom historique (résolution MusicXML par noire).
DIVISIONS_PER_BEAT = 4

# Divisions par temps en mesure composée (temps = noire pointée = 6 doubles).
COMPOUND_DIVISIONS_PER_BEAT = 6

# (valeur en divisions, type MusicXML, nb de points) — trié par valeur décroissante.
_NOTE_TABLE: List[Tuple[int, str, int]] = [
    (16, "whole", 0),
    (12, "half", 1),
    (8, "half", 0),
    (6, "quarter", 1),
    (4, "quarter", 0),
    (3, "eighth", 1),
    (2, "eighth", 0),
    (1, "16th", 0),
]


class RhythmError(ValueError):
    pass


class MeterError(ValueError):
    """Mesure (signature rythmique) non supportée en v1."""


def split_duration(divisions: int, scale: int = 1) -> List[Tuple[int, str, int]]:
    """Décompose une durée en une liste de (divisions, type, points).

    Décomposition gloutonne des plus grandes valeurs notables vers les plus
    petites. Le résultat somme exactement à `divisions`.

    ``scale`` : 1 (grille binaire, noire=4) ou 3 (triolets, noire=12).
    """
    if divisions <= 0:
        raise RhythmError(f"durée invalide: {divisions}")
    if scale < 1:
        raise RhythmError(f"scale invalide: {scale}")
    out: List[Tuple[int, str, int]] = []
    remaining = divisions
    table = [(v * scale, t, d) for v, t, d in _NOTE_TABLE]
    for value, ntype, dots in table:
        while remaining >= value:
            out.append((value, ntype, dots))
            remaining -= value
    if remaining != 0:
        raise RhythmError(f"durée non représentable: {divisions}")
    return out


# ---------------------------------------------------------------------------
# Mesure (signature rythmique).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Meter:
    """Signature rythmique interprétée en pulsations sol-fa.

    beats          : nb de pulsations par mesure (unités du « : »).
    beat_type      : dénominateur MusicXML (4, 8, ...).
    beat_divisions : divisions par pulsation (4 simple / 6 composé).
    compound       : mesure composée (temps = valeur pointée, subdivision ÷3).
    """
    beats: int
    beat_type: int
    beat_divisions: int
    compound: bool

    @property
    def measure_divisions(self) -> int:
        return self.beats * self.beat_divisions


def classify_meter(numerator: int, denominator: int) -> Meter:
    """`<time>` MusicXML -> Meter.

    - 2/4 3/4 4/4 5/4 : temps = noire (4 divisions).
    - 5/8 6/8 10/8 : grille sol-fa = N croches (2 divisions) — dialecte
      chorale / fihirana (6/8 → ``| 1 : 2 : 3 ! 4 : 5 : 6 |``, pas 2/4).
    - 9/8 12/8 : composé (temps = noire pointée, 6 divisions).
    """
    if denominator == 8 and numerator in (5, 6, 10):
        # Croches : même capacité MusicXML que l'ancien 6/8 composé (12 div),
        # mais 6 pulsations sol-fa pour coller aux recueils malgaches.
        return Meter(numerator, 8, 2, False)
    if denominator == 8 and numerator % 3 == 0 and numerator > 3:
        return Meter(numerator // 3, 8, COMPOUND_DIVISIONS_PER_BEAT, True)
    if denominator == 4 and numerator in (2, 3, 4, 5):
        return Meter(numerator, denominator, DIVISIONS_PER_BEAT, False)
    if denominator == 16 and 1 <= numerator <= 24:
        # Mètre à la double-croche (5/16, 7/16, 12/16…), fréquent dans les fihirana
        # à métrique variable. TOUJOURS simple : chaque pulsation = 1 double-croche
        # (1 division), N pulsations — pas de lecture composée (÷3) qui doublerait
        # la capacité de la mesure.
        return Meter(numerator, 16, 1, False)
    raise MeterError(f"mesure non supportée en v1: {numerator}/{denominator}")


# Mesures candidates pour inférer une signature depuis le contenu OMR.
_INFERENCE_SIGS: Tuple[Tuple[int, int], ...] = (
    (10, 8), (5, 4), (4, 4), (3, 4), (2, 4), (6, 8), (9, 8), (12, 8),
)


def infer_meter_from_content(
    max_divisions: int,
    preferred: Tuple[int, int],
) -> Tuple[int, int]:
    """Choisit une mesure supportée qui couvre ``max_divisions`` (grille interne).

    Utilisé quand Audiveris omet la balise ``<time>`` : on prend la plus petite
    mesure compatible, en préférant ``preferred`` si elle suffit.
    """
    if max_divisions <= 0:
        return preferred
    try:
        pref_cap = classify_meter(*preferred).measure_divisions
    except MeterError:
        preferred = (4, 4)
        pref_cap = classify_meter(4, 4).measure_divisions
    if max_divisions <= pref_cap:
        return preferred
    best: Optional[Tuple[int, int]] = None
    best_slack: Optional[int] = None
    for sig in _INFERENCE_SIGS:
        try:
            cap = classify_meter(*sig).measure_divisions
        except MeterError:
            continue
        if cap >= max_divisions:
            slack = cap - max_divisions
            if best_slack is None or slack < best_slack:
                best, best_slack = sig, slack
    return best if best is not None else preferred


# ---------------------------------------------------------------------------
# Fusion des liaisons + disposition inverse en cellules sol-fa.
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """Événement musical logique d'une mesure (liaisons déjà fusionnées).

    kind : 'note' (attaque) | 'rest' (silence) | 'cont' (tenue venue de la
           mesure précédente, rendue par un « - »).
    tuplet : (actual, normal) si triolet, sinon None — ne doit pas être
             fusionné avec une note binaire voisine.
    """
    kind: str
    duration: int
    pitch: Optional[Pitch] = None
    tuplet: Optional[Tuple[int, int]] = None


def _same_pitch(a: Pitch, b: Pitch) -> bool:
    return (a.step, a.alter, a.octave) == (b.step, b.alter, b.octave)


def scale_meter(meter: Meter, scale: int) -> Meter:
    """Agrandit la grille d'un mètre (scale=3 quand divisions MusicXML = 12)."""
    if scale <= 1:
        return meter
    return Meter(
        beats=meter.beats,
        beat_type=meter.beat_type,
        beat_divisions=meter.beat_divisions * scale,
        compound=meter.compound,
    )


def merge_tied(notes: List[NoteEl]) -> List[Event]:
    """Fusionne les chaînes de liaisons/fragments d'une mesure en événements.

    Les notes qu'un writer a fragmentées (chevauchement de barre, durée non
    notable) portent des liaisons ; on les recolle en un seul événement de
    durée cumulée. Une note liée depuis la mesure précédente (tie_stop sans
    attaque correspondante) devient un événement 'cont'.
    Les notes de triolet (time_modification) restent atomiques.
    """
    events: List[Event] = []
    for n in notes:
        if n.is_rest:
            events.append(Event("rest", n.duration))
            continue
        prev = events[-1] if events else None
        # Ne jamais fusionner un triolet (durée / type figés).
        if n.time_modification is not None or (
            prev is not None and prev.tuplet is not None
        ):
            events.append(
                Event("note", n.duration, n.pitch, tuplet=n.time_modification)
            )
            continue
        if (
            n.tie_stop
            and prev is not None
            and prev.kind in ("note", "cont")
            and prev.pitch is not None
            and n.pitch is not None
            and _same_pitch(prev.pitch, n.pitch)
        ):
            prev.duration += n.duration
        elif n.tie_stop:
            events.append(Event("cont", n.duration, n.pitch))
        else:
            events.append(Event("note", n.duration, n.pitch))
    return events


# Jeton de cellule : ('note', Pitch) | ('hold', None) | ('rest', None).
CellTok = Tuple[str, Optional[Pitch]]


def layout_measure(events: List[Event], meter: Meter) -> List[List[CellTok]]:
    """Dispose les événements d'une mesure sur la grille des temps.

    Renvoie une liste de temps ; chaque temps est une liste de `g` cellules
    égales (g divise `beat_divisions`), choisi pour que toute attaque tombe sur
    une frontière de cellule. La sortie n'utilise que des subdivisions par `.`
    (binaire *ou* ternaire selon le mètre) ; le rendu texte est fait par to_solfa.
    """
    bd = meter.beat_divisions
    total = meter.measure_divisions

    onset_at: dict = {}
    covering: List[Optional[Event]] = [None] * total
    pos = 0
    for ev in events:
        if pos < total:
            onset_at[pos] = ev
        for d in range(pos, min(pos + ev.duration, total)):
            covering[d] = ev
        pos += ev.duration

    beats: List[List[CellTok]] = []
    for b in range(meter.beats):
        start = b * bd
        cuts = {off for off in range(1, bd) if (start + off) in onset_at}
        divisor = reduce(gcd, cuts, bd)
        g = bd // divisor
        cell_div = bd // g

        cells: List[CellTok] = []
        for i in range(g):
            d = start + i * cell_div
            ev = onset_at.get(d) or covering[d]
            is_onset = d in onset_at
            if ev is None or ev.kind == "rest":
                cells.append(("rest", None))
            elif ev.kind == "cont":
                cells.append(("hold", None))
            elif is_onset:
                cells.append(("note", ev.pitch))
            else:
                cells.append(("hold", None))
        beats.append(cells)
    return beats
