"""Pipeline Connected Components : segmentation par bande → composantes connexes → classifieur.

Alternative au pipeline YOLO quand le modèle n'est pas entraîné. Chaque bande
est binarisée, puis les composantes connexes sont extraites et classifiées par
le template classifier (distance L2 contre glyphes synthétiques).

Avantage : fonctionne sans entraînement. Suffisant pour un alphabet de ~13 classes.
"""
from __future__ import annotations

from typing import List, Optional

from .classifier import (
    GlyphPrediction,
    TemplateGlyphClassifier,
    classify_band_glyphs,
    extract_connected_components,
    get_default_classifier,
)
from .extract import Run
from .ocr import detect_voice_bands, preprocess_image


def cc_ocr_page(
    bgr,
    *,
    y_offset: float = 0.0,
    margin: int = 6,
    conf_threshold: float = 0.3,
    classifier: Optional[TemplateGlyphClassifier] = None,
) -> List[Run]:
    """Pipeline CC complet : bandes → composantes connexes → classifieur → runs.

    Retourne une liste de ``Run`` (même contrat que le pipeline Tesseract).
    """
    if classifier is None:
        classifier = get_default_classifier()

    binary = preprocess_image(bgr)
    page_h = float(binary.shape[0])

    bands = detect_voice_bands(
        binary, min_gap=6, min_height=10, max_height=48, density=0.015
    )
    if not bands:
        return _cc_full_page(binary, page_h, y_offset, classifier, conf_threshold)

    runs: List[Run] = []
    for y_start, y_end in bands:
        if (y_end - y_start) < 10:
            continue
        top = max(0, y_start - margin)
        bottom = min(binary.shape[0], y_end + margin)
        strip = binary[top:bottom, :]
        if strip.shape[0] < 8 or strip.shape[1] < 20:
            continue

        preds = classify_band_glyphs(strip, classifier)
        for p in preds:
            if p.confidence < conf_threshold:
                continue
            # Convertir coordonnées image → PDF-like.
            img_y = float(top) + p.y + p.h / 2.0
            pdf_y = y_offset + (page_h - img_y)
            runs.append(
                Run(
                    y=round(pdf_y, 1),
                    x=round(float(p.x), 1),
                    font="cc",
                    text=p.label,
                )
            )

    return runs


def _cc_full_page(
    binary,
    page_h: float,
    y_offset: float,
    classifier: TemplateGlyphClassifier,
    conf_threshold: float,
) -> List[Run]:
    """Fallback : CC sur la page entière."""
    preds = classify_band_glyphs(binary, classifier)
    runs: List[Run] = []
    for p in preds:
        if p.confidence < conf_threshold:
            continue
        img_y = p.y + p.h / 2.0
        pdf_y = y_offset + (page_h - img_y)
        runs.append(
            Run(
                y=round(pdf_y, 1),
                x=round(float(p.x), 1),
                font="cc",
                text=p.label,
            )
        )
    return runs
