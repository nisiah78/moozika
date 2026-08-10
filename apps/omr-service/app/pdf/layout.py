"""Reconstruction de la mise en page : runs positionnés -> notation sol-fa.

Règles déduites du format réel (recueils malgaches, cf. jesoa-tsy-mba-mandao) :
  - Les runs sont regroupés en lignes par proximité verticale (y).
  - Sens de lecture : si l'en-tête (« dia ») est en bas (y faible), l'axe Y est
    inversé (ex. the-lord-bless-you) → on lit y croissant.
  - Une ligne « voix » contient des séparateurs de temps ':' ou '!'.
  - Barre de mesure : glyphe « | », ou deux temps sans séparateur (jesoa).
  - Si l'en-tête impose 4/4 et que les barres du PDF ne portent que 2 temps,
    on fusionne les demi-mesures (ex. lord-bless).
  - Système monodique en tête (label Sopranos) → Soprano seul, autres = silences.
  - Glyphes Tj unaires : collage ``d``+``,`` → ``d,``.
  - Alignement intra-système par grille x (midbars) : silences si une voix
    entre plus à droite (ex. ténor/basse en pause pendant que le soprano reprend).
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .extract import Run
from ..solfa.keys import CHROMATIC, DIATONIC
from ..solfa.lexer import LexError, _parse_beat
from ..solfa.rhythm import DIVISIONS_PER_BEAT

_Y_TOL = 6.0
# Écart inter-système : jesoa ≈ 88, lord-bless ≈ 61, 244 (SATB→paroles) ≈ 56.
_SYSTEM_GAP = 50.0
_GLYPH_GAP = 12.0
_HEADER_GLYPH_GAP = 22.0  # titres / « Do dia Gb » plus aérés
# Grand trou horizontal après un temps → nouvelle mesure (grilles 3/4 type 244).
_BAR_GAP = 45.0
_SEP_CHARS = set(":!;")
_BAR_CHAR = "|"
_VALID_CORES = set(DIATONIC) | set(CHROMATIC)
_SYLLABLE_RE = re.compile(r"^([a-zA-Z]+)([',_]*)$")
_SATB = ["Soprano", "Alto", "Tenor", "Bass"]


@dataclass
class Header:
    title: str = ""
    composer: str = ""
    tonic: str = "C"
    beats: int = 4
    beat_type: int = 4
    tempo: Optional[int] = None


@dataclass
class SolfaDocument:
    header: Header
    voices: List[str] = field(default_factory=list)
    voice_names: List[str] = field(default_factory=list)


def _cluster_rows(runs: List[Run]) -> List[List[Run]]:
    """Regroupe les runs en lignes (par y décroissant), triées par x."""
    ordered = sorted(runs, key=lambda r: (-r.y, r.x))
    rows: List[List[Run]] = []
    cur: List[Run] = []
    cur_y: Optional[float] = None
    for run in ordered:
        if cur_y is None or abs(run.y - cur_y) <= _Y_TOL:
            cur.append(run)
            cur_y = run.y if cur_y is None else cur_y
        else:
            rows.append(sorted(cur, key=lambda r: r.x))
            cur = [run]
            cur_y = run.y
    if cur:
        rows.append(sorted(cur, key=lambda r: r.x))
    return rows


def _row_text(row: List[Run]) -> str:
    return " ".join(r.text for r in row)


def _row_plain(row: List[Run], gap_tol: float = _HEADER_GLYPH_GAP) -> str:
    """Texte d'en-tête : glyphes recollés (``Do dia Gb,4/4``)."""
    return " ".join(r.text for r in merge_close_glyphs(row, gap_tol=gap_tol))


def _is_rest_grid_row(row: List[Run]) -> bool:
    """Grille de silences « : | : : | : : » (aucune syllabe, mais structure rythmique)."""
    text = _row_text(row)
    if ":" not in text:
        return False
    compact = re.sub(r"\s+", "", text)
    if not compact or not re.fullmatch(r"[:|!\-]+", compact):
        return False
    return compact.count(":") >= 2


def _is_voice_row(row: List[Run]) -> bool:
    """Ligne de musique : contient des séparateurs de temps + des syllabes sol-fa.

    Robuste aux dialectes : séparateurs `: ! ; |`, tenues `-`/`_`.
    """
    # Filtre « bruit de barres de mesure » : un trait `|` est un grand trait
    # vertical que l'OCR/YOLO éclate en plusieurs boîtes réparties en y, formant
    # une BANDE PARASITE (dominée par des `|`) entre deux vraies voix — d'où des
    # voix fantômes (mivavaha : 5 au lieu de 4). Une vraie ligne (sonnante OU au
    # repos) est structurée par des séparateurs de temps `:`/`!` ; on écarte donc
    # les lignes où les barres l'emportent sur les séparateurs.
    n_bar = sum(1 for r in row if r.text.strip() == _BAR_CHAR)
    n_sep = sum(1 for r in row if r.text.strip() in _SEP_CHARS)
    if n_bar > n_sep:
        return False

    text = _row_text(row)
    if not any(c in text for c in _SEP_CHARS) and _BAR_CHAR not in text:
        return False
    # Découpe en atomes ; une ligne de voix est majoritairement des syllabes
    # sol-fa (les paroles contenant un ':' isolé sont ainsi écartées).
    atoms = [a for a in re.split(r"[:!;|.,\s]+", text) if a]
    n_alpha = 0
    solfa = 0
    for a in atoms:
        if a in ("-", "_"):
            continue
        if any(c.isalpha() for c in a):
            n_alpha += 1
        m = _SYLLABLE_RE.match(a)
        if m and m.group(1).lower() in _VALID_CORES:
            solfa += 1
    if solfa >= 1 and solfa >= 0.5 * n_alpha:
        return True
    return _is_rest_grid_row(row)


def _row_y(row: List[Run]) -> float:
    return row[0].y


def _orient_rows(rows: List[List[Run]]) -> Tuple[List[List[Run]], bool]:
    """Ordre de lecture + sens Y (True = y décroissant = PDF classique)."""
    if not rows:
        return rows, True
    header_y: Optional[float] = None
    for row in rows:
        # « DodiaGb » (sans espaces) ou « Do dia Gb ».
        if re.search(r"dia|doh", _row_plain(row), re.I):
            header_y = _row_y(row)
            break
    if header_y is None:
        return rows, True
    ys = [_row_y(r) for r in rows]
    mid = (min(ys) + max(ys)) / 2.0
    if header_y < mid:
        return list(reversed(rows)), False
    return rows, True


def parse_header(rows: List[List[Run]]) -> Header:
    """Extrait titre / tonique / mesure / tempo des lignes d'en-tête."""
    header = Header()
    plain_rows = [_row_plain(r) for r in rows if not _is_voice_row(r)]
    blob = "  ".join(plain_rows)
    blob_no_paren = re.sub(r"\([^)]*\)", " ", blob)

    for t in plain_rows:
        compact = re.sub(r"\s+", "", t)
        if len(compact) < 4 or re.fullmatch(r"\d+", compact):
            continue
        if re.match(r"^\d+\s*Soprano", t, re.I):
            continue
        if re.fullmatch(r"[Aamen\s.\-]+", t, re.I):
            continue
        header.title = re.sub(r"\s+", " ", t.strip())
        break

    # Compositeur (best-effort) : une ligne EN CAPITALES, distincte du titre,
    # ni tonique ni mesure. Ex. « ANDRIAMIADAMAHATRATRA ». Peut échouer sur un
    # OCR bruité — reste optionnel.
    for t in plain_rows:
        compact = re.sub(r"[^A-Za-z]", "", t)
        clean = re.sub(r"\s+", " ", t.strip())
        if len(compact) >= 6 and compact.isupper() and clean != header.title:
            header.composer = clean
            break

    # « dia Db » / « DodiaGb » / « Do dia D b » (bémol en glyphe séparé).
    m = re.search(r"dia\s*([A-Ga-g])\s*([#b♭♯]?)", blob, re.I)
    if not m:
        m = re.search(r"(?:doh|do)\s*=?\s*([A-Ga-g])\s*([#b♭♯]?)", blob, re.I)
    if m:
        acc = m.group(2).replace("♯", "#").replace("♭", "b")
        header.tonic = m.group(1).upper() + acc

    m = re.search(r"(\d+)\s*/\s*(\d+)", blob_no_paren)
    if m:
        nb, nbt = int(m.group(1)), int(m.group(2))
        # Rejette les lectures OCR aberrantes (ex. « 4/64 ») : on ne garde qu'une
        # signature plausible, sinon on conserve le défaut (4/4). Le parsing des
        # notes s'appuie de toute façon sur l'inférence par pulsations, pas sur
        # cette valeur — mais elle sert à l'affichage.
        if 1 <= nb <= 12 and nbt in (2, 4, 8, 16):
            header.beats, header.beat_type = nb, nbt

    m = re.search(r"=\s*c?\.?\s*(\d+)", blob)
    if m:
        header.tempo = int(m.group(1))

    return header


def merge_close_glyphs(row: List[Run], gap_tol: float = _GLYPH_GAP) -> List[Run]:
    """Recolle les glyphes horizontalement proches (``d``+``,`` → ``d,``)."""
    if not row:
        return []
    ordered = sorted(row, key=lambda r: r.x)
    out: List[Run] = []
    buf_text = ordered[0].text
    buf_x = ordered[0].x
    buf_y = ordered[0].y
    buf_font = ordered[0].font
    prev_x = ordered[0].x
    for run in ordered[1:]:
        if run.x - prev_x <= gap_tol:
            buf_text += run.text
        else:
            out.append(Run(y=buf_y, x=buf_x, font=buf_font, text=buf_text))
            buf_text, buf_x, buf_y, buf_font = run.text, run.x, run.y, run.font
        prev_x = run.x
    out.append(Run(y=buf_y, x=buf_x, font=buf_font, text=buf_text))
    return out


def _is_pitched_beat(tok: str) -> bool:
    """Vrai s'il y a au moins une syllabe (pas seulement tenues / silences)."""
    if tok in ("", "-", "BAR"):
        return False
    return any(c.isalpha() for c in tok)


def _resolve_empty_holds(
    tokens: List[Tuple[str, float]],
) -> List[Tuple[str, float]]:
    """« f : : f » → tenue ; vide sans syllabe plus loin dans la ligne → silence.

    Les grilles d'hymnes (244, anacrouses) codent les tenues par des temps
    vides ; en fin de phrase (plus aucune syllabe sur la ligne) le vide = silence
    (blanche pointée + noire de silence pour T/B m18).
    """
    n = len(tokens)
    has_pitch_after = [False] * n
    seen = False
    for i in range(n - 1, -1, -1):
        has_pitch_after[i] = seen
        if _is_pitched_beat(tokens[i][0]):
            seen = True

    out: List[Tuple[str, float]] = []
    for i, (tok, x) in enumerate(tokens):
        if tok == "":
            out.append(("-" if has_pitch_after[i] else "", x))
        else:
            out.append((tok, x))
    return out


def _tokenize_row_anchored(row: List[Run]) -> List[Tuple[str, float]]:
    """Jetons (texte, x) : temps ou 'BAR'.

    « f : : f » → f, -, f ; vide en fin de mesure → silence.
    Grand trou en x (syllabe *ou* séparateur) → BAR.
    """
    merged = merge_close_glyphs(row)
    tokens: List[Tuple[str, float]] = []
    buf = ""
    buf_x = 0.0
    prev_x: Optional[float] = None
    ended_with_sep = False
    last_sep_x = 0.0

    def flush_beat(at_x: Optional[float] = None):
        nonlocal buf, buf_x
        cell = buf.strip()
        if cell == "_":            # tenue notée '_' (ex. kristy) -> '-'
            cell = "-"
        if at_x is not None:
            x = at_x
        elif buf:
            x = buf_x
        else:
            x = last_sep_x
        # Cellule vide : on laisse "" ; _resolve_empty_holds trancheratenue/silence.
        tokens.append((cell, x))
        buf = ""

    def flush_bar_boundary(*, allow_trailing_empty: bool = False):
        nonlocal ended_with_sep
        if ended_with_sep:
            # Le « : » a déjà clos le temps précédent ; ne pas inventer un
            # temps vide avant une barre (sinon 3 temps / demi-mesure).
            # En fin de ligne, le vide final reste un silence légitime.
            if allow_trailing_empty:
                flush_beat(last_sep_x)
            ended_with_sep = False
        elif buf.strip():
            flush_beat()

    def maybe_bar_at(x: float) -> None:
        if tokens and tokens[-1][0] != "BAR":
            flush_bar_boundary()
            if tokens and tokens[-1][0] != "BAR":
                tokens.append(("BAR", x))

    for run in merged:
        raw = run.text
        starts_syllable = bool(raw.strip()) and raw.strip()[0] not in (_SEP_CHARS | {_BAR_CHAR})

        if (
            prev_x is not None
            and run.x - prev_x >= _BAR_GAP
            and starts_syllable
            and (buf.strip() or tokens)
        ):
            maybe_bar_at(run.x)

        if starts_syllable and buf.strip() and not any(c in _SEP_CHARS for c in buf):
            flush_beat()
            if tokens and tokens[-1][0] != "BAR":
                tokens.append(("BAR", run.x))
            ended_with_sep = False

        for ch in raw:
            if ch in _SEP_CHARS:
                flush_beat(run.x)
                ended_with_sep = True
                last_sep_x = run.x
            elif ch == _BAR_CHAR:
                flush_bar_boundary()
                tokens.append(("BAR", run.x))
                ended_with_sep = False
            elif ch == " ":
                if buf.strip():
                    flush_beat()
                    ended_with_sep = False
            else:
                if not buf:
                    buf_x = run.x
                buf += ch
                ended_with_sep = False
        prev_x = run.x

    flush_bar_boundary(allow_trailing_empty=True)
    return _resolve_empty_holds(tokens)


def _tokenize_row(row: List[Run]) -> List[str]:
    return [tok for tok, _ in _tokenize_row_anchored(row)]


def _is_solfa_beat(tok: str) -> bool:
    if tok == "BAR":
        return False
    parts = tok.split(".")
    if not parts:
        return False
    for raw in parts:
        cell = raw.strip()
        if cell in ("", "-", "_"):
            continue
        m = _SYLLABLE_RE.match(cell)
        if not m or m.group(1).lower() not in _VALID_CORES:
            return False
    return True


def row_to_measures(row: List[Run], *, use_implicit_bars: bool = True) -> List[List[str]]:
    """Voix -> liste de mesures (chaque mesure = liste de temps)."""
    return [beats for _, beats in row_to_measures_anchored(row)]


def row_to_measures_anchored(row: List[Run]) -> List[Tuple[float, List[str]]]:
    """Voix -> [(x_début, temps), ...] pour aligner les voix d'un système."""
    tokens = _tokenize_row_anchored(row)
    measures: List[Tuple[float, List[str]]] = []
    current: List[str] = []
    start_x: Optional[float] = None

    for tok, x in tokens:
        if tok == "BAR":
            if current and start_x is not None:
                measures.append((start_x, current))
                current = []
                start_x = None
            continue
        if not _is_solfa_beat(tok):
            continue
        if start_x is None:
            start_x = x
        current.append(tok)
    if current and start_x is not None:
        measures.append((start_x, current))
    return measures


def coalesce_to_meter(
    measures: List[List[str]], beats_per_measure: int
) -> List[List[str]]:
    """Regroupe des demi-mesures pour atteindre la signature (ex. 2+2 → 4/4)."""
    anchored = coalesce_anchored([(0.0, m) for m in measures], beats_per_measure)
    return [beats for _, beats in anchored]


def coalesce_anchored(
    measures: List[Tuple[float, List[str]]], beats_per_measure: int
) -> List[Tuple[float, List[str]]]:
    """Comme coalesce_to_meter, en conservant le x du premier temps de chaque mesure."""
    if beats_per_measure <= 0 or not measures:
        return measures
    if len(measures[0][1]) >= beats_per_measure:
        return measures
    out: List[Tuple[float, List[str]]] = []
    buf: List[str] = []
    buf_xs: List[float] = []
    for x, bar in measures:
        for beat in bar:
            buf.append(beat)
            buf_xs.append(x)
            while len(buf) >= beats_per_measure:
                out.append((buf_xs[0], buf[:beats_per_measure]))
                buf = buf[beats_per_measure:]
                buf_xs = buf_xs[beats_per_measure:]
    if buf:
        out.append((buf_xs[0], buf))
    return out


def _group_systems(
    voice_rows: List[List[Run]], *, y_descending: bool = True,
    system_gap: float = _SYSTEM_GAP,
) -> List[List[List[Run]]]:
    systems: List[List[List[Run]]] = []
    cur: List[List[Run]] = []
    prev_y: Optional[float] = None
    for row in voice_rows:
        y = _row_y(row)
        if prev_y is not None:
            delta = (prev_y - y) if y_descending else (y - prev_y)
            if delta > system_gap:
                systems.append(cur)
                cur = []
        cur.append(row)
        prev_y = y
    if cur:
        systems.append(cur)
    return systems


def _adaptive_system_gap(voice_rows: List[List[Run]]) -> Optional[float]:
    """Seuil de séparation des systèmes déduit de la PÉRIODICITÉ des écarts y.

    Dans un recueil SATB dense, l'écart inter-systèmes (basse → soprano suivant)
    est proche de l'écart intra-système : un seuil fixe échoue. On détecte la
    période p (voix par système) qui maximise le contraste (écart moyen aux
    frontières − écart moyen à l'intérieur), puis on place le seuil entre le plus
    grand écart intérieur et le plus petit écart-frontière. Renvoie None si aucune
    périodicité nette (→ repli sur le seuil fixe)."""
    n = len(voice_rows)
    if n < 4:
        return None
    ys = [_row_y(r) for r in voice_rows]
    gaps = [abs(ys[i] - ys[i - 1]) for i in range(1, n)]
    best_p: Optional[int] = None
    best_score = 0.0
    for p in range(2, 7):
        if p >= n or n % p != 0 or n // p < 2:
            continue
        bidx = set(range(p - 1, n - 1, p))
        b = [g for i, g in enumerate(gaps) if i in bidx]
        inter = [g for i, g in enumerate(gaps) if i not in bidx]
        if not b or not inter:
            continue
        score = sum(b) / len(b) - sum(inter) / len(inter)
        if score > best_score:
            best_score, best_p = score, p
    if best_p is None:
        return None
    bidx = set(range(best_p - 1, n - 1, best_p))
    b = [g for i, g in enumerate(gaps) if i in bidx]
    inter = [g for i, g in enumerate(gaps) if i not in bidx]
    # Frontières franchement plus grandes : sinon (chevauchement) exiger au moins
    # que la frontière moyenne domine l'intérieur, sans quoi le seuil est douteux.
    if min(b) <= max(inter) and sum(b) / len(b) <= 1.2 * (sum(inter) / len(inter)):
        return None
    return (max(inter) + min(b)) / 2.0


def _infer_n_voices(systems: List[List[List[Run]]]) -> int:
    sizes = [len(s) for s in systems if len(s) >= 2]
    if not sizes:
        return len(systems[0]) if systems else 0
    return Counter(sizes).most_common(1)[0][0]


def _rest_measure(beats: int) -> List[str]:
    return [""] * max(beats, 1)


def _normalize_measure_beats(measure: List[str], beats: int) -> List[str]:
    """Chaque mesure doit avoir exactement ``beats`` temps (sinon le parseur décale).

    Les temps manquants prolongent la dernière note (``-``), sauf mesure
    silencieuse où l'on pad avec des silences vides — ne jamais transformer
    une blanche / blanche pointée en silences.
    """
    if beats <= 0:
        return measure
    out = list(measure)
    if len(out) > beats:
        out = out[:beats]
    if len(out) >= beats:
        return out

    sounding = any(_is_pitched_beat(b) or b.strip() == "-" for b in out)
    last = out[-1].strip() if out else ""
    if sounding and last != "":
        pad = "-"
    else:
        pad = ""
    while len(out) < beats:
        out.append(pad)
    return out


def _normalize_voice_beats(
    measures: List[List[str]], beats: int
) -> List[List[str]]:
    return [_normalize_measure_beats(m, beats) for m in measures]


def _midbar_xs(system: List[List[Run]]) -> List[float]:
    xs: List[float] = []
    for row in system:
        for run in merge_close_glyphs(row):
            if run.text.strip() == _BAR_CHAR:
                xs.append(run.x)
    if not xs:
        return []
    xs.sort()
    clustered: List[float] = []
    for x in xs:
        if not clustered or abs(x - clustered[-1]) > 20.0:
            clustered.append(x)
        else:
            clustered[-1] = (clustered[-1] + x) / 2.0
    return clustered


def _system_grid(system: List[List[Run]]) -> Tuple[float, float, int]:
    """Origine x, largeur de mesure, nombre de colonnes estimé."""
    mids = _midbar_xs(system)
    if len(mids) >= 2:
        gaps = [b - a for a, b in zip(mids, mids[1:])]
        # Largeur = plus petit écart ≈ 1 mesure (les trous 2× sont des midbars manquants).
        unit = min(gaps)
        width = unit
        # Si un écart ≈ 2×unit, midbar manquant.
        n_from_mids = 1
        for g in gaps:
            n_from_mids += max(1, int(round(g / unit)))
        origin = mids[0] - width / 2.0
        return origin, width, n_from_mids
    # Repli : emprise horizontale des glyphes.
    xs = [run.x for row in system for run in row]
    if not xs:
        return 0.0, 160.0, 1
    return min(xs), 160.0, 1


def _measure_col(x: float, origin: float, width: float) -> int:
    if width <= 0:
        return 0
    return max(0, int((x - origin) / width))


def _pad_system_voices(
    raw: List[List[List[str]]], n_voices: int, beats: int
) -> List[List[List[str]]]:
    """Aligne les voix d'un système (même nombre de mesures, voix manquantes = silences)."""
    rest = _rest_measure(beats)
    while len(raw) < n_voices:
        raw.append([])
    n_bars = max((len(m) for m in raw), default=0)
    for v in range(n_voices):
        while len(raw[v]) < n_bars:
            raw[v].append(list(rest))
    return raw[:n_voices]


def _is_rest_only(measure: List[str]) -> bool:
    return all(b.strip() in ("", "-") for b in measure)


def _align_system_by_x(
    anchored: List[List[Tuple[float, List[str]]]],
    system: List[List[Run]],
    n_voices: int,
    beats: int,
) -> List[List[List[str]]]:
    """Place les mesures sur une grille x (silences si une voix entre en retard).

    Un trou de colonnes n'est créé qu'après une mesure déjà silencieuse : ainsi
    une entrée tardive (soprano qui reprend à droite) reste calée, sans décaler
    une voix qui enchaîne juste après une anacrouse.
    """
    origin, width, n_cols_hint = _system_grid(system)
    rest = _rest_measure(beats)

    while len(anchored) < n_voices:
        anchored.append([])

    grids: List[dict[int, List[str]]] = []
    max_col = n_cols_hint - 1

    for ms in anchored[:n_voices]:
        grid: dict[int, List[str]] = {}
        if not ms:
            # Voix absente ou grille de silences sans ancre : remplir plus bas.
            grids.append(grid)
            continue
        prev_col = -1
        for x, bar in ms:
            col = _measure_col(x, origin, width)
            if prev_col >= 0 and col <= prev_col:
                col = prev_col + 1
            elif prev_col >= 0 and col > prev_col + 1:
                if not _is_rest_only(grid[prev_col]):
                    col = prev_col + 1
            while col in grid:
                col += 1
            grid[col] = list(bar)
            prev_col = col
            max_col = max(max_col, col)
        grids.append(grid)

    n_cols = max(max_col + 1, 1)
    out: List[List[List[str]]] = []
    for grid in grids:
        row = [list(rest) for _ in range(n_cols)]
        for col, bar in grid.items():
            if 0 <= col < n_cols:
                row[col] = bar
        out.append(row)

    return _pad_system_voices(out, n_voices, beats)


def _is_anacrusis_beat(tok: str) -> bool:
    """Temps d'anacrouse « .m » (silence + note), pas « -.m » (tenue + note)."""
    t = tok.strip()
    return t.startswith(".") and not t.startswith("-.") and any(c.isalpha() for c in t)


def _split_mashed_anacrusis(
    measures: List[List[str]], beats: int
) -> List[List[str]]:
    """« .m m -.m m.m » (levée collée à la mesure suivante) → repose + corps.

    Les voix qui entrent à la levée n'ont souvent pas les silences du début de
    mesure : le coalesce fusionne alors ``.m`` avec les 3 temps suivants.
    """
    if beats <= 0 or not measures:
        return measures
    first = list(measures[0])
    if len(first) != beats or not _is_anacrusis_beat(first[0]):
        return measures
    if not any(_is_pitched_beat(b) for b in first[1:]):
        return measures
    lead = [""] * (beats - 1) + [first[0]]
    body = _normalize_measure_beats(first[1:], beats)
    return [lead, body] + [list(m) for m in measures[1:]]


def _absorb_leading_rest_anacrusis(
    measures: List[List[str]], beats: int
) -> List[List[str]]:
    """« silences | .m : … » → « silences… .m | … » (anacrouse sur le dernier temps)."""
    if beats <= 0 or len(measures) < 2:
        return measures
    out = [list(m) for m in measures]
    while (
        len(out) >= 2
        and _is_rest_only(out[0])
        and out[1]
        and _is_anacrusis_beat(out[1][0])
    ):
        pickup = out[1][0]
        out[0] = _normalize_measure_beats(out[0][:-1] + [pickup], beats)
        out[1] = out[1][1:]
        if not out[1]:
            out.pop(1)
        else:
            out[1] = _normalize_measure_beats(out[1], beats)
            break
    return out


def _split_mashed_anacrusis_anchored(
    anchored: List[Tuple[float, List[str]]],
    beats: int,
    origin: float,
    width: float,
) -> List[Tuple[float, List[str]]]:
    """Comme ``_split_mashed_anacrusis``, seulement si la voix entre en retard (col>0)."""
    if not anchored:
        return anchored
    x0, first = anchored[0]
    if _measure_col(x0, origin, width) == 0:
        return anchored
    split = _split_mashed_anacrusis([first], beats)
    if len(split) == 1:
        return anchored
    return [(x0, split[0]), (x0, split[1])] + list(anchored[1:])


def _prepare_voice_measures(
    measures: List[List[str]], beats: int
) -> List[List[str]]:
    """Normalise durées + anacrouses (sans re-splitter les mesures déjà calées)."""
    out = [_normalize_measure_beats(m, beats) for m in measures]
    out = _absorb_leading_rest_anacrusis(out, beats)
    return out


def _measures_to_notation(measures: List[List[str]]) -> str:
    bars = [" : ".join(beats) for beats in measures if beats is not None]
    return " | ".join(bars)


# --------------------------------------------------------------------------
# Chemin « grille régulière » (partitions type lord-bless)
#
# Certaines partitions (ex. John Rutter arrangé) ont :
#   - une barre de mesure INVISIBLE (glyphe épais non extrait) ;
#   - un séparateur de mi-mesure « | » (fin, extrait) ;
#   - des temps RÉGULIÈREMENT espacés (grille en x).
# Ni les barres ni les gros écarts ne délimitent les mesures : on reconstruit
# une grille de colonnes à pas constant, on place chaque temps par sa position
# x (les voix s'alignent verticalement), puis on découpe en mesures de `beats`.
# Robuste aux séparateurs manquants (ex. le « : » absent de la mesure 3).
# --------------------------------------------------------------------------

def _has_pipe_voice_rows(voice_rows: List[List[Run]]) -> bool:
    return any(_BAR_CHAR in _row_text(r) for r in voice_rows)


def _content_beats(row: List[Run]) -> Tuple[List[Tuple[float, str]], List[float]]:
    """(temps ayant du contenu [(x, jeton)], positions x des séparateurs)."""
    beats: List[Tuple[float, str]] = []
    seps: List[float] = []
    for run in merge_close_glyphs(row):
        buf = ""
        buf_x: Optional[float] = None
        for ch in run.text:
            if ch in _SEP_CHARS or ch == _BAR_CHAR:
                if buf.strip():
                    beats.append((buf_x if buf_x is not None else run.x, buf.strip()))
                buf, buf_x = "", None
                seps.append(run.x)
            elif ch == " ":
                if buf.strip():
                    beats.append((buf_x if buf_x is not None else run.x, buf.strip()))
                buf, buf_x = "", None
            else:
                if buf_x is None:
                    buf_x = run.x
                buf += ch
        if buf.strip():
            beats.append((buf_x if buf_x is not None else run.x, buf.strip()))
    return beats, seps


def _cluster_xs(xs: List[float], tol: float = 10.0) -> List[float]:
    xs = sorted(xs)
    out: List[List[float]] = []
    for x in xs:
        if out and x - out[-1][-1] <= tol:
            out[-1].append(x)
        else:
            out.append([x])
    return [sum(c) / len(c) for c in out]


def _grid_system(
    system: List[List[Run]], n_voices: int, beats: int
) -> List[List[List[str]]]:
    """Un système -> mesures par voix, via la grille x régulière."""
    per_voice: List[List[Tuple[float, str]]] = []
    all_seps: List[float] = []
    all_pipes: List[float] = []
    all_content_x: List[float] = []
    for v in range(n_voices):
        bts, sps = _content_beats(system[v]) if v < len(system) else ([], [])
        per_voice.append(bts)
        all_seps += sps
        all_content_x += [x for x, _ in bts]
        if v < len(system):
            all_pipes += [run.x for run in merge_close_glyphs(system[v]) if _BAR_CHAR in run.text]

    pipe_cols = _cluster_xs(all_pipes, tol=14.0)
    pipe_gaps = [b - a for a, b in zip(pipe_cols, pipe_cols[1:])]

    if len(pipe_cols) >= 2 and pipe_gaps:
        # Les « | » extraits sont les séparateurs de mi-mesure, espacés d'une
        # mesure entière (la vraie barre, épaisse, n'est pas extraite). D'où :
        # largeur de temps = espacement_| / beats.
        measure_w = statistics.median(pipe_gaps)
        width = measure_w / beats
        # Origine via la PHASE modulaire des « | » (robuste à un « | » parasite
        # isolé qui décalerait l'origine s'il servait de référence).
        phase = statistics.median([px % measure_w for px in pipe_cols])
        origin = phase - (beats // 2) * width
        # (Pas de recalage sur le contenu : dans une intro, le contenu le plus à
        # gauche peut être en mesure 1, pas 0 — seule la phase des « | » situe la grille.)
    else:
        sep_cols = _cluster_xs(all_seps)
        gaps = [b - a for a, b in zip(sep_cols, sep_cols[1:])]
        width = statistics.median(gaps) if gaps else 41.0
        origin = (min(sep_cols) - width) if sep_cols else (min(all_content_x) if all_content_x else 0.0)
        if all_content_x and width > 0:
            span = max(all_content_x) - origin
            n = max(1, round(span / width))
            width = span / n

    max_idx = 0
    grids: List[dict] = []
    for bts in per_voice:
        grid: dict = {}
        for x, tok in bts:
            cell = "-" if tok == "_" else tok
            # Écarte les paroles mêlées au sol-fa (même police/ligne).
            if not _is_solfa_beat(cell):
                continue
            # Case contenant x : le contenu est calé à gauche de sa case, d'où
            # le -0.5 (équivaut à un floor robuste aux frontières).
            idx = max(0, round((x - origin) / width - 0.5)) if width > 0 else 0
            while idx in grid:
                idx += 1
            grid[idx] = cell
            max_idx = max(max_idx, idx)
        grids.append(grid)

    n_cols = ((max_idx + 1 + beats - 1) // beats) * beats
    out: List[List[List[str]]] = []
    for grid in grids:
        cells = [grid.get(i, "") for i in range(n_cols)]
        out.append([cells[i : i + beats] for i in range(0, n_cols, beats)])
    return out


def _trim_trailing_rests(
    voices_measures: List[List[List[str]]],
) -> List[List[List[str]]]:
    """Retire les mesures finales entièrement silencieuses sur TOUTES les voix."""
    if not voices_measures:
        return voices_measures
    n = min(len(v) for v in voices_measures)
    while n > 1 and all(_is_rest_only(v[n - 1]) for v in voices_measures):
        n -= 1
    return [v[:n] for v in voices_measures]


def _build_grid(
    systems: List[List[List[Run]]], n_voices: int, beats: int
) -> List[List[List[str]]]:
    voices_measures: List[List[List[str]]] = [[] for _ in range(n_voices)]
    for system in systems:
        for v, measures in enumerate(_grid_system(system, n_voices, beats)):
            voices_measures[v].extend(measures)
    return _trim_trailing_rests(voices_measures)


# Normalisation des confusions de caractères propres à l'OCR (PaddleOCR) sur le
# sol-fa scanné — corrections SÛRES (aucune ambiguïté dans ce corpus) :
#   - variantes de tiret unicode (− U+2212, – U+2013, — U+2014) → '-' (tenue) ;
#   - chiffre '1' → lettre 'l' (la syllabe basse « l, » lue « 1, »).
# '1' n'apparaît jamais légitimement dans une ligne de VOIX (la mesure vit dans
# l'en-tête, parsé à part) → mapping sans risque ici.
_OCR_DASHES = {ord("−"): "-", ord("–"): "-", ord("—"): "-"}
# 2+ virgules de suite : l'OCR a collé la marque d'octave grave (un seul ',' est
# légitime) avec un ',' de quart de temps. Sans correction, 'd,,' = d DEUX octaves
# plus bas (valeur absurde, interdite en composition — CLAUDE.md). On **cap à une
# seule** virgule d'octave (`,,`→`,`) : ça supprime l'octave absurde sans
# fragmenter le temps en silences parasites. Une note réellement non lue est déjà
# gérée en amont par la dégradation (→ silence).
_MULTI_COMMA_RE = re.compile(r",{2,}")
# Une tenue '-' est une note tenue d'AU MOINS un demi-temps ; elle ne se colle
# jamais directement à une note (« d,- » est invalide). Collée à une syllabe,
# c'est le signe d'un ':' de temps mangé par l'OCR (GT « d,:-.l, » lu « d,-.l, »),
# qui décale toute la voix. On rétablit le ':' → un nouveau temps commence sur la
# tenue. (Une tenue précédée d'un '.' — « d.- » — reste un demi-temps valide.)
_GLUED_HOLD_RE = re.compile(r"(?<=[A-Za-z',_])-")


def _norm_ocr_solfa(text: str) -> str:
    t = text.translate(_OCR_DASHES).replace("1", "l")
    t = _MULTI_COMMA_RE.sub(",", t)
    return _GLUED_HOLD_RE.sub(":-", t)


def _beat_fits(beat: str) -> bool:
    """Le contenu tient-il en UN temps (pas de sur-subdivision) ?"""
    try:
        _parse_beat(beat, DIVISIONS_PER_BEAT, lenient=True)
        return True
    except LexError:
        return False


def _rebeat_crammed(beat: str) -> List[str]:
    """Découpe un temps **sur-chargé** (OCR ayant mangé un ``:`` → deux temps
    collés, ex. ``l, . t, d , t,``) en sous-temps, en coupant sur les espaces qui
    séparent deux NOTES complètes — jamais une sous-division ``.``/``,``/``-``.

    Préserve les octaves graves (le ``,`` de sous-division n'est pas recollé à la
    syllabe précédente). Cf. Alto/Basse, saturées de temps courts en octave grave."""
    frags = beat.split()
    if len(frags) <= 1:
        return [beat.strip()] if beat.strip() else []
    subs: List[str] = []
    cur = [frags[0]]
    for prev, f in zip(frags, frags[1:]):
        prev_complete = prev[-1:] not in (".", "-") and not all(c in ".,-" for c in prev)
        f_note_start = f[:1] not in (".", ",", "-")
        if prev_complete and f_note_start:
            subs.append(" ".join(cur))
            cur = [f]
        else:
            cur.append(f)
    subs.append(" ".join(cur))
    return subs


def _flatten_beats(segs: List[Run]) -> List[str]:
    """Segments (ordonnés x) d'une voix → liste **plate de temps**.

    On éclate sur ``:`` ET ``|`` : la distinction temps/barre de l'OCR n'est pas
    fiable (``:``↔``|`` fréquents), donc on l'ignore et le re-barrage se fait
    ensuite au mètre connu (voir ``_rebar``).

    Les temps VIDES **internes** (``d : - :  : m,.f,``) sont des **silences** : on
    les conserve (indispensable pour ne pas décaler le compte de temps). On ne
    supprime que les vides de **bord** de segment (artefacts de la coupure OCR :
    un segment commençant/finissant par ``:`` double le séparateur voisin).

    Un temps sur-chargé (OCR ayant fusionné deux temps) est **re-découpé** plutôt
    que dégradé plus loin en silence — récupère les notes perdues (Alto/Basse)."""
    beats: List[str] = []
    for s in segs:
        txt = _norm_ocr_solfa(s.text).replace(_BAR_CHAR, ":")
        parts = [p.strip() for p in txt.split(":")]
        while parts and parts[0] == "":
            parts.pop(0)
        while parts and parts[-1] == "":
            parts.pop()
        for p in parts:
            if p == "" or _beat_fits(p):
                beats.append(p)          # temps valide (ou silence interne)
            else:
                beats.extend(_rebeat_crammed(p))   # sur-chargé → sous-temps
    return beats


def _detect_anacrusis(first_system: List[List[Run]], beats: int) -> int:
    """Longueur de la levée = plus petit nb de temps du 1er segment des voix.

    La voix la plus « propre » (levée isolée dans un segment séparé, ex. soprano
    ``m, . f,``) donne la vraie levée ; les voix où la levée est collée au 1er
    temps donnent un compte plus grand → on prend le minimum. 0 si pas de levée
    nette (segment plein ou ambigu)."""
    counts: List[int] = []
    for voice_row in first_system:
        segs = sorted(voice_row, key=lambda r: r.x)
        if not segs:
            continue
        first = _norm_ocr_solfa(segs[0].text).replace(_BAR_CHAR, ":")
        n = len([b for b in first.split(":") if b.strip()])
        if n:
            counts.append(n)
    if not counts:
        return 0
    a = min(counts)
    return a if 0 < a < beats else 0


def _rebar(beats_flat: List[str], beats: int, anacrusis: int) -> str:
    """Re-barre une liste plate de temps **au mètre connu** (barre tous les
    ``beats``), immunisant le découpage en mesures contre les barres/temps mal
    lus par l'OCR. La levée est complétée en tête par des silences → 1re mesure
    pleine, ce qui aligne les temps forts suivants."""
    if not beats_flat:
        return ""
    measures: List[List[str]] = []
    i = 0
    if 0 < anacrusis < beats:
        measures.append([""] * (beats - anacrusis) + beats_flat[:anacrusis])
        i = anacrusis
    while i < len(beats_flat):
        measures.append(beats_flat[i:i + beats])
        i += beats
    return " | ".join(" : ".join(m) for m in measures)


def _build_document_from_lines(runs: List[Run]) -> SolfaDocument:
    """Chemin PaddleOCR : runs = **segments de ligne** (une phrase par boîte).

    L'OCR lit bien les syllabes mais mal les micro-séparateurs (``.``↔``,``,
    ``:``↔``|``). On ne fait donc PAS confiance aux barres/temps de l'OCR pour la
    structure : on **aplatit chaque voix en liste de temps** puis on **re-barre au
    mètre connu** (``_rebar``), avec la levée en mesure implicite. Le lexer
    (``parse_solfa``, insensible aux espaces) résout ensuite hauteurs et durées.
    """
    clustered = _cluster_rows(runs)
    rows, y_descending = _orient_rows(clustered)
    header = parse_header(rows)

    voice_rows = [r for r in rows if _is_voice_row(r)]
    # Systèmes SATB denses : seuil adaptatif par périodicité des écarts y
    # (le seuil fixe ne discrimine pas frontière-système vs écart inter-voix).
    sys_gap = _adaptive_system_gap(voice_rows)
    if sys_gap is None:
        sys_gap = _SYSTEM_GAP
    systems = _group_systems(voice_rows, y_descending=y_descending, system_gap=sys_gap)
    if not systems:
        raise ValueError("aucune ligne de voix détectée dans le PDF")
    n_voices = _infer_n_voices(systems)
    if n_voices <= 0:
        raise ValueError("aucune voix exploitable dans le PDF")

    beats = header.beats or 4
    anacrusis = _detect_anacrusis(systems[0], beats)

    voice_beats: List[List[str]] = [[] for _ in range(n_voices)]
    for system in systems:
        for v in range(n_voices):
            if v < len(system):
                voice_beats[v].extend(
                    _flatten_beats(sorted(system[v], key=lambda r: r.x))
                )
    voices = [_rebar(vb, beats, anacrusis) for vb in voice_beats]
    names = list(_SATB) if n_voices == 4 else [f"Voix {i + 1}" for i in range(n_voices)]
    return SolfaDocument(header=header, voices=voices, voice_names=names)


def build_document(runs: List[Run]) -> SolfaDocument:
    # PaddleOCR rend des segments de ligne (font "paddle") : chemin dédié
    # concaténation + lexer, au lieu du tokenizer glyphe sensible aux espaces.
    if any(r.font == "paddle" for r in runs):
        return _build_document_from_lines(runs)

    clustered = _cluster_rows(runs)
    rows, y_descending = _orient_rows(clustered)
    header = parse_header(rows)

    voice_rows = [r for r in rows if _is_voice_row(r)]
    systems = _group_systems(voice_rows, y_descending=y_descending)
    if not systems:
        raise ValueError("aucune ligne de voix détectée dans le PDF")

    n_voices = _infer_n_voices(systems)
    if n_voices <= 0:
        raise ValueError("aucune voix exploitable dans le PDF")

    # Partitions à grille régulière (barre invisible, mi-mesure « | ») :
    # segmentation par colonnes x + mètre, plutôt que par gros écarts.
    if _has_pipe_voice_rows(voice_rows):
        beats = header.beats or 4
        grid_voices = _build_grid(systems, n_voices, beats)
        voices = [_measures_to_notation(m) for m in grid_voices]
        names = list(_SATB) if n_voices == 4 else [f"Voix {i + 1}" for i in range(n_voices)]
        return SolfaDocument(header=header, voices=voices, voice_names=names)

    voices_measures: List[List[List[str]]] = [[] for _ in range(n_voices)]
    for system in systems:
        anchored = [
            row_to_measures_anchored(system[v])
            for v in range(min(n_voices, len(system)))
        ]
        beats = header.beats or 4
        if header.beats:
            anchored = [coalesce_anchored(m, header.beats) for m in anchored]
        origin, width, _ = _system_grid(system)
        anchored = [
            _split_mashed_anacrusis_anchored(m, beats, origin, width) for m in anchored
        ]

        if len(system) == 1 and n_voices > 1:
            # Intro / section monodique (Soprano) : autres voix en silences.
            sop = _prepare_voice_measures(
                [beats_list for _, beats_list in anchored[0]], beats
            )
            voices_measures[0].extend(sop)
            rest = _rest_measure(beats)
            for v in range(1, n_voices):
                voices_measures[v].extend([list(rest) for _ in sop])
            continue

        raw = _align_system_by_x(anchored, system, n_voices, beats)
        for v, measures in enumerate(raw):
            voices_measures[v].extend(_prepare_voice_measures(measures, beats))

    voices = [
        _measures_to_notation(_prepare_voice_measures(m, header.beats or 4))
        for m in voices_measures
    ]
    names = list(_SATB) if n_voices == 4 else [f"Voix {i + 1}" for i in range(n_voices)]
    return SolfaDocument(header=header, voices=voices, voice_names=names)
