"""Détection du type de document PDF (architecture §6 — heuristique DET).

Distinction :
  - ``solfa_text``      : feuille sol-fa tonique malgache (glyphes d r m f…)
  - ``staff_notation``  : partition en portée / solfège occidental (PDF gravé)
  - ``scanned``         : image sans texte extractible (OCR ou OMR requis)
  - ``unknown``         : PDF avec texte mais sans ligne sol-fa reconnue
"""
from __future__ import annotations

from typing import Literal

from .extract import ExtractError, Run, extract_runs
from .layout import _cluster_rows, _is_voice_row, _orient_rows

PdfKind = Literal["solfa_text", "staff_notation", "scanned", "unknown"]

_STAFF_HINTS = (
    "satb", "soprano", "alto", "tenor", "bass", "choir", "keyboard",
    "words and music", "music by", "words by", "piano", "organ", "hymn",
    "arr.", "arranged", "copyright",
)


def classify_runs(runs: list[Run]) -> PdfKind:
    """Classifie des runs déjà extraits (texte ou OCR)."""
    if not runs:
        return "unknown"

    rows = _cluster_rows(runs)
    rows, _ = _orient_rows(rows)
    voice_rows = [r for r in rows if _is_voice_row(r)]
    if voice_rows:
        return "solfa_text"

    blob = " ".join(r.text for r in runs).lower()
    if any(h in blob for h in _STAFF_HINTS):
        return "staff_notation"

    if len(runs) >= 15:
        return "staff_notation"

    return "unknown"


def detect_pdf_kind(data: bytes) -> PdfKind:
    """Classifie un PDF sans OCR (chemin MusicXML / rejet explicite)."""
    if not data.startswith(b"%PDF"):
        raise ValueError("n'est pas un PDF")
    try:
        runs = extract_runs(data)
    except ExtractError:
        return "scanned"
    return classify_runs(runs)


def pdf_kind_message(kind: PdfKind) -> str:
    """Message d'erreur utilisateur selon le type détecté."""
    if kind == "staff_notation":
        return (
            "PDF en portée (solfège occidental) : la reconnaissance OMR (Audiveris) "
            "n'est pas encore disponible. Exportez la partition en MusicXML (.mxl) "
            "depuis MuseScore, Finale ou Sibelius, puis importez ce fichier."
        )
    if kind == "scanned":
        return (
            "PDF scanné (image sans texte embarqué). Pour une feuille sol-fa malgache, "
            "l'OCR (Tesseract) est requis — voir l'image Docker omr-service. "
            "Pour une partition en portée, la reconnaissance Audiveris sera nécessaire (à venir)."
        )
    if kind == "unknown":
        return (
            "PDF non reconnu comme feuille sol-fa tonique malgache. "
            "Si c'est une partition en portée, exportez-la en MusicXML (.mxl)."
        )
    return "PDF sol-fa tonique attendu."
