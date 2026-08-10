"""Sérialisation ScoreModel -> MusicXML (score-partwise).

MusicXML est le format pivot du projet : il est lu directement par
OpenSheetMusicDisplay (affichage portée) et convertible en MIDI (playback).
Écrit à la main avec la stdlib (aucune dépendance) pour rester testable.
Gère une partie unique (`to_musicxml`) ou plusieurs voix SATB (`to_musicxml_multi`).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List

from .model import NoteEl, ScoreModel

_CLEFS = {
    "treble": ("G", 2),
    "bass": ("F", 4),
}

_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE score-partwise PUBLIC '
    '"-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
    '"http://www.musicxml.org/dtds/partwise.dtd">\n'
)


def _sub(parent: ET.Element, tag: str, text=None) -> ET.Element:
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def _append_attributes(measure_el: ET.Element, model: ScoreModel) -> None:
    attrs = _sub(measure_el, "attributes")
    _sub(attrs, "divisions", model.divisions)

    key = _sub(attrs, "key")
    _sub(key, "fifths", model.fifths)

    time = _sub(attrs, "time")
    _sub(time, "beats", model.beats)
    _sub(time, "beat-type", model.beat_type)

    sign, line = _CLEFS.get(model.clef, _CLEFS["treble"])
    clef = _sub(attrs, "clef")
    _sub(clef, "sign", sign)
    _sub(clef, "line", line)


def _append_measure_attribute_changes(measure_el: ET.Element, measure) -> None:
    """Émet <attributes> en début de mesure pour changements de mètre / armure.

    Théorie musicale (portée) : clé/armure/mesure se placent juste après la barre,
    avant les notes — jamais au-dessus de la barre seule.
    """
    need_time = measure.time_signature is not None
    need_key = measure.key_fifths is not None
    if not need_time and not need_key:
        return
    attrs = _sub(measure_el, "attributes")
    if need_key:
        key = _sub(attrs, "key")
        _sub(key, "fifths", measure.key_fifths)
    if need_time:
        beats, beat_type = measure.time_signature
        time = _sub(attrs, "time")
        _sub(time, "beats", beats)
        _sub(time, "beat-type", beat_type)


def _append_tempo(measure_el: ET.Element, tempo: int) -> None:
    direction = _sub(measure_el, "direction", None)
    direction.set("placement", "above")
    dtype = _sub(direction, "direction-type")
    metro = _sub(dtype, "metronome")
    _sub(metro, "beat-unit", "quarter")
    _sub(metro, "per-minute", tempo)
    ET.SubElement(direction, "sound", {"tempo": str(tempo)})


def _append_note(measure_el: ET.Element, note: NoteEl) -> None:
    note_el = _sub(measure_el, "note")

    if note.is_rest:
        _sub(note_el, "rest")
    else:
        pitch = note.pitch
        pitch_el = _sub(note_el, "pitch")
        _sub(pitch_el, "step", pitch.step)
        if pitch.alter:
            _sub(pitch_el, "alter", pitch.alter)
        _sub(pitch_el, "octave", pitch.octave)

    _sub(note_el, "duration", note.duration)

    if note.tie_stop:
        ET.SubElement(note_el, "tie", {"type": "stop"})
    if note.tie_start:
        ET.SubElement(note_el, "tie", {"type": "start"})

    _sub(note_el, "type", note.note_type)
    for _ in range(note.dots):
        _sub(note_el, "dot")

    if note.time_modification is not None:
        actual, normal = note.time_modification
        tm = _sub(note_el, "time-modification")
        _sub(tm, "actual-notes", actual)
        _sub(tm, "normal-notes", normal)

    # Notation ties + articulations/ornements/slur/fermata.
    has_tie = note.tie_start or note.tie_stop
    has_notations = (has_tie or note.articulations or note.ornaments
                     or note.slur or note.fermata)
    if has_notations:
        notations = _sub(note_el, "notations")
        if note.tie_stop:
            ET.SubElement(notations, "tied", {"type": "stop"})
        if note.tie_start:
            ET.SubElement(notations, "tied", {"type": "start"})
        if note.articulations:
            arts_el = _sub(notations, "articulations")
            for a in note.articulations:
                _sub(arts_el, a)
        if note.ornaments:
            orns_el = _sub(notations, "ornaments")
            for o in note.ornaments:
                _sub(orns_el, o)
        if note.slur:
            ET.SubElement(notations, "slur", {"type": note.slur, "number": "1"})
        if note.fermata:
            _sub(notations, "fermata")

    # Paroles (lyric).
    if note.lyric is not None:
        lyric_el = _sub(note_el, "lyric")
        _sub(lyric_el, "syllabic", "single")
        _sub(lyric_el, "text", note.lyric)


def _append_direction(measure_el: ET.Element, d) -> None:
    """Direction (nuance/soufflet/texte/tempo/pédale) → <direction>."""
    from .model import Direction  # import local pour éviter le cycle
    dir_el = _sub(measure_el, "direction")
    if d.placement:
        dir_el.set("placement", d.placement)
    dtype = _sub(dir_el, "direction-type")
    if d.kind == "dynamics":
        dyn = _sub(dtype, "dynamics")
        _sub(dyn, d.value)
    elif d.kind == "wedge":
        attrs = {"type": d.value}
        if d.number is not None:
            attrs["number"] = str(d.number)
        ET.SubElement(dtype, "wedge", attrs)
    elif d.kind == "words":
        _sub(dtype, "words", d.value)
    elif d.kind == "metronome":
        metro = _sub(dtype, "metronome")
        _sub(metro, "beat-unit", "quarter")
        _sub(metro, "per-minute", d.value)
        ET.SubElement(dir_el, "sound", {"tempo": str(d.value)})
    elif d.kind == "pedal":
        attrs = {"type": d.value}
        if d.number is not None:
            attrs["number"] = str(d.number)
        ET.SubElement(dtype, "pedal", attrs)
    elif d.kind == "segno":
        _sub(dtype, "segno")
        ET.SubElement(dir_el, "sound", {"segno": "1"})
    elif d.kind == "coda":
        _sub(dtype, "coda")
        ET.SubElement(dir_el, "sound", {"coda": "1"})
    elif d.kind == "dacapo":
        _sub(dtype, "words", d.value or "D.C.")
        ET.SubElement(dir_el, "sound", {"dacapo": "yes"})
    elif d.kind == "dalsegno":
        _sub(dtype, "words", d.value or "D.S.")
        ET.SubElement(dir_el, "sound", {"dalsegno": "yes"})
    elif d.kind == "fine":
        _sub(dtype, "words", d.value or "Fine")
        ET.SubElement(dir_el, "sound", {"fine": "yes"})
    elif d.kind == "tuplet":
        _sub(dtype, "words", d.value or "3")
    off = getattr(d, "offset_divisions", 0) or 0
    if off:
        _sub(dir_el, "offset", str(off))
    if d.staff is not None:
        _sub(dir_el, "staff", d.staff)


def _append_harmony(measure_el: ET.Element, h) -> None:
    """Harmony (accord) → <harmony>."""
    harm = _sub(measure_el, "harmony")
    root = _sub(harm, "root")
    # Décompose 'F#' → step='F', alter=1 ; 'Bb' → step='B', alter=-1.
    step = h.root[0]
    acc = h.root[1:] if len(h.root) > 1 else ""
    _sub(root, "root-step", step)
    if acc:
        alter = acc.count("#") - acc.count("b")
        _sub(root, "root-alter", alter)
    _sub(harm, "kind", h.kind)
    if h.bass:
        bstep = h.bass[0]
        bacc = h.bass[1:] if len(h.bass) > 1 else ""
        bass_el = _sub(harm, "bass")
        _sub(bass_el, "bass-step", bstep)
        if bacc:
            _sub(bass_el, "bass-alter", bacc.count("#") - bacc.count("b"))


def _append_barline(measure_el: ET.Element, measure) -> None:
    """Repeat et ending → <barline>."""
    if measure.repeat == "forward":
        bl = ET.SubElement(measure_el, "barline", {"location": "left"})
        ET.SubElement(bl, "repeat", {"direction": "forward"})
    if measure.repeat == "backward":
        bl = ET.SubElement(measure_el, "barline", {"location": "right"})
        ET.SubElement(bl, "repeat", {"direction": "backward"})
    if measure.ending:
        loc = "right" if measure.ending.get("type", "start") != "start" else "left"
        bl = ET.SubElement(measure_el, "barline", {"location": loc})
        ET.SubElement(bl, "ending", {
            "number": measure.ending.get("number", "1"),
            "type": measure.ending.get("type", "start"),
        })


def _append_part(root: ET.Element, model: ScoreModel, part_id: str) -> None:
    part = ET.SubElement(root, "part", {"id": part_id})
    for i, measure in enumerate(model.measures):
        attrs = {"number": str(measure.number)}
        if getattr(measure, "implicit", False):
            attrs["implicit"] = "yes"   # mesure de levée (anacrouse)
        measure_el = ET.SubElement(part, "measure", attrs)
        if i == 0:
            _append_attributes(measure_el, model)
            if model.tempo:
                _append_tempo(measure_el, model.tempo)
        else:
            # Théorie : armure / chiffrage en tête de mesure (après la barre).
            _append_measure_attribute_changes(measure_el, measure)
        # Directions avant les notes (offset 0) puis, après, le reste.
        for d in measure.directions:
            _append_direction(measure_el, d)
        for h in measure.harmonies:
            _append_harmony(measure_el, h)
        for note in measure.notes:
            _append_note(measure_el, note)
        _append_barline(measure_el, measure)


def _serialize(root: ET.Element) -> str:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return _HEADER + ET.tostring(root, encoding="unicode") + "\n"


def build_multi(
    models: List[ScoreModel], *, title: str = "", composer: str = ""
) -> ET.Element:
    """Assemble plusieurs voix en un seul score-partwise (une partie par voix).

    ``title``/``composer`` alimentent l'en-tête MusicXML (``<work-title>`` /
    ``<creator type="composer">``) — sinon l'éditeur affiche « Untitled Score »."""
    root = ET.Element("score-partwise", {"version": "4.0"})
    # Ordre DTD : work / identification AVANT part-list.
    if title:
        work = _sub(root, "work")
        _sub(work, "work-title", title)
    if composer:
        ident = _sub(root, "identification")
        creator = _sub(ident, "creator", composer)
        creator.set("type", "composer")
    part_list = _sub(root, "part-list")
    for i, model in enumerate(models):
        pid = f"P{i + 1}"
        score_part = ET.SubElement(part_list, "score-part", {"id": pid})
        _sub(score_part, "part-name", model.part_name)
    for i, model in enumerate(models):
        _append_part(root, model, f"P{i + 1}")
    return root


def to_musicxml_multi(
    models: List[ScoreModel], *, title: str = "", composer: str = ""
) -> str:
    if not models:
        raise ValueError("aucune voix à sérialiser")
    return _serialize(build_multi(models, title=title, composer=composer))


def to_musicxml(model: ScoreModel, *, title: str = "", composer: str = "") -> str:
    return to_musicxml_multi([model], title=title, composer=composer)
