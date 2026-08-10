"""Correcteur post-OCR pour runs sol-fa (confusions glyphe + rythme).

Appliqué après ``ocr_to_runs`` / avant ``layout.build_document``.
Stdlib pure : pas de dépendance OCR. Les règles suivent
``packages/shared-contracts/solfa-format.md``.
"""
from __future__ import annotations

import re
from typing import List

from ..solfa.keys import CHROMATIC, DIATONIC
from .extract import Run

_VALID_CORES = set(DIATONIC) | set(CHROMATIC)

# Confusions Tesseract fréquentes en contexte sol-fa (token isolé).
_GLYPH_SUBS = {
    "5": "s",
    "S": "s",
    "L": "l",
    "I": "l",
    "0": "d",
    "O": "d",
    "o": "d",
    "}": "|",
    "]": "|",
    "{": "|",
    "[": "|",
    ";": ":",
    "i": "l",  # isolé seulement (chromatismes gérés à part)
}

_SYLLABLE_RE = re.compile(r"^([a-zA-Z0-9]+)([',_]*)$")


def _correct_token(text: str) -> str:
    """Corrige un token OCR isolé (syllabe ou séparateur)."""
    if not text:
        return text
    # Séparateurs / barres.
    if text in (":", "|", ".", ",", "-", "!", ";", "_", "}", "]", "{", "["):
        if text == ";":
            return ":"
        if text in ("}", "]", "{", "["):
            return "|"
        return text

    # Token entier = confusion isolée (ex. "5" → "s", "L" → "l").
    if len(text) == 1 and text in _GLYPH_SUBS:
        return _GLYPH_SUBS[text]

    # Syllabe avec octave : normaliser le noyau (sans toucher aux chromatismes).
    m = _SYLLABLE_RE.match(text)
    if m:
        core, marks = m.group(1), m.group(2)
        core_l = core.lower()
        if core_l in _VALID_CORES:
            return core_l + marks
        # Confusions dans le noyau (ex. "5," → "s,").
        for bad, good in (("5", "s"), ("0", "d"), ("1", "l"), ("S", "s"), ("L", "l")):
            if bad in core:
                cand = core.replace(bad, good).lower()
                if cand in _VALID_CORES:
                    return cand + marks
        return core_l + marks

    # Multi-caractères non-syllabe : uniquement ; → : et braces → |
    return (
        text.replace(";", ":")
        .replace("}", "|")
        .replace("]", "|")
        .replace("{", "|")
        .replace("[", "|")
    )


def _expand_glued_token(run: Run) -> List[Run]:
    """Éclate ``8l6.m:6.5|`` en runs séparés (syllabes + séparateurs).

    Tesseract PSM 7 colle souvent toute une mesure en un seul mot ; le layout
    a besoin de séparateurs isolés pour tokeniser.
    """
    text = run.text
    # Rien à faire si pas de séparateur embarqué au milieu.
    if not any(c in text for c in ":|!.") or len(text) <= 1:
        return [run]
    # Déjà un séparateur pur.
    if re.fullmatch(r"[:|!.\-,]+", text):
        return [run]

    parts = re.findall(r"[a-zA-Z0-9]+[',_]*|[:|!.]|[,]|-|[^:\s|.!,]+", text)
    if len(parts) <= 1:
        return [run]

    # Répartir les x approximativement sur la largeur du token.
    # Largeur estimée : ~8 px par caractère (OCR 300 dpi).
    char_w = max(4.0, 8.0)
    out: List[Run] = []
    x = float(run.x)
    for part in parts:
        if not part:
            continue
        out.append(Run(y=run.y, x=round(x, 1), font=run.font, text=part))
        x += len(part) * char_w + 2.0
    return out if out else [run]


def correct_glyph_runs(runs: List[Run]) -> List[Run]:
    """Couche 1 : confusions glyphe-à-glyphe + éclatement des tokens collés."""
    out: List[Run] = []
    for run in runs:
        for piece in _expand_glued_token(run):
            new_text = _correct_token(piece.text)
            if new_text != piece.text:
                out.append(Run(y=piece.y, x=piece.x, font=piece.font, text=new_text))
            else:
                out.append(piece)
    return out



def _collapse_repeated_seps(text: str) -> str:
    """``::::`` / ``||||`` impossibles → un seul séparateur."""
    text = re.sub(r":{2,}", ":", text)
    text = re.sub(r"\|{2,}", "|", text)
    text = re.sub(r"!{2,}", "!", text)
    return text


def _insert_missing_bars_in_row(row: List[Run], gap_tol: float = 80.0) -> List[Run]:
    """Insère un ``|`` si deux runs successifs sont séparés par un grand trou X.

    Ne s'applique que si la ligne contient déjà des séparateurs de temps
    (sinon ce n'est pas une ligne de voix).
    """
    if len(row) < 2:
        return row
    row_text = " ".join(r.text for r in row)
    if ":" not in row_text and "!" not in row_text:
        return row

    ordered = sorted(row, key=lambda r: r.x)
    out: List[Run] = [ordered[0]]
    for prev, cur in zip(ordered, ordered[1:]):
        gap = cur.x - prev.x
        # Grand trou + pas déjà une barre de part et d'autre.
        if (
            gap >= gap_tol
            and prev.text.strip() != "|"
            and cur.text.strip() != "|"
        ):
            mid_x = (prev.x + cur.x) / 2.0
            out.append(Run(y=prev.y, x=round(mid_x, 1), font=prev.font, text="|"))
        out.append(cur)
    return out


def _cluster_rows(runs: List[Run], y_tol: float = 6.0) -> List[List[Run]]:
    ordered = sorted(runs, key=lambda r: (-r.y, r.x))
    rows: List[List[Run]] = []
    cur: List[Run] = []
    cur_y = None
    for run in ordered:
        if cur_y is None or abs(run.y - cur_y) <= y_tol:
            cur.append(run)
            cur_y = run.y if cur_y is None else cur_y
        else:
            rows.append(cur)
            cur = [run]
            cur_y = run.y
    if cur:
        rows.append(cur)
    return rows


def correct_rhythm_runs(runs: List[Run]) -> List[Run]:
    """Couche 2 : automate rythmique (séparateurs répétés, barres manquantes)."""
    # Collapse dans le texte de chaque run.
    cleaned: List[Run] = []
    for run in runs:
        text = _collapse_repeated_seps(run.text)
        if text != run.text:
            cleaned.append(Run(y=run.y, x=run.x, font=run.font, text=text))
        else:
            cleaned.append(run)

    # Insérer barres manquantes par ligne.
    rows = _cluster_rows(cleaned)
    out: List[Run] = []
    for row in rows:
        out.extend(_insert_missing_bars_in_row(row))
    return out


def correct_ocr_runs(runs: List[Run]) -> List[Run]:
    """Pipeline complet de correction post-OCR."""
    return correct_rhythm_runs(correct_glyph_runs(runs))
