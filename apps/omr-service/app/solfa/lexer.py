"""Analyse lexicale de la notation sol-fa tonique (dialecte malgache).

Grammaire (v1) — voir packages/shared-contracts/solfa-format.md :

    partition := mesure ( '|' mesure )*
    mesure    := temps ( (':' | '!') temps )*   ( ':' et '!' séparent les temps ;
                                                   '!' marque la mi-mesure )
    temps     := part  ( '.' part )*             ( '.' subdivise en parts égales )
    part      := cellule ( ',' cellule )*        ( ',' (hors octave) subdivise encore )
    cellule   := syllabe | '-' | (vide)

  - syllabe : d r m f s l t (+ chromatismes ri fi ta...), suffixes d'octave
              ' (aigu) et , ou _ (grave), répétables.
  - '-'      : prolongation (liaison) de la note précédente.
  - temps entièrement vide            : silence.
  - sous-cellule vide en tête (« .m ») : silence (anacrouse).
  - sous-cellule vide après une note (« m. ») : prolongation.
  - sous-cellule vide après une tenue (« -. ») : silence (demi-temps).
  - cellule vide issue d'un ',' (« -.,d ») : silence explicite (quart).

  Double rôle du ',' : marque d'octave grave quand il suit une note (« t, »),
  séparateur rythmique sinon (« ,d », « -.,d »).

La barre de mesure est '|'. Dans une partition issue d'un PDF, c'est le module
de mise en page (app/pdf) qui insère les '|' à partir des positions.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .keys import normalize_tonic
from .rhythm import DIVISIONS_PER_BEAT, Meter, MeterError, classify_meter

# Un atome = une tenue (- / _) OU une syllabe (lettres + marques d'octave).
# Sert à re-scinder les cellules « mashées » de l'OCR ('l,s,', 'f, r', 'm S', '-s').
_ATOM_RE = re.compile(r"-|_|[A-Za-z]+[',_]*")

# Syllabes sol-fa (chromatismes avant monogrammes) pour découper un triolet `drm`.
_TRIPLET_ATOM_RE = re.compile(
    r"(-|_|0|"
    r"de|fe|se|di|ri|ra|ma|fi|si|sa|li|la|ta|"
    r"[drmfslt])"
    r"([',_]*)",
    re.IGNORECASE,
)

# lettres de syllabe + éventuelles marques d'octave (aigu ' / grave , _)
_SYLLABLE_RE = re.compile(r"^([a-zA-Z]+)([',_]*)$")
_BEAT_SEP_RE = re.compile(r"[:!;]")  # ';' = ':' fréquemment mal lu par l'OCR
# Un ',' est un séparateur rythmique s'il n'est PAS collé à une note ou à une
# autre marque d'octave (auquel cas il abaisse l'octave). D'où le lookbehind.
_RHYTHM_COMMA_RE = re.compile(r"(?<![A-Za-z',_]),")
# Marqueur de changement de mesure en tête d'une barre : ``(6/8)`` (mètre
# variable). Posé par ``to_solfa`` au-dessus de la barre où le mètre change ;
# relu ici pour un round-trip texte↔modèle complet (l'édition ne l'efface plus).
_METER_MARK_RE = re.compile(r"^\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)\s*")
# Changement de tonalité (mouvable-do) en tête d'une barre : ``(Doh=F)``,
# ``(Doh = Bb)``, ``(doh=F#)``. Posé par ``to_solfa`` là où le doh change ; relu
# ici pour re-résoudre les syllabes suivantes contre la NOUVELLE tonique.
_DOH_MARK_RE = re.compile(
    r"^\s*\(\s*[Dd]oh\s*=\s*([A-Ga-g][#b♯♭]?)\s*\)\s*"
)
# Autres annotations de tête émises par ``to_solfa`` : ``(♩=75)``, ``[D.C.]``,
# ``[Fine]``, ``[Segno]``… Métadonnées à durée nulle (tempo, navigation) lues du
# MODÈLE par l'UI ; le lexer les IGNORE (lossy, volontaire — elles ne changent
# pas la grille rythmique, contrairement au mètre ``(N/M)`` et au doh ``(Doh=)``).
_ANNOTATION_RE = re.compile(r"^\s*(?:\([^)]*\)|\[[^\]]*\])\s*")


class LexError(ValueError):
    pass


@dataclass
class Cell:
    kind: str                 # 'note' | 'rest' | 'hold'
    divisions: int
    core: Optional[str] = None        # syllabe sans marque d'octave
    octave_shift: int = 0
    uncertain: bool = False   # silence « placeholder » : temps présent, contenu non lu
    # Triolet : (actual-notes, normal-notes), ex. (3, 2). None = rythme binaire.
    tuplet: Optional[Tuple[int, int]] = None
    # Type MusicXML préféré pour un membre de triolet ('eighth' | 'quarter').
    tuplet_type: Optional[str] = None
    # Tonique effective (mouvable-do) pour cette cellule si un ``(Doh=X)`` a
    # changé le doh en amont ; None = tonique globale passée au parseur.
    tonic: Optional[str] = None


def split_triplet_atoms(token: str) -> List[str]:
    """Découpe `drm` / `d,rm` en 3 syllabes sol-fa, ou [] si ce n'est pas un triolet."""
    s = token.replace(" ", "")
    if not s or "." in s or _RHYTHM_COMMA_RE.search(s):
        return []
    out: List[str] = []
    pos = 0
    while pos < len(s):
        m = _TRIPLET_ATOM_RE.match(s, pos)
        if not m:
            return []
        out.append(m.group(0))
        pos = m.end()
    return out if len(out) == 3 else []


def is_triplet_beat(raw: str) -> bool:
    """Temps au format triolet : exactement 3 syllabes collées (ex. ``drm``)."""
    return bool(split_triplet_atoms(raw.strip()))


def _parse_triplet_beat(raw: str, total_divisions: int, span_beats: int = 1) -> List[Cell]:
    """3 notes dans ``total_divisions`` (1 ou 2 temps), avec time-modification 3:2."""
    atoms = split_triplet_atoms(raw.strip())
    if len(atoms) != 3:
        raise LexError(f"triolet invalide: {raw!r}")
    if total_divisions % 3 != 0:
        raise LexError(
            f"triolet non représentable dans {raw!r}: "
            f"{total_divisions} divisions non divisibles par 3"
        )
    part = total_divisions // 3
    note_type = "eighth" if span_beats <= 1 else "quarter"
    cells: List[Cell] = []
    for atom in atoms:
        cell = _parse_cell(atom, part)
        cell.tuplet = (3, 2)
        cell.tuplet_type = note_type
        cells.append(cell)
    return cells


@dataclass
class BarMeta:
    """Métadonnées d'une barre reconstruites par le lexer.

    ``cap`` : capacité de la barre en divisions (dépend de son mètre courant).
    ``time_sig`` : (beats, beat_type) si un marqueur ``(N/M)`` ouvrait la barre —
    un changement de mesure à consigner sur ``Measure.time_signature``.
    ``key_tonic`` : tonique normalisée si un ``(Doh=X)`` ouvrait la barre —
    un changement de tonalité à consigner sur ``Measure.key_tonic``."""
    cap: int
    pulses: int
    time_sig: Optional[Tuple[int, int]] = None
    key_tonic: Optional[str] = None


def _parse_cell(raw: str, divisions: int) -> Cell:
    token = raw.strip()
    if token in ("-", "_"):     # '_' = tenue (dialecte kristy), comme '-'
        return Cell(kind="hold", divisions=divisions)
    if token == "0":            # silence explicite (sous-temps sans ambiguïté)
        return Cell(kind="rest", divisions=divisions)
    m = _SYLLABLE_RE.match(token)
    if not m:
        raise LexError(f"cellule invalide: {raw!r}")
    core = m.group(1).lower()
    marks = m.group(2)
    octave_shift = marks.count("'") - marks.count(",") - marks.count("_")
    return Cell(kind="note", divisions=divisions, core=core, octave_shift=octave_shift)


def _split_parts(total: int, n: int, ctx: str, lenient: bool = False) -> List[int]:
    """Répartit `total` divisions en `n` parts.

    - Si `total` est divisible par `n` : parts égales (comportement strict).
    - Sinon, mode **strict** (défaut) : LexError — utile pour la saisie manuelle
      où une subdivision impaire est probablement une faute.
    - Sinon, mode **lenient** (OCR/PDF bruité) : on répartit par arrondi des
      frontières -> cellules entières quasi-égales dont la somme reste `total`
      (ex. 3 parts de 4 divisions -> [1, 2, 1]), plutôt que d'échouer.
      Une sur-segmentation (n > total, non représentable au 16e) reste une erreur.
    """
    if total % n == 0:
        return [total // n] * n
    if not lenient or n > total:
        raise LexError(
            f"subdivision non supportée (v1) dans {ctx!r}: {n} parts pour "
            f"{total} divisions"
        )
    bounds = [round(total * i / n) for i in range(n + 1)]
    return [bounds[i + 1] - bounds[i] for i in range(n)]


def _parse_beat(
    raw: str, beat_divisions: int = DIVISIONS_PER_BEAT, lenient: bool = False
) -> List[Cell]:
    """Un temps -> cellules.

    '.' subdivise le temps en parts égales ; ',' (hors marque d'octave)
    subdivise encore chaque part. `beat_divisions` vaut 4 (temps = noire) ou
    6 (mesure composée, temps = noire pointée -> subdivision par 3 possible).
    `lenient` : tolère les subdivisions impaires par arrondi (entrée OCR/PDF).

    Cellule vide :
      - en tête d'un temps (``.m``) → silence (anacrouse) ;
      - après une **note** via '.' (``m.``) → prolongation ;
      - après une **tenue** via '.' (``-.``) → silence (demi-temps) ;
      - issue d'un ',' (``-.,d``) → silence explicite ;
    ``-`` prolonge explicitement la note précédente ; ``0`` est un silence explicite.
    """
    # Temps entièrement vide -> un seul silence de la durée du temps.
    if raw.strip() == "" or all(c in ". " for c in raw):
        return [Cell(kind="rest", divisions=beat_divisions)]

    halves = raw.split(".")
    half_divs = _split_parts(beat_divisions, len(halves), raw, lenient)

    cells: List[Cell] = []
    seen_content = False
    for half, half_div in zip(halves, half_divs):
        quarters = _RHYTHM_COMMA_RE.split(half)
        quarter_divs = _split_parts(half_div, len(quarters), raw, lenient)
        comma_split = len(quarters) > 1
        for quarter, quarter_div in zip(quarters, quarter_divs):
            token = quarter.strip()
            if token == "-":
                cells.append(Cell(kind="hold", divisions=quarter_div))
                seen_content = True
            elif token == "":
                # ',' => silence explicite ; '.' en tête => silence ;
                # '.' après note => prolongation ; '.' après tenue => silence.
                if comma_split or not seen_content:
                    cells.append(Cell(kind="rest", divisions=quarter_div))
                elif cells and cells[-1].kind == "note":
                    cells.append(Cell(kind="hold", divisions=quarter_div))
                else:
                    cells.append(Cell(kind="rest", divisions=quarter_div))
            else:
                # Correction grammaticale (lenient/OCR) : un token « mashé » ou
                # espacé ('l,s,', 'f, r', 'm S', '-s') = plusieurs atomes → on le
                # scinde en sous-cellules égales (comme une subdivision), au lieu
                # d'échouer sur une cellule invalide.
                atoms = _ATOM_RE.findall(token) if lenient else []
                if len(atoms) > 1:
                    subs = _split_parts(quarter_div, len(atoms), raw, lenient)
                    for atom, d in zip(atoms, subs):
                        if atom in ("-", "_"):
                            cells.append(Cell(kind="hold", divisions=d))
                        else:
                            cells.append(_parse_cell(atom, d))
                elif lenient and len(atoms) == 1:
                    # Un unique atome entouré de bruit OCR (', m,' → 'm,') : on
                    # garde l'atome, on ignore la ponctuation parasite autour.
                    atom = atoms[0]
                    if atom in ("-", "_"):
                        cells.append(Cell(kind="hold", divisions=quarter_div))
                    else:
                        cells.append(_parse_cell(atom, quarter_div))
                elif lenient and not atoms:
                    # Que du bruit (ponctuation seule) → silence « placeholder » :
                    # un temps existe mais son contenu n'a pas pu être lu.
                    cells.append(Cell(kind="rest", divisions=quarter_div, uncertain=True))
                else:
                    cells.append(_parse_cell(token, quarter_div))
                seen_content = True
    return cells


def notation_has_triplet_beats(notation: str) -> bool:
    """True si au moins un temps est au format triolet ``drm``."""
    text = notation.replace("\r", " ").replace("\n", " ")
    for bar in text.split("|"):
        bar = bar.strip()
        while bar:
            mark = _METER_MARK_RE.match(bar)
            if mark:
                bar = bar[mark.end():]
                continue
            ann = _ANNOTATION_RE.match(bar)
            if ann:
                bar = bar[ann.end():]
                continue
            break
        for beat in _BEAT_SEP_RE.split(bar):
            if is_triplet_beat(beat):
                return True
    return False


def tokenize(
    notation: str, meter: Optional[Meter] = None, lenient: bool = False,
    degrade: bool = False,
    division_scale: int = 1,
    triplets: Optional[List[Tuple[int, int, int]]] = None,
) -> Tuple[List[Cell], int, List[BarMeta]]:
    """notation -> (cellules à plat, nb de temps par mesure, métadonnées de barres).

    ``meter`` : mètre INITIAL (None => inférence à la noire, comportement
    d'origine). Une barre peut ouvrir sur un marqueur ``(N/M)`` qui change le
    mètre courant à partir d'elle (mesure variable, ex. jubilate 10/8 → 6/8) ;
    chaque barre est alors découpée avec SES divisions par temps (4 = temps noire,
    6 = mesure composée). Le mètre courant se reporte d'une barre à l'autre.

    ``division_scale`` : facteur (1 ou 3). Avec triolets, scale=3 pour que
    chaque temps ait un nombre de divisions divisible par 3 (noire = 12).

    ``triplets`` : marques ``(start_measure, start_beat, span_beats)`` 0-based.
    Un triolet sur 2 temps occupe une seule cellule notation ``drm`` sans
    séparateur ``:`` entre les deux temps.

    La signature rythmique inférée est le **mode** des pulsations par mesure (et
    non la 1re mesure), ce qui ignore l'anacrouse et la mesure finale, souvent
    plus courtes ; sur égalité, on prend la plus grande valeur.
    `lenient` : tolère les subdivisions impaires + cellules mashées (OCR/PDF).
    """
    if division_scale < 1:
        raise LexError(f"division_scale invalide: {division_scale}")

    text = notation.replace("\r", " ").replace("\n", " ").strip()
    bars_raw = [b.strip() for b in text.split("|")]
    bars_raw = [b for b in bars_raw if b != ""]

    # Index rapide des triolets : (mesure, temps_départ) -> span 1|2
    triplet_at: dict = {}
    for t in triplets or []:
        if len(t) >= 3:
            triplet_at[(int(t[0]), int(t[1]))] = 1 if int(t[2]) <= 1 else 2

    bar_pulses: List[int] = []
    cells: List[Cell] = []
    bars: List[BarMeta] = []
    cur_meter = meter
    cur_tonic: Optional[str] = None  # doh courant (None = tonique globale)

    for mi, bar in enumerate(bars_raw):
        time_sig: Optional[Tuple[int, int]] = None
        bar_key_tonic: Optional[str] = None
        # Peler les marqueurs de tête (dans n'importe quel ordre) : (N/M) change
        # le mètre courant, (Doh=X) change le doh courant → tous deux capturés ;
        # les autres ((♩=…), [D.C.]…) sont ignorées (lues du modèle par l'UI).
        while bar:
            mark = _METER_MARK_RE.match(bar)
            if mark:
                nb, nbt = int(mark.group(1)), int(mark.group(2))
                try:
                    cur_meter = classify_meter(nb, nbt)
                except MeterError as exc:
                    raise LexError(str(exc)) from exc
                time_sig = (nb, nbt)
                bar = bar[mark.end():]
                continue
            doh = _DOH_MARK_RE.match(bar)
            if doh:
                try:
                    cur_tonic = normalize_tonic(doh.group(1))
                except KeyError as exc:
                    raise LexError(str(exc)) from exc
                bar_key_tonic = cur_tonic
                bar = bar[doh.end():]
                continue
            ann = _ANNOTATION_RE.match(bar)
            if ann:
                bar = bar[ann.end():]
                continue
            break
        bar = bar.strip()

        cell_start = len(cells)
        beat_divisions = (
            cur_meter.beat_divisions if cur_meter is not None else DIVISIONS_PER_BEAT
        ) * division_scale
        beats = _BEAT_SEP_RE.split(bar)

        # Avec triolets 2 temps, la notation a moins de tokens que de pulsations :
        # un `drm` marqué span=2 avance de 2 temps logiques pour 1 token.
        bi_tok = 0
        bi_logic = 0
        while bi_tok < len(beats):
            beat = beats[bi_tok]
            span = 1
            try:
                if is_triplet_beat(beat):
                    span = triplet_at.get((mi, bi_logic), 1)
                    cells.extend(
                        _parse_triplet_beat(beat, beat_divisions * span, span)
                    )
                elif degrade:
                    try:
                        cells.extend(_parse_beat(beat, beat_divisions, lenient))
                    except LexError:
                        cells.append(
                            Cell(
                                kind="rest",
                                divisions=beat_divisions,
                                uncertain=True,
                            )
                        )
                else:
                    cells.extend(_parse_beat(beat, beat_divisions, lenient))
            except LexError:
                if degrade:
                    cells.append(
                        Cell(kind="rest", divisions=beat_divisions, uncertain=True)
                    )
                else:
                    raise
            bi_tok += 1
            bi_logic += span

        # Étiqueter les cellules de cette barre avec le doh courant (mouvable-do).
        if cur_tonic is not None:
            for c in cells[cell_start:]:
                c.tonic = cur_tonic

        if cur_meter is not None:
            pulses_meta = cur_meter.beats
            cap = cur_meter.measure_divisions * division_scale
        else:
            pulses_meta = bi_logic if bi_logic > 0 else len(beats)
            cap = pulses_meta * DIVISIONS_PER_BEAT * division_scale
        bar_pulses.append(pulses_meta)
        bars.append(
            BarMeta(cap=cap, pulses=pulses_meta, time_sig=time_sig, key_tonic=bar_key_tonic)
        )

    if bar_pulses:
        counts = Counter(bar_pulses)
        top = max(counts.values())
        beats_per_measure = max(v for v, c in counts.items() if c == top)
    else:
        beats_per_measure = 0

    return cells, beats_per_measure, bars
