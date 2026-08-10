"""Parseur : notation sol-fa tonique -> ScoreModel.

Étapes :
  1. lexer -> cellules à plat (+ nb de temps par mesure)
  2. repli des prolongations '-' dans la note/silence précédent(e)
  3. résolution des hauteurs (mouvable-do -> hauteurs absolues)
  4. empaquetage en mesures avec liaisons (ties) aux barres

Paroles (lyrics) :
  Optionnelles, passées dans une chaîne au même format que la notation :
  séparateurs | (mesures) et : / ! (temps). Chaque temps peut contenir
  un mot/syllabe ou être vide. Le résultat est stocké dans
  Measure.beat_lyrics (liste de str|None par temps).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .keys import fifths_of, normalize_tonic, resolve_pitch
from .lexer import Cell, LexError, notation_has_triplet_beats, tokenize
from .model import Measure, NoteEl, Pitch, ScoreModel
from .rhythm import (
    DIVISIONS_PER_BEAT,
    MeterError,
    RhythmError,
    classify_meter,
    split_duration,
)

_BEAT_SEP_RE = re.compile(r"[:!]")


class ParseError(ValueError):
    """Erreur de parsing exposable à l'utilisateur (message clair)."""


@dataclass
class _Event:
    kind: str                    # 'note' | 'rest'
    duration: int                # divisions cumulées
    pitch: Optional[Pitch] = None
    uncertain: bool = False      # silence « placeholder » : temps présent, non lu
    tuplet: Optional[Tuple[int, int]] = None
    tuplet_type: Optional[str] = None


def _fold_events(
    cells: List[Cell], tonic: str, doh_octave: int, degrade: bool = False
) -> List[_Event]:
    """Résout les hauteurs et absorbe les prolongations '-'."""
    events: List[_Event] = []
    for cell in cells:
        if cell.kind == "hold":
            if not events:
                # Prolongation sans note précédente -> silence.
                events.append(_Event(kind="rest", duration=cell.divisions))
            else:
                # Ne pas fusionner une prolongation dans un triolet (durée figée).
                if events[-1].tuplet is not None:
                    events.append(_Event(kind="rest", duration=cell.divisions))
                else:
                    events[-1].duration += cell.divisions
            continue
        if cell.kind == "rest":
            events.append(_Event(
                kind="rest", duration=cell.divisions, uncertain=cell.uncertain
            ))
            continue
        try:
            # ``cell.tonic`` est posé par le lexer après un ``(Doh=X)`` (mouvable-do,
            # changement de tonalité en cours de partition) ; sinon tonique globale.
            pitch = resolve_pitch(
                cell.core, cell.octave_shift, cell.tonic or tonic, doh_octave
            )
        except KeyError as exc:
            # Dégradation gracieuse OCR : syllabe non résoluble (ex. 'ml' mashé)
            # → silence « placeholder » (temps présent, note non lue), plutôt que
            # d'échouer toute la voix.
            if degrade:
                events.append(_Event(kind="rest", duration=cell.divisions, uncertain=True))
                continue
            raise ParseError(str(exc)) from exc
        events.append(_Event(
            kind="note",
            duration=cell.divisions,
            pitch=pitch,
            tuplet=cell.tuplet,
            tuplet_type=cell.tuplet_type,
        ))
    return events


def _cap_at(caps: List[int], index: int) -> int:
    """Capacité de la mesure d'indice ``index`` : ``caps[index]`` si défini,
    sinon la dernière (mètre stable au-delà de la liste). ``caps`` a 1 élément
    pour un mètre constant, un par barre pour un mètre variable ``(N/M)``."""
    if index < len(caps):
        return caps[index]
    return caps[-1]


def _pack_measures(
    events: List[_Event], caps: List[int], scale: int = 1
) -> List[Measure]:
    """Répartit les événements en mesures, en liant les notes aux barres.

    ``caps`` : capacité par mesure (divisions). Un seul élément = mètre constant
    (toutes les mesures identiques) ; un par barre = mètre variable (jubilate
    10/8 → 6/8 → 4/4), chaque mesure prenant sa propre capacité."""
    measures: List[Measure] = [Measure(number=1)]
    remaining_in_measure = _cap_at(caps, 0)

    for event in events:
        # Triolet : une note atomique (pas de découpe / liaison de barre).
        if event.tuplet is not None:
            if remaining_in_measure == 0:
                measures.append(Measure(number=len(measures) + 1))
                remaining_in_measure = _cap_at(caps, len(measures) - 1)
            if event.duration > remaining_in_measure:
                raise ParseError(
                    f"triolet trop long pour la mesure restante "
                    f"({event.duration} > {remaining_in_measure})"
                )
            is_note = event.kind == "note"
            note = NoteEl(
                is_rest=not is_note,
                duration=event.duration,
                note_type=event.tuplet_type or "eighth",
                dots=0,
                pitch=event.pitch if is_note else None,
                tie_start=False,
                tie_stop=False,
                uncertain=event.uncertain,
                time_modification=event.tuplet,
            )
            measures[-1].notes.append(note)
            remaining_in_measure -= event.duration
            continue

        # Chaque événement peut chevaucher une barre -> on le découpe.
        pieces: List[tuple] = []  # (value, type, dots, measure_index)
        left = event.duration
        while left > 0:
            if remaining_in_measure == 0:
                measures.append(Measure(number=len(measures) + 1))
                remaining_in_measure = _cap_at(caps, len(measures) - 1)
            chunk = min(left, remaining_in_measure)
            try:
                for value, ntype, dots in split_duration(chunk, scale):
                    pieces.append((value, ntype, dots, len(measures) - 1))
            except RhythmError as exc:
                raise ParseError(str(exc)) from exc
            left -= chunk
            remaining_in_measure -= chunk

        total = len(pieces)
        for idx, (value, ntype, dots, mi) in enumerate(pieces):
            is_note = event.kind == "note"
            note = NoteEl(
                is_rest=not is_note,
                duration=value,
                note_type=ntype,
                dots=dots,
                pitch=event.pitch if is_note else None,
                # Une note fragmentée (chevauchement de barre ou durée
                # non notable) est reliée par des liaisons.
                tie_start=is_note and idx < total - 1,
                tie_stop=is_note and idx > 0,
                uncertain=event.uncertain and not is_note,
            )
            measures[mi].notes.append(note)

    # Retire une éventuelle mesure vide en fin.
    if len(measures) > 1 and not measures[-1].notes:
        measures.pop()
    return measures


def _parse_lyrics(
    lyrics_str: str, beats_per_measure: int, n_measures: int
) -> List[List[Optional[str]]]:
    """Parse une chaîne de paroles en [[lyric_par_temps]_par_mesure].

    Même structure que la notation : barres | séparent les mesures,
    ':' et '!' séparent les temps. Retourne exactement n_measures listes
    de beats_per_measure éléments (None si temps vide).
    """
    if not lyrics_str or not lyrics_str.strip():
        return [[None] * beats_per_measure for _ in range(n_measures)]

    raw_measures = lyrics_str.split("|")
    result: List[List[Optional[str]]] = []
    for i in range(n_measures):
        if i < len(raw_measures):
            raw_beats = _BEAT_SEP_RE.split(raw_measures[i])
        else:
            raw_beats = []
        beat_lyrics: List[Optional[str]] = []
        for b in range(beats_per_measure):
            if b < len(raw_beats):
                text = raw_beats[b].strip()
                beat_lyrics.append(text if text else None)
            else:
                beat_lyrics.append(None)
        result.append(beat_lyrics)
    return result


def _enforce_measure_capacity(measures: List[Measure], caps: List[int]) -> None:
    """Validation de composition : chaque mesure vaut EXACTEMENT sa capacité en
    divisions (le total des notes + silences d'une mesure = sa capacité, ni plus
    ni moins). ``caps`` : 1 élément (mètre constant) ou un par mesure (variable).

    Une mesure trop courte (dernière d'une phrase, ou note/silence non reconnu par
    l'OCR) est **complétée par un silence** en fin — jamais laissée incomplète.
    ``_pack_measures`` ne dépasse jamais la capacité, donc rien à tronquer."""
    for mi, meas in enumerate(measures):
        cap = _cap_at(caps, mi)
        if cap <= 0:
            continue
        total = sum(n.duration for n in meas.notes)
        if total < cap:
            for value, ntype, dots in split_duration(cap - total):
                meas.notes.append(
                    NoteEl(
                        is_rest=True, duration=value, note_type=ntype, dots=dots,
                        uncertain=True,  # complément = contenu perdu, à vérifier
                    )
                )


def parse_solfa(
    notation: str,
    tonic: str = "C",
    doh_octave: int = 4,
    clef: str = "treble",
    tempo: Optional[int] = None,
    part_name: str = "Sol-fa",
    lyrics: Optional[str] = None,
    beats: Optional[int] = None,
    beat_type: int = 4,
    lenient: bool = False,
    degrade: bool = False,
    triplets: Optional[List[dict]] = None,
) -> ScoreModel:
    """Point d'entrée : convertit une notation sol-fa en ScoreModel.

    ``lyrics`` : chaîne de paroles optionnelle, même format que la notation
    (barres | et séparateurs : / !). Les paroles sont stockées dans
    Measure.beat_lyrics (par temps, 0-based).

    ``beats``/``beat_type`` : signature rythmique MusicXML explicite. Fournie,
    elle autorise les grilles /8 chorales (5/8, 6/8, 10/8 = N croches) et les
    mesures **composées** 9/8 12/8 (temps = noire pointée). Absente, la
    signature est déduite du nombre de pulsations de la 1re mesure (mètre
    simple à la noire, comportement d'origine).

    ``lenient`` : tolère les subdivisions impaires (par arrondi) au lieu de
    lever une erreur. À activer pour l'entrée OCR/PDF, bruitée ; laisser à False
    pour la saisie manuelle (une subdivision impaire y est plutôt une faute).
    ``lenient`` rejette encore la sur-segmentation non représentable au 16e.

    ``degrade`` : dégradation gracieuse (OCR uniquement) — un temps trop bruité
    ou une syllabe non résoluble devient un **silence** de la durée, au lieu
    d'échouer toute la voix. À réserver au pipeline OCR (jamais la saisie).

    ``triplets`` : marques optionnelles ``{startMeasure, startBeat, spanBeats}``
    (0-based). Un triolet texte est ``drm`` (3 syllabes collées) ; ``spanBeats``
    2 indique 3 notes sur 2 temps (sans ``:`` entre eux dans la notation).
    """
    try:
        key = normalize_tonic(tonic)
    except KeyError as exc:
        raise ParseError(str(exc)) from exc

    if beats is not None:
        try:
            meter: Optional[object] = classify_meter(beats, beat_type)
        except MeterError as exc:
            raise ParseError(str(exc)) from exc
    else:
        meter = None

    triplet_tuples: List[Tuple[int, int, int]] = []
    for t in triplets or []:
        try:
            triplet_tuples.append((
                int(t.get("startMeasure", t.get("start_measure", 0))),
                int(t.get("startBeat", t.get("start_beat", 0))),
                int(t.get("spanBeats", t.get("span_beats", 1))),
            ))
        except (TypeError, ValueError) as exc:
            raise ParseError(f"marque de triolet invalide: {t!r}") from exc

    needs_triplets = bool(triplet_tuples) or notation_has_triplet_beats(notation)
    # Grille ×3 pour que chaque temps soit divisible par 3 (noire = 12).
    division_scale = 3 if needs_triplets else 1

    try:
        cells, pulses, bars = tokenize(
            notation,
            meter,
            lenient,
            degrade,
            division_scale=division_scale,
            triplets=triplet_tuples or None,
        )
    except LexError as exc:
        raise ParseError(str(exc)) from exc

    if pulses == 0:
        raise ParseError("notation vide")

    # Signature d'en-tête MusicXML (≠ nombre de pulsations sol-fa composées).
    # Sans ``beats=`` explicite : NE PAS faire ``pulses/4`` — un ``(9/8)`` à
    # 3 pulsations composées donnerait à tort 3/4. Préférer le 1er marqueur
    # ``(N/M)`` ou le mètre passé au tokenize.
    if beats is not None:
        model_beats, model_beat_type = beats, beat_type
    else:
        opening_sig: Optional[Tuple[int, int]] = None
        for bar in bars:
            if bar.time_sig is not None:
                opening_sig = bar.time_sig
                break
        if opening_sig is not None:
            model_beats, model_beat_type = opening_sig
        elif meter is not None:
            model_beats, model_beat_type = pulses, 4
        else:
            model_beats, model_beat_type = pulses, 4

    # Capacités par mesure. Mètre CONSTANT (aucun marqueur ``(N/M)``) : une seule
    # capacité, comportement d'origine (re-découpage à plat, anacrouse absorbée).
    # Mètre VARIABLE : une capacité par barre, chaque mesure prend la sienne.
    # Un changement de tonalité ``(Doh=X)`` force aussi l'alignement mesure↔barre
    # pour que le changement retombe sur une frontière de mesure.
    has_meter_changes = any(b.time_sig is not None for b in bars)
    has_key_changes = any(b.key_tonic is not None for b in bars)
    if has_meter_changes or has_key_changes:
        caps = [b.cap for b in bars]
    elif beats is not None:
        caps = [meter.measure_divisions * division_scale]  # type: ignore[union-attr]
    else:
        caps = [pulses * DIVISIONS_PER_BEAT * division_scale]

    events = _fold_events(cells, key, doh_octave, degrade)
    measures = _pack_measures(events, caps, scale=division_scale)
    if degrade:
        # Chemin OCR : garantit que chaque mesure vaut exactement 1 mesure pleine
        # (silence de complément si une note a été perdue à la lecture).
        _enforce_measure_capacity(measures, caps)

    # Mètre variable : reporter le changement de signature sur la mesure où il
    # se produit (miroir de ``to_solfa`` qui l'affiche au-dessus de la barre).
    if has_meter_changes:
        for mi, bar in enumerate(bars):
            if bar.time_sig is not None and mi < len(measures):
                measures[mi].time_signature = bar.time_sig

    # Tonalité variable (mouvable-do) : reporter le nouveau doh + son armure sur
    # la mesure où ``(Doh=X)`` apparaît (les hauteurs, elles, ont déjà été
    # résolues cellule par cellule dans _fold_events via cell.tonic).
    if has_key_changes:
        for mi, bar in enumerate(bars):
            if bar.key_tonic is not None and mi < len(measures):
                measures[mi].key_tonic = bar.key_tonic
                measures[mi].key_fifths = fifths_of(bar.key_tonic)

    # Association des paroles aux mesures (par pulsation, pas par note)
    if lyrics:
        beat_lyrics_by_measure = _parse_lyrics(lyrics, pulses, len(measures))
        for mi, measure in enumerate(measures):
            measure.beat_lyrics = beat_lyrics_by_measure[mi]

    return ScoreModel(
        tonic=key,
        fifths=fifths_of(key),
        beats=model_beats,
        beat_type=model_beat_type,
        divisions=DIVISIONS_PER_BEAT * division_scale,
        clef=clef,
        measures=measures,
        tempo=tempo,
        part_name=part_name,
    )
