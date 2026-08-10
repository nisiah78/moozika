"""ScoreModel → texte sol-fa tonique (notation textuelle canonique).

Inverse de `parser.py`. Utilise `rhythm.merge_tied` + `rhythm.layout_measure`
pour disposer les événements musicaux sur la grille des temps, puis encode chaque
temps en séquence de syllabes/tirets/vides selon la grammaire sol-fa.

Stdlib pur — aucune dépendance externe (contrainte CLAUDE.md).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .keys import syllable_of_pitch
from .model import Measure, ScoreModel
from .rhythm import (
    DIVISIONS_PER_BEAT,
    Event,
    Meter,
    MeterError,
    classify_meter,
    layout_measure,
    merge_tied,
    scale_meter,
)

# CellTok = ('note', Pitch) | ('hold', None) | ('rest', None)
_CellTok = Tuple[str, object]


# ---------------------------------------------------------------------------
# Rendu d'une cellule → token texte
# ---------------------------------------------------------------------------

def _with_marks(core: str, shift: int) -> str:
    """Syllabe + marques d'octave Curwen (' = aigu, , = grave)."""
    if shift > 0:
        return core + "'" * shift
    if shift < 0:
        return core + "," * (-shift)
    return core


def _cell_to_token(cell: _CellTok, tonic: str, doh_octave: int) -> str:
    """Convertit une cellule de layout_measure en token sol-fa textuel."""
    kind, pitch = cell
    if kind == "note":
        core, shift = syllable_of_pitch(
            pitch.step, pitch.alter, pitch.octave, tonic, doh_octave
        )
        return _with_marks(core, shift)
    if kind == "hold":
        return "-"
    return "0"  # silence de sous-temps explicite (voir _beat_to_text)


# ---------------------------------------------------------------------------
# Grille de cellules → texte d'un temps
# ---------------------------------------------------------------------------
# Encodage (inverse du lexer), **uniquement des points** pour subdiviser :
#   g=1 → « m »            g=2 → « a.b »        g=3 → « a.b.c »
#   g=4 → « a.b.c.d »      g=6 → « a.b.c.d.e.f »
#
# Pourquoi jamais de ',' : le ',' a un double rôle (quart-de-temps ET octave
# grave) ; collé à une note il est TOUJOURS lu comme marque d'octave (« d,r »
# est illisible). Le '.' seul atteint toutes les subdivisions utiles (il divise
# un temps en 1/2/4 en simple, 1/2/3/6 en composé) et reste round-trippable.
#
# Silences : un temps entièrement muet -> vide ('') ; un silence de SOUS-temps
# après une **note** -> '0' (une cellule vide après '.' serait relue comme
# prolongation ``m.``). Après une **tenue**, le vide suffit (``-.`` = tenue +
# silence de demi-temps).

def _half_token(c0, c1, tonic: str, doh_octave: int):
    """Deux cellules-quarts → token d'un DEMI-temps, en utilisant ``,`` pour le
    quart (comme la vraie notation : ``,t`` = silence-quart + t). Renvoie None si
    non imbriquable proprement — cas où un ``,`` tomberait APRÈS une syllabe (lu
    comme octave grave), ex. [note, note] ou [note, silence]."""
    k0, k1 = c0[0], c1[0]
    if k0 == "note" and k1 == "hold":
        return _cell_to_token(c0, tonic, doh_octave)   # note tenue = demi-temps
    if k0 == "hold" and k1 == "hold":
        return "-"                                     # tenue sur le demi-temps
    if k0 == "rest" and k1 == "rest":
        return ""                                      # demi-temps silencieux
    if k0 == "rest" and k1 == "note":
        return "," + _cell_to_token(c1, tonic, doh_octave)   # silence-quart + note
    if k0 == "rest" and k1 == "hold":
        return ",-"
    return None   # ',' interdit après une note (collision octave) → repli plat


def _beat_to_text(cells: List[_CellTok], tonic: str, doh_octave: int) -> str:
    if all(c[0] == "rest" for c in cells):
        return ""  # temps entièrement silencieux
    # Temps à 4 cellules (double-croches) : on tente la structure IMBRIQUÉE
    # demi(`.`)/quart(`,`) de la vraie notation — ``d.,t`` plutôt que ``d.-.0.t``.
    if len(cells) == 4:
        h1 = _half_token(cells[0], cells[1], tonic, doh_octave)
        h2 = _half_token(cells[2], cells[3], tonic, doh_octave)
        if h1 is not None and h2 is not None:
            if h2 != "":
                return f"{h1}.{h2}"
            # Demi final silencieux : ``-.`` OK (vide après tenue = silence) ;
            # après une note, ``d.`` serait une prolongation → repli plat (`0`).
            half1_has_note = cells[0][0] == "note" or cells[1][0] == "note"
            if not half1_has_note:
                return f"{h1}."

    # Repli : rendu plat par `.` (double-croches / croches).
    toks: List[str] = []
    last_kind: Optional[str] = None
    for cell in cells:
        kind = cell[0]
        if kind == "rest":
            # Vide après note → relu comme prolongation ; il faut `0`.
            # Vide en tête ou après tenue → silence (`-.`, `.m`).
            toks.append("0" if last_kind == "note" else "")
        elif kind == "hold":
            toks.append("-")
            last_kind = "hold"
        else:
            toks.append(_cell_to_token(cell, tonic, doh_octave))
            last_kind = "note"
    return ".".join(toks)


# ---------------------------------------------------------------------------
# Quantisation optionnelle (grille plus grossière -> moins de sursauts OMR)
# ---------------------------------------------------------------------------

def _snap_events(events: List[Event], cap: int, q: int) -> List[Event]:
    """Recale le rythme sur une grille de pas ``q`` (2 = croche).

    Échantillonne l'événement **qui sonne au début de chaque maille** (donc on
    garde la note sur le temps, pas la contretemps) et fusionne les mailles
    consécutives issues d'un même événement. Absorbe ainsi le jitter des durées
    OMR ; la somme reste exactement ``cap`` (multiple de ``q`` pour tous les
    mètres v1)."""
    if q <= 1:
        return events
    covering: List[Optional[Event]] = [None] * cap
    pos = 0
    for ev in events:
        for d in range(pos, min(pos + ev.duration, cap)):
            covering[d] = ev
        pos += ev.duration

    out: List[Event] = []
    last_src: Optional[Event] = None
    for p in range(0, cap, q):
        src = covering[p]
        if src is not None and src is last_src:
            out[-1].duration += q          # même événement -> prolonge la maille
        else:
            kind = src.kind if src is not None else "rest"
            pitch = src.pitch if src is not None else None
            out.append(Event(kind, q, pitch))
            last_src = src
    return out


# ---------------------------------------------------------------------------
# Mesure → texte sol-fa
# ---------------------------------------------------------------------------

def _is_triplet_group(events: List[Event], i: int) -> bool:
    """Trois notes consécutives marqués triolet 3:2."""
    if i + 2 >= len(events):
        return False
    group = events[i : i + 3]
    return all(
        e.kind == "note" and e.tuplet == (3, 2) and e.pitch is not None for e in group
    )


def _join_beat_slots(slots: List[Optional[str]], nbeats: int) -> str:
    """Joint les temps visibles ; ``None`` = temps absorbé par un triolet 2 temps."""
    mid = nbeats // 2
    parts: List[str] = []
    for b, text in enumerate(slots):
        if text is None:
            continue
        if parts:
            parts.append(" ! " if b == mid else " : ")
        parts.append(text)
    return "".join(parts)


def _measure_to_text_with_tuplets(
    events: List[Event], meter: Meter, tonic: str, doh_octave: int
) -> str:
    """Rendu mesure contenant des triolets : ``drm`` collé, span 1 ou 2 temps."""
    bd = meter.beat_divisions
    nbeats = meter.beats
    # str = texte du temps ; None = absorbé (suite d'un triolet 2 temps)
    slots: List[Optional[str]] = [""] * nbeats
    absorbed = [False] * nbeats

    pos = 0
    i = 0
    while i < len(events):
        if _is_triplet_group(events, i):
            group = events[i : i + 3]
            total = sum(e.duration for e in group)
            span = total // bd if bd and total % bd == 0 else 1
            start_beat = pos // bd if bd else 0
            glued = "".join(
                _cell_to_token(("note", e.pitch), tonic, doh_octave) for e in group
            )
            if 0 <= start_beat < nbeats:
                slots[start_beat] = glued
                for b in range(start_beat + 1, min(start_beat + span, nbeats)):
                    absorbed[b] = True
                    slots[b] = None
            pos += total
            i += 3
            continue

        # Segment binaire jusqu'au prochain triolet (ou fin).
        j = i
        while j < len(events) and not _is_triplet_group(events, j):
            j += 1
        segment = events[i:j]
        seg_dur = sum(e.duration for e in segment)
        # Padding pour aligner layout_measure sur la grille complète.
        padded: List[Event] = []
        if pos > 0:
            padded.append(Event("rest", pos))
        padded.extend(segment)
        rem = meter.measure_divisions - pos - seg_dur
        if rem > 0:
            padded.append(Event("rest", rem))
        elif rem < 0:
            # Segment trop long — layout sur ce qui reste sans padding final.
            pass
        laid = layout_measure(padded, meter)
        start_b = pos // bd if bd else 0
        end_b = (pos + seg_dur + bd - 1) // bd if bd else nbeats
        for b in range(max(0, start_b), min(end_b, nbeats)):
            if absorbed[b]:
                continue
            slots[b] = _beat_to_text(laid[b], tonic, doh_octave)
        pos += seg_dur
        i = j

    visible: List[Optional[str]] = [
        None if absorbed[b] else (slots[b] if slots[b] is not None else "")
        for b in range(nbeats)
    ]
    return _join_beat_slots(visible, nbeats)


def _measure_to_text(
    measure: Measure, meter: Meter, tonic: str, doh_octave: int, min_cell: int = 1
) -> str:
    """Une mesure (notes déjà sous forme NoteEl) → ligne sol-fa."""
    events = merge_tied(measure.notes)
    has_tuplet = any(e.tuplet is not None for e in events)
    # Ne pas quantifier grossièrement une mesure à triolets (détruit 3:2).
    if min_cell > 1 and not has_tuplet:
        events = _snap_events(events, meter.measure_divisions, min_cell)
    if has_tuplet:
        return _measure_to_text_with_tuplets(events, meter, tonic, doh_octave)
    beats = layout_measure(events, meter)
    # Séparateur canonique « : » (le « ! » de mi-mesure est accepté en entrée
    # mais to_solfa normalise — comportement historique des tests).
    return " : ".join(_beat_to_text(b, tonic, doh_octave) for b in beats)


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def _measure_directive_prefix(measure: Measure) -> str:
    """Préfixes d'annotation au début d'une mesure (affichage / artefact texte).

    Lossy pour le re-parse du lexer (les chips UI lisent le modèle) — volontaire.
    """
    bits: List[str] = []
    if measure.key_tonic:
        bits.append(f"(Doh={measure.key_tonic})")
    for d in measure.directions or []:
        kind = d.kind
        if kind == "metronome" and d.value:
            bits.append(f"(♩={d.value})")
        elif kind == "dacapo":
            bits.append("[D.C.]")
        elif kind == "dalsegno":
            bits.append("[D.S.]")
        elif kind == "fine":
            bits.append("[Fine]")
        elif kind == "segno":
            bits.append("[Segno]")
        elif kind == "coda":
            bits.append("[Coda]")
        elif kind == "words" and d.value and not (
            measure.key_tonic and d.value.startswith("Doh")
        ):
            bits.append(f"[{d.value}]")
    if not bits:
        return ""
    return " ".join(bits) + " "


def to_solfa(
    model: ScoreModel, include_header: bool = False, min_cell: int = 1
) -> str:
    """ScoreModel → texte sol-fa tonique canonique.

    Paramètres
    ----------
    model           : partition issue de `parse_solfa` ou `from_musicxml`.
    include_header  : si True, préfixe une ligne d'en-tête lisible par un humain
                      (``doh = X  beats/beat_type  = tempo``). L'en-tête n'est
                      **pas** parseable par `parse_solfa` tel quel — il sert à
                      rendre l'artefact texte autonome.
    min_cell        : taille minimale d'une cellule en divisions (1 = double-
                      croche, résolution complète ; 2 = croche). Passer 2 recale
                      le rythme sur la grille de croches — utile pour absorber le
                      jitter des durées OMR et alléger le rendu (moins de cellules
                      par temps). Lossy : les attaques plus courtes qu'une croche
                      fusionnent.

    Sorties
    -------
    Texte sol-fa canonique séparé par `` : `` (temps) et `` | `` (mesures),
    subdivisions par `.` uniquement. Re-parseable via ``parse_solfa(text,
    tonic=model.tonic, beats=model.beats, beat_type=model.beat_type)``
    (à résolution complète, min_cell=1).
    """
    base_meter = classify_meter(model.beats, model.beat_type)
    # Quand le parseur a mis divisions=12 (triolets), la grille texte doit
    # être ×3 — sinon chaque noire (durée 12) est lue comme 3 temps de 4
    # et devient « d : - : - : r » (régression fatale à la sauvegarde).
    scale = (
        model.divisions // DIVISIONS_PER_BEAT
        if DIVISIONS_PER_BEAT and model.divisions >= DIVISIONS_PER_BEAT
        else 1
    )
    if scale < 1:
        scale = 1
    meter = scale_meter(base_meter, scale)
    tonic, doh_octave = model.tonic, model.doh_octave

    # Mètre / tonalité variables : une mesure avec ``time_signature`` /
    # ``key_tonic`` change la signature / le doh à partir d'elle.
    measure_texts: List[str] = []
    cur_meter = meter
    cur_tonic = tonic
    for m in model.measures:
        prefix = ""
        if m.time_signature is not None:
            try:
                cur_meter = scale_meter(
                    classify_meter(m.time_signature[0], m.time_signature[1]),
                    scale,
                )
                prefix += f"({m.time_signature[0]}/{m.time_signature[1]}) "
            except MeterError:
                cur_meter = meter
        if m.key_tonic:
            cur_tonic = m.key_tonic
        prefix += _measure_directive_prefix(m)
        # Évite double (Doh=) si déjà dans prefix via key_tonic + words
        if m.key_tonic and "(Doh=" in prefix:
            # _measure_directive_prefix already added Doh= ; time prefix may precede
            pass
        measure_texts.append(
            prefix + _measure_to_text(m, cur_meter, cur_tonic, doh_octave, min_cell)
        )
    notation = " | ".join(measure_texts)

    if not include_header:
        return notation

    header = f"doh = {tonic}  {model.beats}/{model.beat_type}"
    if model.tempo:
        header += f"  = {model.tempo}"
    return header + "\n" + notation
