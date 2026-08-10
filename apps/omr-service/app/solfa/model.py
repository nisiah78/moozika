"""Modèle de domaine : la représentation intermédiaire « facile à interpréter ».

C'est le pivot interne entre le sol-fa lu et n'importe quelle sortie
(MusicXML, affichage portée, playback...). Un `ScoreModel` sérialisé en JSON
est directement consommable par le frontend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Pitch:
    """Hauteur absolue, épelée correctement (step + altération + octave)."""
    step: str          # A..G (lettre anglo-saxonne, exigée par MusicXML)
    alter: int         # -1 bémol, 0 naturel, +1 dièse, ...
    octave: int        # octave scientifique (C4 = do central)
    syllable: str      # syllabe sol-fa d'origine (d, r, m, fe, s', ...)

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "alter": self.alter,
            "octave": self.octave,
            "syllable": self.syllable,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Pitch":
        return cls(
            step=str(d["step"]),
            alter=int(d.get("alter", 0)),
            octave=int(d["octave"]),
            syllable=str(d.get("syllable", "")),
        )


@dataclass
class NoteEl:
    """Une note ou un silence notés (durée exprimée en `divisions`)."""
    is_rest: bool
    duration: int          # en divisions (voir ScoreModel.divisions)
    note_type: str         # 'whole' | 'half' | 'quarter' | 'eighth' | '16th'
    dots: int
    pitch: Optional[Pitch] = None
    tie_start: bool = False
    tie_stop: bool = False
    lyric: Optional[str] = None   # syllabe/mot de parole sur cette note
    # --- détail expressif (optionnel, lu du MusicXML ; ne change pas la hauteur)
    articulations: List[str] = field(default_factory=list)  # staccato, accent...
    ornaments: List[str] = field(default_factory=list)      # trill, mordent, turn
    slur: Optional[str] = None        # 'start' | 'stop' | 'continue' (phrasé)
    fermata: bool = False
    grace: bool = False               # note d'agrément (durée nulle)
    chord_pitches: List[Pitch] = field(default_factory=list)  # notes d'un accord
    # Silence « placeholder » : un TEMPS est bien présent (le mètre le garantit)
    # mais l'OCR n'a pas su lire ce qu'il y avait dessus (note illisible / temps
    # perdu). À distinguer d'un vrai silence voulu → l'interface peut le surligner
    # pour correction manuelle. Toujours False hors chemin OCR bruité.
    uncertain: bool = False
    # Triolet MusicXML : (actual-notes, normal-notes), ex. (3, 2).
    time_modification: Optional[Tuple[int, int]] = None

    def to_dict(self) -> dict:
        d: dict = {
            "isRest": self.is_rest,
            "duration": self.duration,
            "type": self.note_type,
            "dots": self.dots,
            "pitch": self.pitch.to_dict() if self.pitch else None,
            "tieStart": self.tie_start,
            "tieStop": self.tie_stop,
        }
        if self.lyric is not None:
            d["lyric"] = self.lyric
        if self.articulations:
            d["articulations"] = self.articulations
        if self.ornaments:
            d["ornaments"] = self.ornaments
        if self.slur is not None:
            d["slur"] = self.slur
        if self.fermata:
            d["fermata"] = True
        if self.grace:
            d["grace"] = True
        if self.chord_pitches:
            d["chordPitches"] = [p.to_dict() for p in self.chord_pitches]
        if self.uncertain:
            d["uncertain"] = True
        if self.time_modification is not None:
            d["timeModification"] = {
                "actualNotes": self.time_modification[0],
                "normalNotes": self.time_modification[1],
            }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "NoteEl":
        pitch_raw = d.get("pitch")
        chord_raw = d.get("chordPitches") or []
        tm_raw = d.get("timeModification")
        tm = None
        if isinstance(tm_raw, dict):
            tm = (int(tm_raw["actualNotes"]), int(tm_raw["normalNotes"]))
        return cls(
            is_rest=bool(d.get("isRest", False)),
            duration=int(d.get("duration", 0)),
            note_type=str(d.get("type", "quarter")),
            dots=int(d.get("dots", 0)),
            pitch=Pitch.from_dict(pitch_raw) if isinstance(pitch_raw, dict) else None,
            tie_start=bool(d.get("tieStart", False)),
            tie_stop=bool(d.get("tieStop", False)),
            lyric=d.get("lyric"),
            articulations=list(d.get("articulations") or []),
            ornaments=list(d.get("ornaments") or []),
            slur=d.get("slur"),
            fermata=bool(d.get("fermata", False)),
            grace=bool(d.get("grace", False)),
            chord_pitches=[Pitch.from_dict(p) for p in chord_raw if isinstance(p, dict)],
            uncertain=bool(d.get("uncertain", False)),
            time_modification=tm,
        )


@dataclass
class Direction:
    """Indication à durée nulle attachée à une position dans la mesure
    (nuance, soufflet, texte, tempo, pédale)."""
    offset_divisions: int
    kind: str                 # 'dynamics' | 'wedge' | 'words' | 'metronome' | 'pedal'
    value: str                # 'f','p','crescendo','rall.','Andante','75'...
    placement: Optional[str] = None   # 'above' | 'below'
    staff: Optional[int] = None
    number: Optional[int] = None      # appariement des spans (soufflet/pédale)

    def to_dict(self) -> dict:
        d: dict = {
            "offset": self.offset_divisions,
            "kind": self.kind,
            "value": self.value,
        }
        if self.placement is not None:
            d["placement"] = self.placement
        if self.staff is not None:
            d["staff"] = self.staff
        if self.number is not None:
            d["number"] = self.number
        return d


@dataclass
class Harmony:
    """Symbole d'accord (root/kind/bass) attaché à une position dans la mesure."""
    offset_divisions: int
    root: str                 # 'C', 'F#', 'Bb'...
    kind: str                 # 'major','minor','dominant','major-seventh'...
    bass: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {"offset": self.offset_divisions, "root": self.root, "kind": self.kind}
        if self.bass is not None:
            d["bass"] = self.bass
        return d


@dataclass
class Measure:
    number: int
    notes: List[NoteEl] = field(default_factory=list)
    beat_lyrics: List[Optional[str]] = field(default_factory=list)
    """Paroles par temps (index = numéro de temps dans la mesure, 0-based).
    None = pas de texte pour ce temps. Stockées à ce niveau pour le frontend ;
    la note portant la parole est la première note non-silence de chaque temps."""
    directions: List[Direction] = field(default_factory=list)
    harmonies: List[Harmony] = field(default_factory=list)
    implicit: bool = False        # mesure de levée (anacrouse) / incomplète
    repeat: Optional[str] = None  # 'forward' (|:) | 'backward' (:|)
    ending: Optional[dict] = None  # {'number': '1', 'type': 'start'|'stop'} (volta)
    # Changement de signature rythmique À CETTE mesure (beats, beat_type). None =
    # inchangée depuis la mesure précédente. Posé uniquement là où le mètre change
    # (ex. 10/8 → 6/8 à la mesure 8) → l'affichage montre la nouvelle mesure au-
    # dessus de la barre, et le writer MusicXML émet un <time>.
    time_signature: Optional[Tuple[int, int]] = None
    # Changement d'armure À CETTE mesure (fifths MusicXML). None = inchangée.
    # Accompagné en sol-fa d'une indication « Doh = … » (direction words).
    key_fifths: Optional[int] = None
    # Tonique déclarée si key_fifths est posé (mouvable-do). Ex. 'F', 'Bb'.
    key_tonic: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {"number": self.number, "notes": [n.to_dict() for n in self.notes]}
        if self.beat_lyrics:
            d["beatLyrics"] = self.beat_lyrics
        if self.directions:
            d["directions"] = [x.to_dict() for x in self.directions]
        if self.harmonies:
            d["harmonies"] = [x.to_dict() for x in self.harmonies]
        if self.implicit:
            d["implicit"] = True
        if self.repeat is not None:
            d["repeat"] = self.repeat
        if self.ending is not None:
            d["ending"] = self.ending
        if self.time_signature is not None:
            d["timeSignature"] = {
                "beats": self.time_signature[0], "beatType": self.time_signature[1]
            }
        if self.key_fifths is not None:
            d["keyFifths"] = self.key_fifths
        if self.key_tonic is not None:
            d["keyTonic"] = self.key_tonic
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Measure":
        notes_raw = d.get("notes") or []
        dirs_raw = d.get("directions") or []
        harms_raw = d.get("harmonies") or []
        directions: List[Direction] = []
        for x in dirs_raw:
            if not isinstance(x, dict):
                continue
            directions.append(Direction(
                offset_divisions=int(x.get("offset", 0)),
                kind=str(x.get("kind", "")),
                value=str(x.get("value", "")),
                placement=x.get("placement"),
                staff=x.get("staff"),
                number=x.get("number"),
            ))
        harmonies: List[Harmony] = []
        for x in harms_raw:
            if not isinstance(x, dict):
                continue
            harmonies.append(Harmony(
                offset_divisions=int(x.get("offset", 0)),
                root=str(x.get("root", "")),
                kind=str(x.get("kind", "")),
                bass=x.get("bass"),
            ))
        ts_raw = d.get("timeSignature")
        time_signature: Optional[Tuple[int, int]] = None
        if isinstance(ts_raw, dict) and "beats" in ts_raw:
            time_signature = (int(ts_raw["beats"]), int(ts_raw.get("beatType", 4)))
        key_fifths = d.get("keyFifths")
        return cls(
            number=int(d.get("number", 1)),
            notes=[NoteEl.from_dict(n) for n in notes_raw if isinstance(n, dict)],
            beat_lyrics=list(d.get("beatLyrics") or []),
            directions=directions,
            harmonies=harmonies,
            implicit=bool(d.get("implicit", False)),
            repeat=d.get("repeat"),
            ending=d.get("ending"),
            time_signature=time_signature,
            key_fifths=int(key_fifths) if key_fifths is not None else None,
            key_tonic=d.get("keyTonic"),
        )


@dataclass
class ScoreModel:
    """Partition complète prête à être rendue ou exportée."""
    tonic: str             # ex. "C", "F", "Bb" (le doh, mouvable-do)
    fifths: int            # armure MusicXML (nb de dièses>0 / bémols<0)
    beats: int             # numérateur de la mesure (nb de temps par mesure)
    beat_type: int         # dénominateur (4 = temps = noire)
    divisions: int         # divisions par noire (résolution rythmique)
    clef: str              # 'treble' | 'bass'
    measures: List[Measure] = field(default_factory=list)
    tempo: Optional[int] = None   # noires par minute (si connu)
    part_name: str = "Sol-fa"     # nom de la partie (ex. Soprano)
    mode: str = "major"           # 'major' | 'minor' (mineur = la-based)
    doh_octave: int = 4           # octave scientifique du doh (registre de réf.)

    def to_dict(self) -> dict:
        return {
            "tonic": self.tonic,
            "mode": self.mode,
            "fifths": self.fifths,
            "timeSignature": {"beats": self.beats, "beatType": self.beat_type},
            "divisions": self.divisions,
            "dohOctave": self.doh_octave,
            "clef": self.clef,
            "tempo": self.tempo,
            "partName": self.part_name,
            "measures": [m.to_dict() for m in self.measures],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScoreModel":
        ts = d.get("timeSignature") or {}
        measures_raw = d.get("measures") or []
        tempo = d.get("tempo")
        return cls(
            tonic=str(d.get("tonic", "C")),
            fifths=int(d.get("fifths", 0)),
            beats=int(ts.get("beats", d.get("beats", 4))),
            beat_type=int(ts.get("beatType", d.get("beatType", 4))),
            divisions=int(d.get("divisions", 1)),
            clef=str(d.get("clef", "treble")),
            measures=[Measure.from_dict(m) for m in measures_raw if isinstance(m, dict)],
            tempo=int(tempo) if tempo is not None else None,
            part_name=str(d.get("partName", "Sol-fa")),
            mode=str(d.get("mode", "major")),
            doh_octave=int(d.get("dohOctave", 4)),
        )
