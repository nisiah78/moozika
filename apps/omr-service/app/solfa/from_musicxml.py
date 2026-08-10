"""Lecture MusicXML (portée / solfège) -> ScoreModel(s) mouvable-do.

Sens inverse de `musicxml.py` : on lit une partition en notation occidentale et
on reconstruit le modèle sol-fa tonique. Stdlib pur (`xml.etree`, `zipfile`) —
aucune dépendance (music21 non requis : la théorie est dans `keys.py`).

Pièges gérés (voir docs/architecture.md §6 et le plan) :
  - `.mxl` (archive ZIP) : on suit META-INF/container.xml jusqu'au rootfile ;
  - le contenu d'une `<measure>` déplace un **curseur** temporel : `<backup>` /
    `<forward>` reculent/avancent, `<chord>` ne l'avance pas (accord), `<grace>`
    non plus ; on regroupe les notes par (portée, voix) en flux monophoniques ;
  - les trous d'une voix sont comblés par des silences ;
  - `divisions` variable -> rescalé sur la grille interne (noire = 4) ;
  - `<time>` / `<key>` réellement changés en cours -> erreur explicite ;
  - `<transpose>` : ignoré pour l'épellation (mouvable-do sur la hauteur écrite),
    warning si transposition chromatique réelle ;
  - accord dans une voix : on garde la note supérieure (+ warning).

Inc 3 : socle notes / rythme / octaves / liaisons / silences / SATB / clefs.
Les couches d'expression (nuances, paroles, harmonie...) sont ajoutées en Inc 4.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import List, Optional, Tuple, Union
import xml.etree.ElementTree as ET

from .keys import syllable_of_pitch, tonic_from_fifths
from .model import Direction, Harmony, Measure, NoteEl, Pitch, ScoreModel
from .rhythm import (
    DIVISIONS_PER_BEAT,
    MeterError,
    RhythmError,
    classify_meter,
    infer_meter_from_content,
    split_duration,
)


class MusicXmlError(ValueError):
    """Erreur exposable lors de la lecture d'un MusicXML."""


# clé MusicXML (sign) -> clef du modèle.
_CLEF_SIGN = {"G": "treble", "F": "bass"}

# Capacités de mesure supportées (en divisions internes, noire = 4), croissantes.
#   8 = 2/4 · 12 = 6/8|3/4 · 16 = 4/4 · 20 = 10/8|5/4 · 24 = 12/8
_SUPPORTED_CAPS = [8, 12, 16, 20, 24]


_PIANO_HINTS = ("piano", "keyboard", "orgue", "organ", "accompaniment", "accomp")


def _looks_like_piano(part_name: str) -> bool:
    base = part_name.split(" v")[0].strip().lower()
    return any(h in base for h in _PIANO_HINTS)


def _capacity_to_meter(cap: int, prefer_eighth: bool) -> Tuple[int, int]:
    """Capacité (divisions) -> (beats, beat_type). À capacité égale, le
    dénominateur déclaré tranche : /8 -> mètre en croches, sinon en noires."""
    if cap <= 8:
        return (2, 4)
    if cap == 12:
        return (6, 8) if prefer_eighth else (3, 4)
    if cap == 16:
        return (4, 4)
    if cap == 20:
        return (10, 8) if prefer_eighth else (5, 4)
    return (12, 8)  # 24


@dataclass
class MusicXmlResult:
    models: List[ScoreModel]
    warnings: List[str] = field(default_factory=list)
    predominant_time: Optional[Tuple[int, int]] = None


# --------------------------------------------------------------------------
# Chargement / normalisation du document.
# --------------------------------------------------------------------------

def _load_bytes(source: Union[str, bytes, Path]) -> bytes:
    if isinstance(source, Path):
        return source.read_bytes()
    if isinstance(source, bytes):
        return source
    if isinstance(source, str):
        if "<" in source:              # contenu XML direct
            return source.encode("utf-8")
        return Path(source).read_bytes()  # chemin de fichier
    raise MusicXmlError(f"source non supportée: {type(source)!r}")


def _unzip_mxl(data: bytes) -> bytes:
    """Archive .mxl -> octets du MusicXML racine (via META-INF/container.xml)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise MusicXmlError("archive .mxl illisible") from exc
    root_path = None
    try:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        for rf in container.iter():
            if rf.tag.rsplit("}", 1)[-1] == "rootfile":
                root_path = rf.get("full-path")
                break
    except KeyError:
        pass
    if root_path is None:  # repli : premier .xml/.musicxml non-META
        for name in zf.namelist():
            if name.lower().endswith((".xml", ".musicxml")) and not name.startswith("META-INF"):
                root_path = name
                break
    if root_path is None:
        raise MusicXmlError("aucun MusicXML trouvé dans l'archive .mxl")
    return zf.read(root_path)


def _strip_ns(root: ET.Element) -> None:
    """Retire les préfixes de namespace (MusicXML via XSD) pour un accès simple."""
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.rsplit("}", 1)[-1]


def _decode_xml_text(data: bytes) -> str:
    """UTF-8/16 + BOM — exports MuseScore/Finale parfois en UTF-16."""
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16-le")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16-be")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    return data.decode("utf-8", errors="replace")


def _find_partwise_start(text: str) -> int:
    """Recherche case-insensitive de la racine score-partwise."""
    m = re.search(r"<\s*score-partwise\b", text, re.IGNORECASE)
    return m.start() if m else -1


def _reject_non_musicxml_bytes(data: bytes) -> None:
    """PDF/image/etc. → erreur explicite (pas « score-partwise introuvable »)."""
    if data.startswith(b"%PDF"):
        from ..pdf.detect import detect_pdf_kind, pdf_kind_message
        kind = detect_pdf_kind(data)
        if kind == "solfa_text":
            raise MusicXmlError(
                "Ce fichier est un PDF sol-fa tonique malgache, pas du MusicXML. "
                "Utilisez l'import « PDF sol-fa » (pas MusicXML)."
            )
        raise MusicXmlError(pdf_kind_message(kind))
    if data.startswith(b"\x89PNG") or data[:3] == b"\xff\xd8\xff":
        raise MusicXmlError(
            "Fichier image détecté : fournir du MusicXML (.xml / .mxl), "
            "pas une image de partition."
        )


def _parse_root(source: Union[str, bytes, Path]) -> ET.Element:
    data = _load_bytes(source)
    if data[:2] == b"PK":
        data = _unzip_mxl(data)
    else:
        _reject_non_musicxml_bytes(data)

    text = _decode_xml_text(data)

    if re.search(r"<\s*score-timewise\b", text, re.IGNORECASE):
        raise MusicXmlError(
            "MusicXML 'score-timewise' non supporté (fournir du score-partwise)"
        )
    idx = _find_partwise_start(text)
    if idx == -1:
        raise MusicXmlError(
            "racine <score-partwise> introuvable — le fichier n'est probablement "
            "pas du MusicXML (partition en portée : exporter en .mxl depuis un "
            "logiciel de notation, ou attendre la reconnaissance OMR Audiveris)."
        )
    try:
        root = ET.fromstring(text[idx:])
    except ET.ParseError as exc:
        raise MusicXmlError(f"XML invalide: {exc}") from exc
    _strip_ns(root)
    return root


# --------------------------------------------------------------------------
# Lecture des hauteurs / attributs.
# --------------------------------------------------------------------------

def _read_pitch_raw(note_el: ET.Element) -> Optional[Tuple[str, int, int]]:
    """Hauteur (step, alter, octave) d'une <note>, ou None si elle n'en a pas
    d'exploitable. Accepte <unpitched> (position d'affichage). Robustesse OMR :
    une note bruitée sans hauteur ne doit pas faire échouer toute la voix."""
    p = note_el.find("pitch")
    if p is None:
        p = note_el.find("unpitched")
        if p is None:
            return None
        step = (p.findtext("display-step") or "C").strip().upper()
        alter = 0
        octave = int(p.findtext("display-octave") or "4")
        return step, alter, octave
    step = (p.findtext("step") or "C").strip().upper()
    try:
        alter = int(float(p.findtext("alter", "0") or "0"))
        octave = int(p.findtext("octave", "4") or "4")
    except ValueError:
        return None
    return step, alter, octave


def _pitch_height(step: str, alter: int, octave: int) -> int:
    """Ordre de hauteur approximatif (pour choisir la note du haut d'un accord)."""
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    return octave * 12 + base.get(step, 0) + alter


def _read_note_expression(note_el: ET.Element):
    """(<lyric>, articulations, ornements, slur, fermata) d'une <note>."""
    lyric = None
    lyric_el = note_el.find("lyric")
    if lyric_el is not None:
        text = lyric_el.findtext("text")
        if text is not None:
            lyric = text.strip() or None

    articulations: List[str] = []
    ornaments: List[str] = []
    slur = None
    fermata = False
    notations = note_el.find("notations")
    if notations is not None:
        arts = notations.find("articulations")
        if arts is not None:
            articulations = [c.tag for c in arts]
        orns = notations.find("ornaments")
        if orns is not None:
            ornaments = [c.tag for c in orns]
        slur_el = notations.find("slur")
        if slur_el is not None:
            slur = slur_el.get("type")
        if notations.find("fermata") is not None:
            fermata = True
    return lyric, articulations, ornaments, slur, fermata


def _acc_to_str(step: str, alter: int) -> str:
    return step + ("#" * alter if alter > 0 else "b" * (-alter))


def _read_directions(dir_el: ET.Element, offset: int) -> List[Direction]:
    """<direction> -> liste de Direction (nuance, soufflet, texte, tempo, pédale)."""
    placement = dir_el.get("placement")
    staff = dir_el.findtext("staff")
    staff_n = int(staff) if staff else None
    out: List[Direction] = []
    for dt in dir_el.findall("direction-type"):
        for child in dt:
            tag = child.tag
            if tag == "dynamics":
                for d in child:
                    out.append(Direction(offset, "dynamics", d.tag, placement, staff_n))
            elif tag == "wedge":
                num = child.get("number")
                out.append(Direction(offset, "wedge", child.get("type", ""),
                                     placement, staff_n,
                                     int(num) if num else None))
            elif tag == "words":
                out.append(Direction(offset, "words", (child.text or "").strip(),
                                     placement, staff_n))
            elif tag == "metronome":
                pm = child.findtext("per-minute")
                if pm:
                    out.append(Direction(offset, "metronome", pm.strip(),
                                         placement, staff_n))
            elif tag == "pedal":
                num = child.get("number")
                out.append(Direction(offset, "pedal", child.get("type", ""),
                                     placement, staff_n, int(num) if num else None))
    return out


def _read_harmony(h_el: ET.Element, offset: int) -> Optional[Harmony]:
    root = h_el.find("root")
    if root is None:
        return None
    step = (root.findtext("root-step") or "C").strip().upper()
    alter = int(float(root.findtext("root-alter", "0")))
    kind = (h_el.findtext("kind") or "").strip() or "major"
    bass_el = h_el.find("bass")
    bass = None
    if bass_el is not None:
        bstep = (bass_el.findtext("bass-step") or "").strip().upper()
        balter = int(float(bass_el.findtext("bass-alter", "0")))
        bass = _acc_to_str(bstep, balter) if bstep else None
    return Harmony(offset, _acc_to_str(step, alter), kind, bass)


def _read_barline(bl_el: ET.Element):
    """(repeat, ending) d'une <barline>."""
    repeat = None
    rep = bl_el.find("repeat")
    if rep is not None:
        repeat = rep.get("direction")   # 'forward' | 'backward'
    ending = None
    end = bl_el.find("ending")
    if end is not None:
        ending = {"number": end.get("number", ""), "type": end.get("type", "")}
    return repeat, ending


@dataclass
class _RawNote:
    onset: int                 # début, en divisions internes (noire = 4)
    duration: int              # durée interne (0 pour une note d'agrément)
    is_rest: bool
    note_type: Optional[str]   # <type> MusicXML si présent
    dots: int
    heights: List[Tuple[str, int, int]]  # hauteurs (step,alter,octave) — accord
    tie_start: bool
    tie_stop: bool
    # couches d'expression (Inc 4)
    lyric: Optional[str] = None
    articulations: List[str] = field(default_factory=list)
    ornaments: List[str] = field(default_factory=list)
    slur: Optional[str] = None
    fermata: bool = False


# --------------------------------------------------------------------------
# Moteur curseur : une <part> -> flux par (portée, voix).
# --------------------------------------------------------------------------

class _Reader:
    def __init__(self, *, quantize_rhythm: bool = False, on_chord: str = "top") -> None:
        self.warnings: List[str] = []
        self.quantize_rhythm = quantize_rhythm
        # 'top' : accord réduit à la note du haut ; 'split' : accord de portée
        # scindé en deux voix (haut/bas) — pour le SATB condensé (T+B, S+A).
        self.on_chord = on_chord
        self._quantized = False
        self._trunc_measures: set[int] = set()
        self._time_sig_counts: Counter = Counter()
        # `_forced_sig` : override EXPLICITE du caller (time_override) — force le
        # mètre sur TOUTES les mesures (l'appelant a lu la signature). `_global_sig`
        # : mètre prédominant inféré du contenu — sert seulement d'INITIALE aux
        # mesures sans <time>, sans écraser un vrai changement de mesure en cours.
        self._forced_sig: Optional[Tuple[int, int]] = None
        self._global_sig: Optional[Tuple[int, int]] = None

    @staticmethod
    def _measure_spans(root: ET.Element) -> Tuple[List[int], bool]:
        """Longueur réelle de chaque mesure (span max du curseur, toutes voix)
        + indice « /8 déclaré quelque part ». Le `<time>` d'Audiveris étant peu
        fiable, c'est le CONTENU qui donne la vraie capacité : une mesure de N
        divisions de vraies notes ne peut pas tenir dans un mètre plus court."""
        by_index: dict = {}
        prefer_eighth = False
        for part in root.findall("part"):
            divisions = 1
            for i, measure_el in enumerate(part.findall("measure")):
                cur = mx = 0
                for child in measure_el:
                    tag = child.tag
                    if tag == "attributes":
                        d = child.findtext("divisions")
                        if d:
                            divisions = int(d)
                        t = child.find("time")
                        if t is not None and t.findtext("beat-type") in ("8", "16"):
                            prefer_eighth = True
                    elif tag == "note":
                        if child.find("grace") is not None:
                            continue
                        it = int(round(int(child.findtext("duration", "0"))
                                       * DIVISIONS_PER_BEAT / divisions))
                        if child.find("chord") is None:
                            cur += it
                        mx = max(mx, cur)
                    elif tag == "backup":
                        cur -= int(round(int(child.findtext("duration", "0"))
                                         * DIVISIONS_PER_BEAT / divisions))
                    elif tag == "forward":
                        cur += int(round(int(child.findtext("duration", "0"))
                                         * DIVISIONS_PER_BEAT / divisions))
                by_index[i] = max(by_index.get(i, 0), mx)
        return list(by_index.values()), prefer_eighth

    def _infer_global_meter(
        self, root: ET.Element, overflow_thresh: float = 0.10
    ) -> Optional[Tuple[int, int]]:
        """Mètre global = plus petite capacité supportée telle que ≤10 % des
        mesures débordent (le `<time>` d'Audiveris n'est PAS fiable ; le contenu
        prime). Le dénominateur déclaré (/8 vs /4) départage à capacité égale."""
        spans, prefer_eighth = self._measure_spans(root)
        spans = [s for s in spans if s > 0]
        if not spans:
            return None
        n = len(spans)
        chosen = _SUPPORTED_CAPS[-1]
        for cap in _SUPPORTED_CAPS:
            if sum(1 for s in spans if s > cap) / n <= overflow_thresh:
                chosen = cap
                break
        return _capacity_to_meter(chosen, prefer_eighth)

    def read(
        self,
        source: Union[str, bytes, Path],
        time_override: Optional[Tuple[int, int]] = None,
    ) -> MusicXmlResult:
        root = _parse_root(source)
        part_names = self._read_part_list(root)
        # Priorité : override explicite (l'utilisateur lit le mètre sur la
        # partition) > inférence par contenu > None (fallback simple plus bas).
        # `_forced_sig` force ce mètre partout ; `_global_sig` (override OU
        # inférence) sert de valeur prédominante rapportée et d'initiale.
        self._forced_sig = time_override
        # Priorité du mètre initial/global : override explicite (l'utilisateur lit
        # le mètre sur la partition) > <time> DÉCLARÉ par Audiveris (fiable : il
        # annonce 3/4 même quand les durées lues sont bruitées) > inférence par
        # contenu (dernier recours). `_forced_sig` force ce mètre partout ;
        # `_global_sig` sert d'initiale aux mesures sans <time>. Le contenu OMR peut
        # gonfler les spans (durées erronées) et faussait le mètre vers 5/4.
        self._global_sig = (
            time_override
            or self._first_declared_meter(root)
            or self._infer_global_meter(root)
        )
        models: List[ScoreModel] = []
        for part_el in root.findall("part"):
            pid = part_el.get("id", "")
            name = part_names.get(pid, pid or "Voix")
            models.extend(self._read_part(part_el, name))
        if not models:
            raise MusicXmlError("aucune partie exploitable dans le MusicXML")
        self._assign_satb_names(models)
        if self.quantize_rhythm and self._trunc_measures:
            nums = sorted(self._trunc_measures)
            shown = ", ".join(str(n) for n in nums[:12])
            if len(nums) > 12:
                shown += f", … ({len(nums)} au total)"
            self._warn(
                "rhythm",
                f"rythme OMR approximatif dans {len(nums)} mesure(s) : {shown}",
            )
        # Mètre prédominant rapporté (= en-tête) : le mètre EFFECTIF le plus
        # fréquent par mesure (report des <time> déclarés d'une mesure à l'autre),
        # et non le global inféré du contenu. Ex. « What Sweeter Music » : ~60
        # mesures 3/4 + quelques 4/4 → 3/4 (l'inférence par contenu produisait 5/4
        # sur des spans OMR gonflés). Repli sur le global s'il n'y a aucune mesure.
        if self._time_sig_counts:
            predominant = self._time_sig_counts.most_common(1)[0][0]
        else:
            predominant = self._global_sig
        return MusicXmlResult(
            models=models, warnings=self.warnings, predominant_time=predominant
        )

    @staticmethod
    def _read_part_list(root: ET.Element) -> dict:
        names = {}
        for sp in root.findall("part-list/score-part"):
            pid = sp.get("id", "")
            names[pid] = (sp.findtext("part-name") or "").strip() or pid
        return names

    @staticmethod
    def _first_explicit_time_sig(part_el: ET.Element) -> Optional[Tuple[int, int]]:
        """Première ``<time>`` explicite (Audiveris la déclare souvent tardivement)."""
        for measure_el in part_el.findall("measure"):
            for child in measure_el:
                if child.tag != "attributes":
                    continue
                time_el = child.find("time")
                if time_el is not None:
                    return (
                        int(time_el.findtext("beats", "4")),
                        int(time_el.findtext("beat-type", "4")),
                    )
        return None

    @staticmethod
    def _first_declared_meter(root: ET.Element) -> Optional[Tuple[int, int]]:
        """Premier <time> DÉCLARÉ et SUPPORTÉ du document (toutes parts). None si
        aucun. Sert de mètre d'ouverture/initiale (le <time> d'Audiveris est fiable
        même quand les durées lues sont bruitées). On ignore un <time> non géré en
        v1 (ex. 7/4) pour retomber proprement sur l'inférence par contenu."""
        for part in root.findall("part"):
            for measure_el in part.findall("measure"):
                for child in measure_el:
                    if child.tag != "attributes":
                        continue
                    time_el = child.find("time")
                    if time_el is None:
                        continue
                    try:
                        sig = (
                            int(time_el.findtext("beats", "4")),
                            int(time_el.findtext("beat-type", "4")),
                        )
                        classify_meter(*sig)
                    except (ValueError, MeterError):
                        continue
                    return sig
        return None

    def _read_part(self, part_el: ET.Element, part_name: str) -> List[ScoreModel]:
        divisions = 1                 # divisions MusicXML par noire (défaut)
        fifths = 0
        mode = "major"
        time_sig: Optional[Tuple[int, int]] = None
        implicit_time_sig = self._first_explicit_time_sig(part_el)
        clef_by_staff: dict = {}
        seen_key = False
        seen_time = False
        # Tonalité d'ouverture (en-tête du modèle) vs clé effective par mesure :
        # un changement d'armure en cours de pièce est reporté sur la mesure.
        initial_fifths = 0
        initial_mode = "major"
        initial_captured = False

        # une entrée par mesure : dict (staff,voice) -> liste de _RawNote
        measures_data: List[dict] = []
        # métadonnées d'expression par mesure (directions, harmonies, reprises)
        measures_meta: List[dict] = []

        def rescale(mx_dur: int) -> int:
            num = mx_dur * DIVISIONS_PER_BEAT
            if num % divisions != 0:
                if not self.quantize_rhythm:
                    raise RhythmError(
                        f"durée non alignée sur la grille (triolet ?) : {mx_dur}/{divisions}"
                    )
                if not self._quantized:
                    self._warn(
                        "rhythm",
                        "durées OMR arrondies à la grille sol-fa (triolets ignorés)",
                    )
                    self._quantized = True
                return round(num / divisions)
            return num // divisions

        for measure_el in part_el.findall("measure"):
            cursor = 0
            last_onset = 0
            per_stream_raw: dict = {}   # (staff,voice) -> list[_RawNote] (cette mesure)
            cur_directions: List[Direction] = []
            cur_harmonies: List[Harmony] = []
            cur_repeat: Optional[str] = None
            cur_ending: Optional[dict] = None
            measure_time_sig = time_sig
            key_change_fifths: Optional[int] = None

            for child in measure_el:
                tag = child.tag
                if tag == "attributes":
                    d = child.findtext("divisions")
                    if d is not None:
                        divisions = int(d)
                    key_el = child.find("key")
                    if key_el is not None:
                        nf = int(key_el.findtext("fifths", "0"))
                        nm = (key_el.findtext("mode") or "major").strip().lower()
                        if not seen_key:
                            fifths, mode, seen_key = nf, nm, True
                        elif nf != fifths:
                            # Changement d'armure en cours de pièce : SUPPORTÉ.
                            # On bascule le doh (mouvable-do) pour les mesures
                            # suivantes et on consigne le changement sur la mesure.
                            fifths, mode = nf, nm
                            key_change_fifths = nf
                        elif nm != mode:
                            # Mode seul (même armure, ex. Do maj ↔ La min) : même
                            # doh en la-based → aucun effet sol-fa, on note le mode.
                            mode = nm
                    time_el = child.find("time")
                    if time_el is not None:
                        nb = int(time_el.findtext("beats", "4"))
                        nbt = int(time_el.findtext("beat-type", "4"))
                        new_sig = (nb, nbt)
                        # Un <time> explicite est RARE et délibéré (Audiveris ne le
                        # déclare qu'aux vrais changements — ex. jubilate : 6/8
                        # mes.37, 4/4 mes.39). On le RESPECTE comme un changement de
                        # mesure en cours de pièce, au lieu de le normaliser vers un
                        # mètre global ou de lever une erreur.
                        if seen_time and new_sig != time_sig:
                            self._warn(
                                "time",
                                f"changement de mesure {time_sig[0]}/{time_sig[1]} "
                                f"→ {nb}/{nbt} (mesure {measure_el.get('number', '?')})",
                            )
                        time_sig, seen_time = new_sig, True
                        measure_time_sig = time_sig
                    for clef_el in child.findall("clef"):
                        st = int(clef_el.get("number", "1"))
                        sign = (clef_el.findtext("sign") or "G").strip().upper()
                        clef_by_staff[st] = _CLEF_SIGN.get(sign, "treble")
                    tr = child.find("transpose")
                    if tr is not None and int(tr.findtext("chromatic", "0")) != 0:
                        self._warn("transpose", "instrument transpositeur : épellation "
                                   "faite sur la hauteur écrite")
                elif tag == "note":
                    self._handle_note(child, cursor, last_onset, per_stream_raw, rescale)
                    if child.find("chord") is None and child.find("grace") is None:
                        dur = child.findtext("duration")
                        if dur is not None:
                            last_onset = cursor
                            cursor += rescale(int(dur))
                elif tag == "backup":
                    cursor -= rescale(int(child.findtext("duration", "0")))
                elif tag == "forward":
                    cursor += rescale(int(child.findtext("duration", "0")))
                elif tag == "direction":
                    off_el = child.find("offset")
                    eff = cursor + rescale(int(off_el.text or "0")) if off_el is not None else cursor
                    cur_directions.extend(_read_directions(child, eff))
                elif tag == "harmony":
                    off_el = child.find("offset")
                    eff = cursor + rescale(int(off_el.text or "0")) if off_el is not None else cursor
                    h = _read_harmony(child, eff)
                    if h is not None:
                        cur_harmonies.append(h)
                elif tag == "barline":
                    rep, end = _read_barline(child)
                    if rep is not None:
                        cur_repeat = rep
                    if end is not None:
                        cur_ending = end

            if self._forced_sig is not None:
                # Override explicite du caller : force le mètre sur TOUTES les
                # mesures (prioritaire sur <time>/inférence). Dans ce mode il n'y
                # a pas de changement de mesure à détecter.
                measure_time_sig = self._forced_sig
            else:
                # Le mètre d'une mesure suit les <time> EXPLICITES (respectés
                # ci-dessus) et est reporté d'une mesure à l'autre (ligne 496). Le
                # global inféré ne sert que d'INITIALE aux mesures SANS <time> ; on
                # ne l'impose plus à TOUTES (sinon un vrai changement de mesure —
                # ex. jubilate 10/8 → 6/8 → 4/4 — serait écrasé).
                if measure_time_sig is None and self._global_sig is not None:
                    measure_time_sig = self._global_sig
                if measure_time_sig is None:
                    # Aucun <time> ni global : dernier recours, inférence contenu.
                    pref = time_sig or implicit_time_sig or (4, 4)
                    max_end = max(
                        (r.onset + r.duration for raws in per_stream_raw.values() for r in raws),
                        default=0,
                    )
                    if self.quantize_rhythm and max_end > 0:
                        measure_time_sig = infer_meter_from_content(max_end, pref)
                    else:
                        measure_time_sig = pref
            if time_sig is None:
                time_sig = measure_time_sig
            if measure_time_sig is not None:
                self._time_sig_counts[measure_time_sig] += 1

            if not initial_captured:
                initial_fifths, initial_mode = fifths, mode
                initial_captured = True

            measures_data.append(per_stream_raw)
            measures_meta.append({
                "directions": cur_directions,
                "harmonies": cur_harmonies,
                "repeat": cur_repeat,
                "ending": cur_ending,
                "time_sig": measure_time_sig,
                "eff_fifths": fifths,          # armure en vigueur pour cette mesure
                "key_change_fifths": key_change_fifths,  # non-None si elle change ici
            })

        # Alignement : chaque voix reçoit une entrée par mesure (vide si muette).
        all_keys = sorted({k for md in measures_data for k in md})
        streams = {k: [md.get(k, []) for md in measures_data] for k in all_keys}

        # SATB condensé : scinder les accords de portée en voix haut/bas
        # (sauf partie de piano/orgue, où un accord n'est pas une paire de voix).
        if self.on_chord == "split" and not _looks_like_piano(part_name):
            streams = self._split_chord_streams(streams)

        if not streams:
            return []

        if time_sig is None:
            time_sig = (4, 4)
        try:
            default_meter = classify_meter(*time_sig)
        except MeterError as exc:
            raise MusicXmlError(str(exc)) from exc

        return self._build_models(
            streams, measures_meta, default_meter,
            initial_fifths, initial_mode, clef_by_staff, part_name,
        )

    def _handle_note(self, note_el, cursor, last_onset, per_stream_raw, rescale) -> None:
        is_chord = note_el.find("chord") is not None
        is_grace = note_el.find("grace") is not None
        is_rest = note_el.find("rest") is not None
        staff = int(note_el.findtext("staff", "1"))
        voice = note_el.findtext("voice", "1")
        key = (staff, voice)

        if is_grace:
            # Pas de durée -> hors grille rythmique. Signalé, non modélisé en v1.
            self._warn("grace", "notes d'agrément ignorées (hors grille rythmique)")
            return

        dur_internal = rescale(int(note_el.findtext("duration", "0")))
        note_type = note_el.findtext("type")
        dots = len(note_el.findall("dot"))

        ties = {t.get("type") for t in note_el.findall("tie")}
        tie_start = "start" in ties
        tie_stop = "stop" in ties

        if is_chord:
            # Rattache la hauteur à la dernière note (même voix). En mode 'top'
            # on ne gardera que le sommet (les autres -> chord_pitches) ; en mode
            # 'split' l'accord deviendra deux voix (cf. _split_chord_streams) —
            # pas d'avertissement « réduit » dans ce cas.
            ph = _read_pitch_raw(note_el)
            raws = per_stream_raw.get(key)
            if ph is not None and raws and not raws[-1].is_rest:
                raws[-1].heights.append(ph)
                if self.on_chord != "split":
                    self._warn("chord", "accord réduit à la note supérieure")
            return

        ph = None if is_rest else _read_pitch_raw(note_el)
        # Note sans hauteur exploitable (bruit OMR) → silence de sa durée, pour
        # préserver la grille rythmique au lieu de faire échouer toute la voix.
        if not is_rest and ph is None:
            self._warn("pitch", "note sans hauteur lisible → silence")
            is_rest = True
        heights = [] if is_rest else [ph]
        lyric, arts, orns, slur, fermata = _read_note_expression(note_el)
        raw = _RawNote(
            onset=cursor, duration=dur_internal, is_rest=is_rest,
            note_type=note_type, dots=dots, heights=heights,
            tie_start=tie_start, tie_stop=tie_stop,
            lyric=lyric, articulations=arts, ornaments=orns,
            slur=slur, fermata=fermata,
        )
        per_stream_raw.setdefault(key, []).append(raw)

    # ----------------------------------------------------------------------

    def _split_chord_streams(self, streams: dict) -> dict:
        """SATB condensé : une voix **seule sur sa portée** et contenant des
        accords est scindée en deux voix — **haut** (note la plus aiguë de chaque
        accord) et **bas** (la plus grave). Une note seule est mise à l'**unisson**
        dans les deux (sinon la voix du bas serait muette pendant les passages
        monophoniques).

        On NE scinde PAS si une autre voix substantielle existe déjà sur la même
        portée (les voix y sont alors déjà séparées : les accords sont des divisi,
        on garde le sommet) — sinon on créerait des doublons quasi-identiques qui
        évinceraient les vraies voix au comptage. Les voix sans accord passent
        inchangées."""
        note_counts = {
            k: sum(1 for meas in ms for r in meas if not r.is_rest)
            for k, ms in streams.items()
        }
        out: dict = {}
        split_any = False
        for (staff, voice), measures in streams.items():
            max_h = max(
                (len(r.heights) for meas in measures for r in meas if not r.is_rest),
                default=0,
            )
            own = note_counts[(staff, voice)]
            has_sibling = any(
                k != (staff, voice) and k[0] == staff and c >= 0.25 * max(own, 1)
                for k, c in note_counts.items()
            )
            if max_h < 2 or has_sibling:
                out[(staff, voice)] = measures
                continue
            split_any = True
            top_meas: List[list] = []
            bot_meas: List[list] = []
            for meas in measures:
                top_row, bot_row = [], []
                for r in meas:
                    if r.is_rest or not r.heights:
                        top_row.append(r)
                        bot_row.append(replace(r))
                        continue
                    ordered = sorted(r.heights, key=lambda h: _pitch_height(*h))
                    top_row.append(replace(r, heights=[ordered[-1]]))
                    bot_row.append(replace(r, heights=[ordered[0]], lyric=None))
                top_meas.append(top_row)
                bot_meas.append(bot_row)
            out[(staff, f"{voice}.1")] = top_meas
            out[(staff, f"{voice}.2")] = bot_meas
        if split_any:
            self._warn("chord", "accords de portée scindés en 2 voix (haut/bas)")
        return out

    def _build_models(self, streams, measures_meta, default_meter, fifths, mode, clef_by_staff, part_name):
        tonic = tonic_from_fifths(fifths)
        multi = len(streams) > 1
        sig_counts: Counter = Counter()
        for i in range(len(next(iter(streams.values())))):
            ts = measures_meta[i].get("time_sig") or (
                default_meter.beats,
                default_meter.beat_type,
            )
            sig_counts[ts] += 1
        pred_sig = sig_counts.most_common(1)[0][0] if sig_counts else (
            default_meter.beats,
            default_meter.beat_type,
        )
        # pred_meter utilisé implicitement via classify_meter(*ts) par mesure

        models: List[ScoreModel] = []
        for (staff, voice) in sorted(streams):
            measures_raw = streams[(staff, voice)]
            clef = clef_by_staff.get(staff, "treble")
            doh_octave = self._pick_doh_octave(measures_raw, tonic, fifths)
            measures = []
            # Mètre courant, initialisé à la signature déclarée (pred_sig, = le
            # mètre d'ouverture affiché). On ne pose `Measure.time_signature` QUE
            # là où le mètre change vraiment vs la mesure précédente (ex. jubilate
            # 10/8 → 6/8 mes.37 → 4/4 mes.39) → l'affichage montre la nouvelle
            # mesure au-dessus de la barre, sans répéter la signature partout.
            prev_ts = pred_sig
            for i, raws in enumerate(measures_raw):
                ts = measures_meta[i].get("time_sig") or pred_sig
                try:
                    meter = classify_meter(*ts)
                except MeterError as exc:
                    raise MusicXmlError(str(exc)) from exc
                # Tonalité effective de la mesure (mouvable-do) : les hauteurs sont
                # épelées contre le doh en vigueur, pas contre le doh d'ouverture.
                eff_fifths = measures_meta[i].get("eff_fifths", fifths)
                eff_tonic = tonic_from_fifths(eff_fifths)
                m = self._raw_measure_to_measure(
                    i + 1, list(raws), measures_meta[i], staff,
                    meter, eff_tonic, eff_fifths, doh_octave,
                )
                if ts != prev_ts:
                    m.time_signature = ts
                    prev_ts = ts
                kc = measures_meta[i].get("key_change_fifths")
                if kc is not None:
                    m.key_fifths = kc
                    m.key_tonic = tonic_from_fifths(kc)
                measures.append(m)
            name = part_name if not multi else f"{part_name} v{voice}"
            models.append(ScoreModel(
                tonic=tonic, fifths=fifths, beats=pred_sig[0],
                beat_type=pred_sig[1],
                divisions=DIVISIONS_PER_BEAT, clef=clef, measures=measures,
                mode=mode, doh_octave=doh_octave, part_name=name,
            ))
        return models

    def _pick_doh_octave(self, measures_raw, tonic, fifths) -> int:
        """Registre du doh MINIMISANT le nombre de marques d'octave (' / ,) sur
        la voix — c'est le but de la notation sol-fa. On essaie les octaves
        autour de la médiane et on garde celle au coût de marques le plus faible.
        (L'ancienne version prenait la médiane, ce qui plaçait souvent le doh
        AU-DESSUS d'une mélodie de soprano → un « , » parasite sur chaque note.)"""
        heights = [h for raws in measures_raw for r in raws for h in r.heights]
        if not heights:
            return 4
        octs = sorted(h[2] for h in heights)
        mid = octs[len(octs) // 2]
        best, best_cost = mid, None
        for doh in range(mid - 2, mid + 3):
            cost = 0
            for step, alter, octave in heights:
                try:
                    _core, shift = syllable_of_pitch(step, alter, octave, tonic, doh)
                except KeyError:
                    continue
                cost += abs(shift)
            if best_cost is None or cost < best_cost:
                best, best_cost = doh, cost
        return best

    def _raw_measure_to_measure(
        self, number, raws, meta, staff, meter, tonic, fifths, doh_octave
    ) -> Measure:
        cap = meter.measure_divisions
        measure = Measure(number=number)
        pos = 0
        for raw in sorted(raws, key=lambda r: r.onset):
            if raw.onset > pos:
                self._fill_rest(measure, raw.onset - pos)
                pos = raw.onset
            self._emit_raw(measure, raw, tonic, fifths, doh_octave)
            pos += raw.duration
        if pos > cap:
            if self.quantize_rhythm:
                self._trunc_measures.add(number)
                while measure.notes and pos > cap:
                    last = measure.notes.pop()
                    pos -= last.duration
            else:
                raise MusicXmlError(
                    f"mesure {number} : durées ({pos}) au-delà de la capacité ({cap})"
                )
        if pos < cap:
            self._fill_rest(measure, cap - pos)
            # mesure incomplète avec des notes -> levée/anacrouse.
            if raws:
                measure.implicit = True
        if self.quantize_rhythm and number == 1:
            while measure.notes and measure.notes[0].is_rest:
                measure.notes.pop(0)
            if measure.notes:
                measure.implicit = True
        # Attacher les métadonnées d'expression :
        # directions filtrées par portée (staff=None = global, s'attache à toutes).
        for d in meta["directions"]:
            if d.staff is None or d.staff == staff:
                measure.directions.append(d)
        measure.harmonies = list(meta["harmonies"])
        if meta["repeat"] is not None:
            measure.repeat = meta["repeat"]
        if meta["ending"] is not None:
            measure.ending = meta["ending"]
        return measure

    def _fill_rest(self, measure: Measure, dur: int) -> None:
        for value, ntype, dots in split_duration(dur):
            measure.notes.append(NoteEl(True, value, ntype, dots))

    def _emit_raw(self, measure, raw, tonic, fifths, doh_octave) -> None:
        if raw.is_rest:
            if raw.note_type:
                measure.notes.append(NoteEl(True, raw.duration, raw.note_type, raw.dots))
            else:
                self._fill_rest(measure, raw.duration)
            return

        # note du haut = sommet de l'accord.
        top = max(raw.heights, key=lambda h: _pitch_height(*h))
        step, alter, octave = top
        try:
            core, shift = syllable_of_pitch(step, alter, octave, tonic, doh_octave)
        except KeyError as exc:
            raise MusicXmlError(str(exc)) from exc
        pitch = Pitch(step=step, alter=alter, octave=octave, syllable=_with_marks(core, shift))
        chord_pitches = [
            Pitch(s, a, o, "") for (s, a, o) in raw.heights if (s, a, o) != top
        ]
        ntype = raw.note_type or split_duration(raw.duration)[0][1]
        note = NoteEl(
            False, raw.duration, ntype, raw.dots, pitch,
            tie_start=raw.tie_start, tie_stop=raw.tie_stop,
            chord_pitches=chord_pitches,
            lyric=raw.lyric,
            articulations=raw.articulations,
            ornaments=raw.ornaments,
            slur=raw.slur,
            fermata=raw.fermata,
        )
        measure.notes.append(note)

    def _assign_satb_names(self, models: List[ScoreModel]) -> None:
        """Si exactement 4 voix aux noms génériques, nomme S/A/T/B par tessiture."""
        generic = all(m.part_name.split(" v")[0] in ("", "Voix", "P1", "P2", "P3", "P4")
                      or m.part_name.startswith("Voix") for m in models)
        if len(models) == 4 and generic:
            order = sorted(models, key=self._median_height, reverse=True)
            for m, nm in zip(order, ("Soprano", "Alto", "Tenor", "Bass")):
                m.part_name = nm

    @staticmethod
    def _median_height(model: ScoreModel) -> float:
        hs = [
            _pitch_height(n.pitch.step, n.pitch.alter, n.pitch.octave)
            for meas in model.measures for n in meas.notes if n.pitch
        ]
        hs.sort()
        return hs[len(hs) // 2] if hs else 0.0

    def _warn(self, tag: str, msg: str) -> None:
        entry = f"[{tag}] {msg}"
        if entry not in self.warnings:
            self.warnings.append(entry)


def _with_marks(core: str, shift: int) -> str:
    """Syllabe + marques d'octave Curwen ('=aigu, ,=grave)."""
    if shift > 0:
        return core + "'" * shift
    if shift < 0:
        return core + "," * (-shift)
    return core


# --------------------------------------------------------------------------
# API publique.
# --------------------------------------------------------------------------

def read_musicxml(
    source: Union[str, bytes, Path],
    *,
    quantize_rhythm: bool = False,
    time_override: Optional[Tuple[int, int]] = None,
    on_chord: str = "top",
) -> MusicXmlResult:
    """Lit un MusicXML -> {models, warnings}.

    ``time_override`` : force la signature (beats, beat_type), ex. (10, 8),
    court-circuitant l'inférence — utile quand l'utilisateur lit le mètre sur la
    partition et que l'OMR se trompe.
    ``on_chord`` : 'top' (défaut, accord réduit au sommet) ou 'split' (accord de
    portée scindé en deux voix haut/bas — pour le SATB condensé T+B, S+A)."""
    return _Reader(
        quantize_rhythm=quantize_rhythm, on_chord=on_chord
    ).read(source, time_override)


def from_musicxml(
    source: Union[str, bytes, Path],
    *,
    time_override: Optional[Tuple[int, int]] = None,
    on_chord: str = "top",
) -> List[ScoreModel]:
    """Lit un MusicXML -> liste de ScoreModel (une par voix)."""
    return read_musicxml(
        source, time_override=time_override, on_chord=on_chord
    ).models


# ---------------------------------------------------------------------------
# CLI : python -m app.solfa.from_musicxml <fichier>
# ---------------------------------------------------------------------------

def _cli_main(argv=None) -> int:
    import argparse
    import json
    import sys as _sys

    p = argparse.ArgumentParser(
        description="Convertit un MusicXML/.mxl en sol-fa tonique."
    )
    p.add_argument("file", help="fichier MusicXML ou .mxl")
    p.add_argument("--out", dest="outfile",
                   help="fichier de sortie (défaut : stdout)")
    p.add_argument("--json", action="store_true",
                   help="sort les modèles en JSON (prioritaire)")
    p.add_argument("--header", action="store_true",
                   help="préfixe chaque voix d'un en-tête (doh=, mesure, tempo)")
    p.add_argument("--eighth", action="store_true",
                   help="cale le rythme sur la grille de croches (absorbe le "
                        "jitter OMR ; défaut : double-croche, fidèle)")
    p.add_argument("--time", dest="time",
                   help="force la signature (ex. 10/8), court-circuite "
                        "l'inférence quand l'OMR se trompe de mètre")
    p.add_argument("--split-chords", action="store_true",
                   help="scinde les accords de portée en 2 voix (SATB condensé "
                        "T+B / S+A) au lieu de ne garder que la note du haut")
    args = p.parse_args(argv)
    min_cell = 2 if args.eighth else 1
    on_chord = "split" if args.split_chords else "top"

    time_override = None
    if args.time:
        try:
            nb, nbt = args.time.split("/")
            time_override = (int(nb), int(nbt))
        except ValueError:
            print(f"Erreur : --time invalide : {args.time!r} (attendu N/D)",
                  file=_sys.stderr)
            return 1

    try:
        result = read_musicxml(
            Path(args.file), time_override=time_override, on_chord=on_chord
        )
    except MusicXmlError as exc:
        print(f"Erreur : {exc}", file=_sys.stderr)
        return 1

    if not result.models:
        print("Aucune voix exploitable.", file=_sys.stderr)
        return 1
    for w in result.warnings:
        print(f"[avertissement] {w}", file=_sys.stderr)

    # Import local pour éviter le cycle à l'import du module.
    from .to_solfa import to_solfa  # noqa: PLC0415

    if args.json:
        output = json.dumps(
            [
                {
                    "name": m.part_name,
                    "notation": to_solfa(m, min_cell=min_cell),
                    "model": m.to_dict(),
                }
                for m in result.models
            ],
            indent=2,
            ensure_ascii=False,
        )
    else:
        lines = []
        for m in result.models:
            lines.append(f"# {m.part_name}")
            lines.append(to_solfa(m, include_header=args.header, min_cell=min_cell))
            lines.append("")
        output = "\n".join(lines).rstrip("\n")

    if args.outfile:
        Path(args.outfile).write_text(output, encoding="utf-8")
        print(f"Écrit : {args.outfile}", file=_sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
