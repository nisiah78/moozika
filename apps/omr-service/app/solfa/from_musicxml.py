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
    scale_meter,
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
# Programmes General MIDI (1-based) de clavier : pianos 1-8, orgues 17-24.
_KEYBOARD_MIDI = frozenset(range(1, 9)) | frozenset(range(17, 25))
# Fraction minimale de notes en accord pour qu'une voix soit considérée comme un
# SATB CONDENSÉ (T+B écrits en accords) et scindée haut/bas. En deçà, ce sont des
# divisi ponctuels d'une voix mono → gardés en note+chord_pitches, pas scindés
# (évite de dupliquer toute la voix à l'unisson). Cf. _split_chord_streams.
_CHORD_SPLIT_MIN_FRAC = 0.4


def _looks_like_piano(part_name: str) -> bool:
    base = part_name.split(" v")[0].strip().lower()
    return any(h in base for h in _PIANO_HINTS)


def _is_tenor_name(part_name: str) -> bool:
    """Vrai si le nom de la voix (LU sur la partition via l'OCR Audiveris, pas
    une estimation) désigne explicitement un ténor. Sert la convention chorale
    déterministe : ténor en clé de Sol standard = sonne 1 octave sous l'écrit."""
    base = part_name.split(" v")[0].strip().lower()
    return "tenor" in base or "ténor" in base


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
    time_modification: Optional[Tuple[int, int]] = None  # (actual, normal) triolet
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
        self._global_fifths: Optional[int] = None
        # Grille interne : ×1 (noire=4) en binaire pur ; ×3 (noire=12) dès qu'il y
        # a des triolets, pour que leurs durées (croche de triolet = 1/3 de temps)
        # tombent JUSTE sur la grille au lieu d'être arrondies en double-croches.
        self._grid_scale: int = 1

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

    def _content_meter_sequence(
        self, root: ET.Element
    ) -> Optional[List[Tuple[int, int]]]:
        """Mètre (beats, beat_type) de CHAQUE mesure, dérivé du CONTENU (span),
        puis LISSÉ. À n'utiliser que quand l'ouverture n'est PAS déclarée : dans ce
        cas Audiveris n'a pas lu les signatures (il ne déclare `<time>` qu'aux rares
        changements qu'il parvient à OCR — ex. jubilate m37/m39), alors que le
        CONTENU reflète le vrai mètre de chaque mesure (10/8, 6/8, 4/4…).

        Le lissage médian (fenêtre 3) remplace une mesure isolée au span aberrant
        (bruit OMR, mesure de transition) par le mètre de ses voisines → on ne crée
        pas de faux changement d'une seule mesure (cf. test_single_overflow_outlier).
        Un vrai changement, SOUTENU sur plusieurs mesures, survit au lissage."""
        spans, prefer_eighth = self._measure_spans(root)
        if not spans or not any(s > 0 for s in spans):
            return None

        def snap(s: int) -> int:
            # capacité supportée la plus proche (égalité → la plus petite).
            return min(_SUPPORTED_CAPS, key=lambda c: (abs(c - s), c))

        caps = [snap(s) if s > 0 else 0 for s in spans]
        n = len(caps)
        # Lissage par HYSTÉRÉSIS : un changement de mètre n'est accepté que s'il est
        # SOUTENU (≥2 mesures consécutives de même span). Une mesure isolée au span
        # aberrant (mesure de transition, pickup, bruit OMR) garde donc le mètre
        # courant — le lissage médian échouait ici (à une frontière A→X→B, la
        # médiane de 3 valeurs distinctes = l'aberrante). L'ouverture = 1er mètre
        # soutenu (ignore une 1re mesure anormale).
        cur = 0
        for i in range(n - 1):
            if caps[i] > 0 and caps[i] == caps[i + 1]:
                cur = caps[i]
                break
        if cur == 0:
            cur = next((c for c in caps if c > 0), 16)
        smoothed: List[int] = []
        for i in range(n):
            c = caps[i]
            if c > 0 and c != cur:
                nxt = caps[i + 1] if i + 1 < n else 0
                nxt2 = caps[i + 2] if i + 2 < n else 0
                if c == nxt:            # changement soutenu → accepté
                    cur = c
                elif (
                    nxt > 0
                    and nxt == nxt2
                    and spans[i] < nxt
                ):
                    # 1re mesure du nouveau mètre TRONQUÉE (OMR a raté des
                    # tenues) : le span isolé n'égale ni l'ancien ni le nouveau,
                    # mais les 2 mesures suivantes soutiennent le nouveau.
                    # Ex. jubilate m61 : span 8 entre 6/8 et 10/8 → 10/8.
                    cur = nxt
            smoothed.append(cur)
        return [_capacity_to_meter(c, prefer_eighth) for c in smoothed]

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
        declared_opening = self._first_declared_meter(root)
        self._global_sig = (
            time_override
            or declared_opening
            or self._infer_global_meter(root)
        )
        # Mètre VARIABLE dérivé du contenu : uniquement quand ni override ni
        # ouverture déclarée. Audiveris ne déclare alors `<time>` qu'aux rares
        # changements qu'il OCR (jubilate : m37/m39), ratant l'ouverture 10/8 et
        # les changements m8, m30… — que le CONTENU, lui, porte. On dérive donc le
        # mètre de chaque mesure du contenu (lissé). Si l'ouverture EST déclarée
        # (What Sweeter Music : <time> fiable en m1), on garde le déclaré tel quel.
        self._content_meters: Optional[List[Tuple[int, int]]] = None
        if time_override is None and declared_opening is None:
            self._content_meters = self._content_meter_sequence(root)
        # Armure de la pièce : 1re <key><fifths> déclarée (tous parts confondus).
        # Sert d'initiale aux parts dont la 1re mesure ne redéclare pas l'armure.
        self._global_fifths = self._first_declared_fifths(root)
        # Grille ×3 ssi un triolet a une durée qui ne tombe PAS sur la grille
        # binaire (sinon un <time-modification> parasite d'Audiveris sur une note
        # « ronde » basculerait tout le rythme en ×3 pour rien, cassant p.ex. la
        # dérivation de mètre variable).
        self._grid_scale = 3 if self._needs_triplet_grid(root) else 1
        midi_programs = self._read_midi_programs(root)
        models: List[ScoreModel] = []
        for part_el in root.findall("part"):
            pid = part_el.get("id", "")
            name = part_names.get(pid, pid or "Voix")
            models.extend(self._read_part(part_el, name, midi_programs.get(pid)))
        if not models:
            raise MusicXmlError("aucune partie exploitable dans le MusicXML")
        self._reconcile_variable_meter(models)
        self._unify_doh_octave(models)
        for mo in models:
            self._detriplet_false_tuplets(mo)
            self._extract_triplets(mo)
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
        # Métrique variable dérivée du contenu : le `<time>` déclaré par l'OMR est
        # faux (4/4, 6/8…). On rapporte alors le mètre EFFECTIF le plus fréquent
        # par mesure (ex. 5/16) pour que l'en-tête colle à ce qui est affiché.
        eff_counter: Counter = Counter()
        for mo in models:
            cur = (mo.beats, mo.beat_type)
            for meas in mo.measures:
                if meas.time_signature:
                    cur = meas.time_signature
                eff_counter[cur] += 1
        if any(sig[1] == 16 for sig in eff_counter):
            predominant = eff_counter.most_common(1)[0][0]
        # Détection défensive d'une signature variable à la double-croche :
        # plusieurs <time> DÉCLARÉS distincts dont au moins un en /16 (ou plus
        # fin). Complète le garde-fou « implicit » du _read_part (qui couvre le cas
        # où l'OMR déclare un mètre faux SANS /16 mais marque tout en levée). Les
        # changements de mètre normaux (ex. 10/8 → 6/8 → 4/4, aucun /16) restent
        # acceptés sans avertissement.
        distinct_sigs = list(self._time_sig_counts)
        if len(distinct_sigs) >= 2 and any(ts[1] >= 16 for ts in distinct_sigs):
            self._warn(
                "meter",
                "signature variable en doubles-croches (…/16 changeant) — "
                "transcription rythmique à vérifier.",
            )
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
    def _read_midi_programs(root: ET.Element) -> dict:
        """id de part → programme MIDI (General MIDI, 1-based) si déclaré.
        Signal de rôle : 1-8 = pianos, 17-24 = orgues → accompagnement."""
        out: dict = {}
        for sp in root.findall("part-list/score-part"):
            pid = sp.get("id", "")
            mp = sp.findtext("midi-instrument/midi-program")
            try:
                out[pid] = int(mp) if mp else None
            except ValueError:
                out[pid] = None
        return out

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
        """<time> déclaré et SUPPORTÉ dans la **1re mesure** (l'OUVERTURE) — None
        sinon. Sert de mètre initial : un <time> d'ouverture est fiable même quand
        les durées lues sont bruitées (cf. TestContentMeterInference).

        ⚠️ On ne prend QUE la 1re mesure, PAS le 1er <time> trouvé n'importe où.
        Audiveris ne déclare souvent le <time> qu'aux CHANGEMENTS : sur une pièce
        qui OUVRE en 10/8 (non déclaré) puis passe en 6/8 à la mesure 37, le 1er
        <time> rencontré est ce 6/8 tardif — le prendre comme mètre d'ouverture
        écraserait le vrai 10/8 initial (bug jubilate). Si l'ouverture ne déclare
        rien, on retombe sur l'inférence par contenu (`_infer_global_meter`), qui
        détecte correctement le 10/8. Un <time> non géré en v1 (ex. 7/4) est ignoré."""
        for part in root.findall("part"):
            first = part.find("measure")
            if first is None:
                continue
            for child in first:
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

    @staticmethod
    def _needs_triplet_grid(root: ET.Element) -> bool:
        """Vrai ssi un <time-modification> porte une note dont la durée NE tombe
        PAS sur la grille binaire interne (noire = DIVISIONS_PER_BEAT). C'est la
        seule situation où la grille ×3 (noire=12) est nécessaire : un triolet
        parasite sur une note « ronde » (qui tient déjà en binaire) est ignoré."""
        for part in root.findall("part"):
            div: Optional[int] = None
            for measure_el in part.findall("measure"):
                for child in measure_el:
                    if child.tag == "attributes":
                        d = child.findtext("divisions")
                        if d:
                            try:
                                div = int(d)
                            except ValueError:
                                div = None
                    elif child.tag == "note" and child.find("time-modification") is not None:
                        if div and div > 0:
                            try:
                                dur = int(child.findtext("duration", "0"))
                            except ValueError:
                                continue
                            if dur > 0 and (dur * DIVISIONS_PER_BEAT) % div != 0:
                                return True
        return False

    @staticmethod
    def _first_declared_fifths(root: ET.Element) -> Optional[int]:
        """Première <key><fifths> déclarée du document (toutes parts). None si
        aucune. = armure de la pièce, héritée par les parts sans <key> initial."""
        el = root.find(".//key/fifths")
        if el is not None and el.text is not None:
            try:
                return int(el.text)
            except ValueError:
                return None
        return None

    def _read_part(
        self, part_el: ET.Element, part_name: str, midi_program: Optional[int] = None
    ) -> List[ScoreModel]:
        divisions = 1                 # divisions MusicXML par noire (défaut)
        # Armure INITIALE = celle de la pièce (1re armure déclarée, tous parts
        # confondus). Sans ça, une part dont la 1re mesure n'a pas de <key>
        # (fréquent en sortie Audiveris) démarrerait en Do (fifths=0) et
        # mé-épellerait toutes ses notes (ex. Solb lu « sa » au lieu de « d »).
        fifths = self._global_fifths or 0
        mode = "major"
        staff_count = 1               # nb de portées de la part (2 = clavier)
        time_sig: Optional[Tuple[int, int]] = None
        implicit_time_sig = self._first_explicit_time_sig(part_el)
        clef_by_staff: dict = {}
        clef_octave_change_by_staff: dict = {}
        seen_key = False
        seen_time = False
        # Tonalité d'ouverture (en-tête du modèle) vs clé effective par mesure :
        # un changement d'armure en cours de pièce est reporté sur la mesure.
        initial_fifths = fifths
        initial_mode = "major"
        initial_captured = False

        # une entrée par mesure : dict (staff,voice) -> liste de _RawNote
        measures_data: List[dict] = []
        # métadonnées d'expression par mesure (directions, harmonies, reprises)
        measures_meta: List[dict] = []

        def rescale(mx_dur: int) -> int:
            num = mx_dur * DIVISIONS_PER_BEAT * self._grid_scale
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
                    sc = child.findtext("staves")
                    if sc:
                        try:
                            staff_count = max(staff_count, int(sc))
                        except ValueError:
                            pass
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
                        oc = clef_el.findtext("clef-octave-change")
                        if oc:
                            try:
                                clef_octave_change_by_staff[st] = int(oc)
                            except ValueError:
                                pass
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

            # Longueur réellement remplie (divisions internes) = max sur toutes
            # les voix. Sert à compléter une levée DÉCLARÉE (implicit) jusqu'à la
            # longueur d'anacrouse commune, sans la gonfler à la mesure pleine.
            filled_divisions = max(
                (r.onset + r.duration
                 for raws in per_stream_raw.values() for r in raws),
                default=0,
            )
            measures_data.append(per_stream_raw)
            measures_meta.append({
                "directions": cur_directions,
                "harmonies": cur_harmonies,
                "repeat": cur_repeat,
                "ending": cur_ending,
                "time_sig": measure_time_sig,
                "eff_fifths": fifths,          # armure en vigueur pour cette mesure
                "key_change_fifths": key_change_fifths,  # non-None si elle change ici
                # Levée déclarée par la source (Audiveris pose implicit="yes" sur
                # l'anacrouse) — à honorer plutôt qu'à deviner/gonfler.
                "implicit": measure_el.get("implicit") == "yes",
                "filled_divisions": filled_divisions,
            })

        # Mètre variable dérivé du contenu (ouverture non déclarée) : on écrase le
        # time_sig de CHAQUE mesure par le mètre lissé dérivé de son contenu, pour
        # récupérer les changements qu'Audiveris n'a pas déclarés (jubilate m8,
        # m30…). Fait AVANT le contrôle under-fill : les time_sig collant désormais
        # au contenu, l'heuristique « mètre non fiable » (/16) ne se déclenche plus
        # à tort. Les mesures d'une part plus courte gardent le reste inchangé.
        if self._content_meters:
            for i, md in enumerate(measures_meta):
                if i < len(self._content_meters):
                    md["time_sig"] = self._content_meters[i]

        # ── Garde-fou « levée » (implicit) + détection de mètre non fiable ──────
        # Une VRAIE anacrouse est rare (1–2 mesures) : une mesure sous-remplie
        # isolée = levée. Mais si la MAJORITÉ des mesures sont sous-remplies
        # (contenu < capacité du mètre déclaré), ce ne sont pas des levées : c'est
        # le symptôme d'un mètre mal reconnu — le contenu ne rentre jamais dans la
        # mesure (typiquement une signature variable à la double-croche,
        # 5/16 · 7/16 · 12/16…, lue 6/8 ou 4/4). Le sous-remplissage est justement
        # ce qui déclenche la levée DÉRIVÉE (pos < cap) : on le détecte AVANT de
        # construire, pour ne PAS marquer toutes ces mesures « levée » ni honorer
        # un implicit déclaré à tort, et on avertit que le rythme n'est pas fiable.
        n_meas = len(measures_meta)
        n_impl = sum(1 for md in measures_meta if md["implicit"])
        n_under = 0
        for md in measures_meta:
            ts = md.get("time_sig")
            if not ts:
                continue
            try:
                cap_i = classify_meter(*ts).measure_divisions * self._grid_scale
            except (MeterError, TypeError, ValueError):
                continue
            fd = md.get("filled_divisions", 0)
            if 0 < fd < cap_i:
                n_under += 1
        # Un mètre FORCÉ par l'appelant (time_override) fait foi — on ne dérive pas.
        if (
            self._forced_sig is None
            and n_meas >= 4
            and (n_impl > n_meas // 2 or n_under > n_meas // 2)
        ):
            for md in measures_meta:
                md["implicit"] = False
                md["meter_unreliable"] = True
            self._warn(
                "meter",
                "métrique variable détectée : l'OMR n'a pas lu la signature de "
                "chaque mesure — elle est DÉRIVÉE du contenu (ex. 5/16, 7/16…). "
                "Rythme et découpage en mesures à vérifier.",
            )

        # Alignement : chaque voix reçoit une entrée par mesure (vide si muette).
        all_keys = sorted({k for md in measures_data for k in md})
        streams = {k: [md.get(k, []) for md in measures_data] for k in all_keys}

        has_lyric = any(
            r.lyric
            for md in measures_data
            for raws in md.values()
            for r in raws
        )
        # Rôle STRUCTUREL : un grand portée (2 portées), un timbre clavier ou un nom
        # piano/orgue = accompagnement — on ne le scinde JAMAIS en voix haut/bas
        # (un accord de clavier n'est pas une paire de voix SATB), quel que soit le nom.
        role_accomp = (
            staff_count >= 2
            or _looks_like_piano(part_name)
            or midi_program in _KEYBOARD_MIDI
        )

        # SATB condensé : scinder les accords de portée en voix haut/bas
        # (sauf accompagnement, cf. role_accomp).
        if self.on_chord == "split" and not role_accomp:
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
            initial_fifths, initial_mode, clef_by_staff, clef_octave_change_by_staff,
            part_name, staff_count, midi_program, has_lyric,
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
        tm_el = note_el.find("time-modification")
        time_mod = None
        if tm_el is not None:
            try:
                time_mod = (
                    int(tm_el.findtext("actual-notes", "0")),
                    int(tm_el.findtext("normal-notes", "0")),
                )
            except ValueError:
                time_mod = None

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
            time_modification=time_mod,
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
        inchangées.

        On NE scinde PAS NON PLUS une voix aux accords seulement OCCASIONNELS
        (fraction < ``_CHORD_SPLIT_MIN_FRAC``) : c'est un chant monophonique avec
        quelques divisi ponctuels (gardés en note + chord_pitches), pas un SATB
        condensé (T+B écrit systématiquement en accords). Sinon on dupliquerait
        toute la voix à l'unisson (bug visible après la dé-condensation par voix
        de merge.py : le Soprano, devenu mono mais avec quelques accords, sortait
        en Soprano I ≈ Soprano II)."""
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
            chorded = sum(
                1 for meas in measures for r in meas
                if not r.is_rest and len(r.heights) >= 2
            )
            chord_frac = chorded / max(own, 1)
            has_sibling = any(
                k != (staff, voice) and k[0] == staff and c >= 0.25 * max(own, 1)
                for k, c in note_counts.items()
            )
            if max_h < 2 or has_sibling or chord_frac < _CHORD_SPLIT_MIN_FRAC:
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

    def _build_models(self, streams, measures_meta, default_meter, fifths, mode,
                      clef_by_staff, clef_octave_change_by_staff, part_name,
                      staff_count=1, midi_program=None, has_lyric=False):
        tonic = tonic_from_fifths(fifths)
        multi = len(streams) > 1

        def eff_ts(meta_i: dict, fallback: "tuple[int, int]") -> "tuple[int, int]":
            """Signature effective d'une mesure. Sous mètre jugé non fiable
            (garde-fou), on la DÉRIVE du contenu (invariant §7.3 : somme des durées
            = signature) : ``filled_divisions`` double-croches → ``N/16``. C'est
            ainsi qu'on récupère une métrique variable (5/16, 7/16…) que l'OMR n'a
            pas su lire, au lieu de forcer un mètre constant faux."""
            if meta_i.get("meter_unreliable"):
                fd = meta_i.get("filled_divisions") or 0
                # ``filled_divisions`` est en divisions internes (×grid_scale) ;
                # une double-croche vaut grid_scale unités → on repasse en
                # double-croches pour exprimer la signature en /16.
                n16 = round(fd / self._grid_scale)
                if n16 > 0:
                    return (n16, 16)
            return meta_i.get("time_sig") or fallback

        sig_counts: Counter = Counter()
        for i in range(len(next(iter(streams.values())))):
            sig_counts[eff_ts(measures_meta[i],
                              (default_meter.beats, default_meter.beat_type))] += 1
        pred_sig = sig_counts.most_common(1)[0][0] if sig_counts else (
            default_meter.beats,
            default_meter.beat_type,
        )
        # pred_meter utilisé implicitement via classify_meter(*ts) par mesure
        # Mètre d'OUVERTURE = celui de la 1re mesure (PAS le prédominant). Sur une
        # pièce à mètre variable (jubilate : 10/8 ouverture, puis 6/8, puis 4/4), le
        # prédominant peut être 4/4 (section la plus longue) ; le prendre comme
        # ouverture ferait apparaître un faux changement « 4/4 → 10/8 » dès la m1.
        opening_sig = (
            eff_ts(measures_meta[0], pred_sig) if measures_meta else pred_sig
        )

        models: List[ScoreModel] = []
        for (staff, voice) in sorted(streams):
            measures_raw = streams[(staff, voice)]
            clef = clef_by_staff.get(staff, "treble")
            # Convention chorale DÉTERMINISTE (pas une estimation) : un ténor
            # noté en clé de Sol standard sonne 1 octave sous l'écrit. Appliquée
            # UNIQUEMENT quand le nom de voix (donnée LUE via l'OCR Audiveris,
            # pas devinée) désigne explicitement un ténor, ET que la partition
            # ne porte pas déjà un <clef-octave-change> explicite (Audiveris a
            # alors déjà résolu l'octave sonnante — reproposer un décalage ferait
            # une double correction). Sur les HAUTEURS BRUTES, AVANT le choix du
            # registre du doh et l'épellation sol-fa : sinon la syllabe/marque
            # d'octave affichée resterait calculée sur l'ancien registre et ne
            # correspondrait plus à la hauteur réellement stockée (cf. mémoire
            # [[playback-pitch-authority]]). Cf. [[part-name]] : sans OCR
            # fonctionnel, part_name reste générique et ceci ne matche jamais.
            if clef == "treble" and clef_octave_change_by_staff.get(staff, 0) == 0 \
                    and _is_tenor_name(part_name):
                for raws in measures_raw:
                    for r in raws:
                        r.heights = [(s, a, o - 1) for s, a, o in r.heights]
                self._warn(
                    "octave-tenor",
                    f"voix « {part_name} » : octave corrigée automatiquement "
                    "(-1) — convention chorale pour un ténor noté en clé de Sol "
                    "(nom lu sur la partition, pas une estimation)."
                )
            doh_octave = self._pick_doh_octave(measures_raw, tonic, fifths)
            measures = []
            # Mètre courant, initialisé à la signature déclarée (pred_sig, = le
            # mètre d'ouverture affiché). On ne pose `Measure.time_signature` QUE
            # là où le mètre change vraiment vs la mesure précédente (ex. jubilate
            # 10/8 → 6/8 mes.37 → 4/4 mes.39) → l'affichage montre la nouvelle
            # mesure au-dessus de la barre, sans répéter la signature partout.
            prev_ts = opening_sig
            for i, raws in enumerate(measures_raw):
                ts = eff_ts(measures_meta[i], pred_sig)
                try:
                    meter = scale_meter(classify_meter(*ts), self._grid_scale)
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
                tonic=tonic, fifths=fifths, beats=opening_sig[0],
                beat_type=opening_sig[1],
                divisions=DIVISIONS_PER_BEAT * self._grid_scale, clef=clef, measures=measures,
                mode=mode, doh_octave=doh_octave, part_name=name,
                staff_count=staff_count, midi_program=midi_program,
                has_lyric=has_lyric,
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
                self._requantize_overfull(measure, cap)
            else:
                raise MusicXmlError(
                    f"mesure {number} : durées ({pos}) au-delà de la capacité ({cap})"
                )
        if meta.get("implicit"):
            # Levée/anacrouse DÉCLARÉE par la source (Audiveris : implicit="yes").
            # On garde sa VRAIE longueur : le silence de tête et la note de levée
            # sont réels (ex. silence pointé + double-croche de levée). On complète
            # seulement jusqu'à la longueur d'anacrouse commune aux voix (max des
            # remplissages) pour aligner le SATB — JAMAIS jusqu'à la mesure pleine —
            # et on NE retire PAS les silences de tête : sinon la note de levée
            # remonte en position 0 (« note fantôme » absente de la partition).
            fill_to = meta.get("filled_divisions") or pos
            if pos < fill_to:
                self._fill_rest(measure, fill_to - pos)
            measure.implicit = True
        elif pos < cap:
            self._fill_rest(measure, cap - pos)
            # Mesure incomplète non déclarée -> heuristique levée/anacrouse.
            # Sauf mètre jugé non fiable (cf. garde-fou) : sinon TOUTES les mesures
            # d'un score à mètre variable seraient marquées « levée ».
            if raws and not meta.get("meter_unreliable"):
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

    def _note_value_ladder(self) -> List[int]:
        """Durées de note VALIDES (divisions internes), grande→petite. Base
        binaire (ronde=16, blanche pointée=12, blanche=8, noire pointée=6,
        noire=4, croche pointée=3, croche=2, double=1) ×grid_scale, + valeurs de
        triolet (croche/noire de triolet) quand la grille est ×3."""
        vals = {v * self._grid_scale for v in (16, 12, 8, 6, 4, 3, 2, 1)}
        if self._grid_scale == 3:
            vals |= {8, 4}  # noire / croche de triolet
        return sorted(vals, reverse=True)

    def _retype_note(self, note: NoteEl) -> None:
        """Recalcule <type>/points d'après la durée (best-effort)."""
        try:
            _v, t, d = split_duration(note.duration, self._grid_scale)[0]
            note.note_type, note.dots = t, d
        except RhythmError:
            pass

    def _requantize_overfull(self, measure: Measure, cap: int) -> None:
        """Mesure trop pleine (durées OMR trop longues) : on la ramène à la
        capacité du mètre SANS jeter de note ni saboter les valeurs fiables.

        Théorie / patterns OMR :
        - une note POINTÉE est distinctive (le point est lu fiablement) → on la
          PROTÈGE (on n'y touche qu'en dernier recours) ;
        - la confusion la plus fréquente est noire↔croche (crochet/ligature
          manqué = valeur doublée) → on réduit d'abord les notes PLEINES, en
          privilégiant la MOITIÉ (12→6) ; si la moitié dépasse l'excédent, on
          réduit d'un cran pointé (point manqué : 24→18).
        Ainsi « noire pointée + croche + noire + noire » (48 en 3/4) devient
        « noire pointée + croche + croche + croche » (36) — la pointée est intacte.
        """
        excess = sum(n.duration for n in measure.notes) - cap
        if excess <= 0:
            return
        ladder = self._note_value_ladder()
        floor = self._grid_scale  # ne pas descendre sous la double-croche

        def reduce_to(cur: int, budget: int) -> "Optional[int]":
            half = cur // 2
            if half >= floor and half in ladder and (cur - half) <= budget:
                return half                       # doublement OMR : on halve
            for v in ladder:                       # sinon plus grande valeur valide
                if floor <= v < cur and (cur - v) <= budget:
                    return v                       # (ladder décroissant → réduction mini)
            return None

        # 1) d'abord absorber sur les SILENCES en trop (bourrage OMR).
        for n in measure.notes:
            if excess <= 0:
                break
            if n.is_rest and n.duration > 0:
                take = min(n.duration, excess)
                n.duration -= take
                excess -= take
        measure.notes = [n for n in measure.notes if not (n.is_rest and n.duration == 0)]
        # 2) puis les notes : non pointées d'abord (protéger les pointées),
        #    plus longues d'abord (absorbent le plus).
        order = sorted(
            (i for i, n in enumerate(measure.notes) if not n.is_rest),
            key=lambda i: (measure.notes[i].dots > 0, -measure.notes[i].duration),
        )
        for i in order:
            if excess <= 0:
                break
            n = measure.notes[i]
            v = reduce_to(n.duration, excess)
            if v is not None:
                excess -= (n.duration - v)
                n.duration = v
                n.time_modification = None
                self._retype_note(n)
        # 3) reliquat non absorbable → tronquer la fin (dernier recours).
        pos = sum(n.duration for n in measure.notes)
        while measure.notes and pos > cap:
            pos -= measure.notes.pop().duration
        # une troncature peut dépasser -> recompléter par un silence (invariant §7.3).
        if pos < cap:
            self._fill_rest(measure, cap - pos)

    def _fill_rest(self, measure: Measure, dur: int) -> None:
        if dur <= 0:
            return
        try:
            parts = split_duration(dur, self._grid_scale)
        except RhythmError:
            # Durée non décomposable sur la grille (rare : reliquat de triolet
            # tronqué) → un silence unique, plutôt que d'échouer toute la voix.
            parts = [(dur, "quarter", 0)]
        for value, ntype, dots in parts:
            measure.notes.append(NoteEl(True, value, ntype, dots))

    _TYPE_UNITS = {
        "whole": 16, "half": 8, "quarter": 4, "eighth": 2, "16th": 1, "32nd": 1,
    }

    def _notated_divisions(self, note: NoteEl) -> Optional[int]:
        """Durée NOTÉE d'une note (d'après son `<type>` + points), en divisions
        internes — c'est-à-dire la durée qu'elle aurait SANS le triolet."""
        base = self._TYPE_UNITS.get(note.note_type or "")
        if base is None:
            return None
        val = base * self._grid_scale
        if note.dots == 1:
            val = val * 3 // 2
        elif note.dots >= 2:
            val = val * 7 // 4
        return val if val > 0 else None

    def _detriplet_false_tuplets(self, model: ScoreModel) -> None:
        """Défait les FAUX triolets d'Audiveris. Théorie : un vrai triolet 3:2 tient
        exactement dans l'espace de 2 notes ; l'OMR fabrique parfois un « triolet »
        en raccourcissant 3 notes normales (croche→triolet) PUIS en ajoutant un
        silence de complément. Signal : si les 3 notes, ramenées à leur valeur
        NOTÉE, remplissent la mesure en absorbant le silence qui suit, ce n'était
        pas un triolet → on rétablit les valeurs normales (ex. « What sweet-er » :
        triolet fantôme → `. s : d . r`). Un vrai triolet (sans silence de
        complément à sa suite) est conservé."""
        if self._grid_scale <= 1:
            return
        for meas in model.measures:
            src = meas.notes
            out: List[NoteEl] = []
            i = 0
            while i < len(src):
                n = src[i]
                if n.time_modification is None:
                    out.append(n)
                    i += 1
                    continue
                actual = n.time_modification[0] or 3
                grp = [n]
                j = i + 1
                while (j < len(src) and src[j].time_modification is not None
                       and len(grp) < actual):
                    grp.append(src[j])
                    j += 1
                expanded = [self._notated_divisions(g) for g in grp]
                # Le silence qui suit doit être un silence RÉGULIER (pas un silence
                # de triolet) pour servir de « complément » d'un faux triolet.
                follow = (src[j] if (j < len(src) and src[j].is_rest
                                     and src[j].time_modification is None) else None)
                delta = (sum(expanded) - sum(g.duration for g in grp)
                         if all(e is not None for e in expanded) else -1)
                # Condition STRICTE : le silence qui suit vaut EXACTEMENT le
                # complément (delta) → c'était un bourrage d'Audiveris. Un vrai
                # triolet suivi d'un silence plus grand/plus petit est CONSERVÉ
                # (on ne « dé-trioletise » qu'à coup sûr).
                if delta > 0 and follow is not None and follow.duration == delta:
                    for g, e in zip(grp, expanded):
                        g.duration = e
                        g.time_modification = None
                    out.extend(grp)  # le silence de complément disparaît (absorbé)
                    i = j + 1
                elif len(grp) != actual:
                    # Groupe incomplet (1–2 notes avec time-modification) :
                    # ce n'est pas un triolet 3:2. On retire la marque, on
                    # garde la durée SONNANTE déjà dans la mesure.
                    for g in grp:
                        g.time_modification = None
                    out.extend(grp)
                    i = j
                else:
                    out.extend(grp)
                    i = j
            meas.notes = out

    def _extract_triplets(self, model: ScoreModel) -> None:
        """Dérive `model.triplets` (repères front {startMeasure, startBeat,
        spanBeats}, 0-based) des notes à `time_modification`. La position en TEMPS
        est calculée EXACTEMENT comme `to_solfa._measure_to_text_with_tuplets`
        (start_beat = onset // beat_divisions, span = total // beat_divisions) →
        le repère et la cellule sol-fa collée `drm` coïncident."""
        if self._grid_scale <= 1:
            return
        scale = self._grid_scale
        marks: List[dict] = []
        # Mètre COURANT (comme to_solfa), pas l'ouverture : sinon un triolet
        # en 4/4 après une ouverture 10/8 atterrit hors grille (jubilate m44
        # → startBeat=4 alors que 4/4 n'a que les temps 0–3).
        cur_ts = (model.beats, model.beat_type)
        for mi, meas in enumerate(model.measures):
            if meas.time_signature:
                cur_ts = meas.time_signature
            ts = cur_ts
            try:
                meter = scale_meter(classify_meter(*ts), scale)
            except MeterError:
                continue
            bd = meter.beat_divisions
            if bd <= 0:
                continue
            onset, i, notes = 0, 0, meas.notes
            while i < len(notes):
                n = notes[i]
                if n.time_modification is not None:
                    actual = n.time_modification[0] or 3
                    group = [n]
                    j = i + 1
                    while (j < len(notes) and notes[j].time_modification is not None
                           and len(group) < actual):
                        group.append(notes[j])
                        j += 1
                    total = sum(g.duration for g in group)
                    start_beat = onset // bd
                    span = 2 if (total % bd == 0 and total // bd >= 2) else 1
                    # Un vrai triolet a exactement `actual` notes (3:2 → 3).
                    # Un groupe incomplet = tuplet parasite Audiveris.
                    if (
                        len(group) == actual
                        and 0 <= start_beat < meter.beats
                    ):
                        marks.append({
                            "id": f"t{mi}-{start_beat}",
                            "startMeasure": mi,
                            "startBeat": start_beat,
                            "spanBeats": span,
                        })
                    onset += total
                    i = j
                else:
                    onset += n.duration
                    i += 1
        if marks:
            model.triplets = marks

    def _unify_doh_octave(self, models: List[ScoreModel]) -> None:
        """UN seul ``doh_octave`` pour toutes les voix d'une pièce, afin que les
        marques d'octave reflètent le VRAI registre SATB (soprano en haut, basse
        en bas). Sinon chaque voix minimise SES propres marques indépendamment →
        registres incohérents (ex. un soprano `s,` sous une basse `d'`, l'octave
        « inversée »). On choisit le doh partagé qui minimise le total des marques
        sur l'ensemble des voix, puis on réécrit les syllabes stockées."""
        if len(models) < 2:
            return
        samples: List["tuple"] = []  # (Pitch, tonic effectif)
        for mo in models:
            cur_tonic = mo.tonic
            for meas in mo.measures:
                if meas.key_tonic:
                    cur_tonic = meas.key_tonic
                for n in meas.notes:
                    if not n.is_rest and n.pitch is not None:
                        samples.append((n.pitch, cur_tonic))
        if not samples:
            return
        octs = sorted(p.octave for p, _ in samples)
        mid = octs[len(octs) // 2]
        best, best_cost = mid, None
        for doh in range(mid - 3, mid + 4):
            cost = 0
            for p, tn in samples:
                try:
                    _c, sh = syllable_of_pitch(p.step, p.alter, p.octave, tn, doh)
                except KeyError:
                    continue
                cost += abs(sh)
            if best_cost is None or cost < best_cost:
                best, best_cost = doh, cost
        for mo in models:
            mo.doh_octave = best
            cur_tonic = mo.tonic
            for meas in mo.measures:
                if meas.key_tonic:
                    cur_tonic = meas.key_tonic
                for n in meas.notes:
                    if n.is_rest or n.pitch is None:
                        continue
                    try:
                        core, shift = syllable_of_pitch(
                            n.pitch.step, n.pitch.alter, n.pitch.octave, cur_tonic, best
                        )
                        n.pitch.syllable = _with_marks(core, shift)
                    except KeyError:
                        pass

    def _retime_measure(self, measure: Measure, cap: int) -> None:
        """Rerègle une mesure sur une capacité ``cap`` (divisions internes) :
        déficit → silences ajoutés ; excédent → notes de fin retirées (§7.3)."""
        pos = sum(n.duration for n in measure.notes)
        while measure.notes and pos > cap:
            pos -= measure.notes.pop().duration
        if pos < cap:
            self._fill_rest(measure, cap - pos)

    def _reconcile_variable_meter(self, models: List[ScoreModel]) -> None:
        """Métrique variable dérivée du contenu : rendre le mètre de chaque mesure
        COHÉRENT entre voix (colonnes sol-fa alignées, MusicXML SATB valide).

        Pour chaque mesure on prend le mètre le plus FRÉQUENT sur les voix — le
        bruit OMR d'une voix isolée (ex. 11/16 au lieu de 5/16) est ainsi écarté —
        puis on rerègle chaque voix dessus. On n'agit QUE là où au moins une voix a
        un mètre dérivé ``/16`` (sinon on ne touche pas aux vrais changements de
        mètre déclarés)."""
        if len(models) < 2:
            return
        n = max((len(m.measures) for m in models), default=0)

        def eff_list(mo: ScoreModel) -> List["tuple[int, int]"]:
            out: List["tuple[int, int]"] = []
            cur = (mo.beats, mo.beat_type)
            for meas in mo.measures:
                if meas.time_signature:
                    cur = meas.time_signature
                out.append(cur)
            return out

        per = [eff_list(m) for m in models]
        targets: List[Optional["tuple[int, int]"]] = [None] * n
        variable = False
        for i in range(n):
            sigs = [per[j][i] for j in range(len(models)) if i < len(per[j])]
            if any(s[1] == 16 for s in sigs):
                targets[i] = Counter(sigs).most_common(1)[0][0]
                variable = True
        if not variable:
            return
        for mi, mo in enumerate(models):
            prev = (mo.beats, mo.beat_type)
            for i, meas in enumerate(mo.measures):
                eff = targets[i] if (i < n and targets[i] is not None) else per[mi][i]
                if i < n and targets[i] is not None and per[mi][i] != targets[i]:
                    try:
                        cap = classify_meter(*eff).measure_divisions * self._grid_scale
                    except MeterError:
                        cap = None
                    if cap is not None:
                        self._retime_measure(meas, cap)
                meas.time_signature = eff if eff != prev else None
                prev = eff

    def _emit_raw(self, measure, raw, tonic, fifths, doh_octave) -> None:
        if raw.is_rest:
            if raw.note_type:
                measure.notes.append(NoteEl(
                    True, raw.duration, raw.note_type, raw.dots,
                    time_modification=raw.time_modification,
                ))
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
        ntype = raw.note_type or split_duration(raw.duration, self._grid_scale)[0][1]
        note = NoteEl(
            False, raw.duration, ntype, raw.dots, pitch,
            time_modification=raw.time_modification,
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
        """Si exactement 4 VOIX chantées aux noms génériques, nomme S/A/T/B par
        tessiture. Les accompagnements (grand portée / clavier) sont exclus du
        décompte : on ne fabrique jamais un SATB à partir d'un clavier."""
        def _vocal(m: ScoreModel) -> bool:
            return not (
                getattr(m, "staff_count", 1) >= 2
                or _looks_like_piano(m.part_name)
                or getattr(m, "midi_program", None) in _KEYBOARD_MIDI
            )
        vocal = [m for m in models if _vocal(m)]
        # "Voice" (anglais) est le PLACEHOLDER PROPRE À AUDIVERIS pour une part
        # sans titre lisible dans la partition (constaté sur du MusicXML réel :
        # <part-name>Voice</part-name>, pas balise absente) — distinct de "Voix"
        # (notre propre repli quand la balise <part-name> manque totalement,
        # cf. ``_read_part_list``). Sans ce cas, l'estimation SATB silencieuse
        # ci-dessous ne se détecte jamais sur une vraie sortie Audiveris.
        def _is_generic(name: str) -> bool:
            base = name.split(" v")[0].strip().lower()
            low = name.strip().lower()
            return base in ("", "voix", "voice", "p1", "p2", "p3", "p4") or low.startswith(
                ("voix", "voice")
            )
        generic = all(_is_generic(m.part_name) for m in vocal)
        if len(vocal) == 4 and generic:
            order = sorted(vocal, key=self._median_height, reverse=True)
            for m, nm in zip(order, ("Soprano", "Alto", "Tenor", "Bass")):
                m.part_name = nm
            self._warn(
                "part-name",
                "noms de voix non fournis par Audiveris — attribution "
                "Soprano/Alto/Tenor/Bass par tessiture (estimation, pas une "
                "donnée lue). Une voix de ténor notée en clé de Sol classique "
                "peut sonner une octave plus bas que noté : vérifiez au son, "
                "corrigez via le bouton d'octave de la vue Partition si besoin."
            )

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


def read_musicxml_metadata(source: Union[str, bytes, Path]) -> dict:
    """Extrait titre, compositeur et numéro d'œuvre depuis l'en-tête MusicXML."""
    from .musicxml import read_score_metadata

    root = _parse_root(source)
    return read_score_metadata(root)


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
