"""Lecture de lignes sol-fa via TrOCR (Microsoft Vision Transformer).

Remplace Tesseract pour la lecture par bande. TrOCR est un modèle seq2seq
(ViT encoder + GPT-2 decoder) pré-entraîné sur du texte imprimé, beaucoup
plus robuste que Tesseract sur les petits caractères et la ponctuation.

Usage :
  - ``trocr_available()`` : True si transformers + torch sont installés.
  - ``TrOCRLineReader`` : lit une bande (image) → texte.
  - ``trocr_ocr_bands()`` : pipeline complet bande par bande → ``Run``.
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from .extract import Run


def trocr_available() -> bool:
    try:
        import torch  # noqa: F401
        from transformers import TrOCRProcessor  # noqa: F401
        from transformers import VisionEncoderDecoderModel  # noqa: F401

        return True
    except ImportError:
        return False


class TrOCRLineReader:
    """Lit une ligne de texte (image bande) via TrOCR.

    Charge le modèle au premier appel (lazy loading).
    Modèle par défaut : ``microsoft/trocr-base-printed``.
    """

    def __init__(self, model_name: str = "microsoft/trocr-small-printed"):
        self._model_name = model_name
        self._processor: Optional[Any] = None
        self._model: Optional[Any] = None

    def _load(self):
        if self._processor is None:
            from transformers import (
                TrOCRProcessor,
                ViTImageProcessor,
                VisionEncoderDecoderModel,
                XLMRobertaTokenizer,
            )

            image_processor = ViTImageProcessor.from_pretrained(self._model_name)
            tokenizer = XLMRobertaTokenizer.from_pretrained(self._model_name)
            self._processor = TrOCRProcessor(
                image_processor=image_processor, tokenizer=tokenizer
            )
            self._model = VisionEncoderDecoderModel.from_pretrained(
                self._model_name
            )
            self._model.eval()

    def read_line(self, image) -> str:
        """Lit une image de bande → chaîne de texte.

        ``image`` : PIL Image, ou numpy array (RGB ou grayscale).
        """
        import torch
        from PIL import Image as PILImage
        import numpy as np

        self._load()

        if isinstance(image, np.ndarray):
            if len(image.shape) == 2:
                # Grayscale → RGB.
                image = np.stack([image, image, image], axis=-1)
            image = PILImage.fromarray(image)

        pixel_values = self._processor(
            images=image, return_tensors="pt"
        ).pixel_values
        with torch.no_grad():
            generated_ids = self._model.generate(pixel_values, max_new_tokens=256)
        text = self._processor.batch_decode(
            generated_ids, skip_special_tokens=True
        )[0]
        return text.strip()


def _split_trocr_text(text: str) -> List[str]:
    """Découpe le texte lu par TrOCR en tokens sol-fa individuels.

    TrOCR retourne une chaîne comme ``"d : r . m : f | s"``
    qu'on doit éclater en tokens isolés.
    """
    # Garde les séparateurs comme tokens individuels.
    tokens = re.findall(
        r"[a-zA-Z]+[',_]*|[:|!.]|[,\-]|\S+",
        text,
    )
    return [t for t in tokens if t.strip()]


def trocr_ocr_bands(
    bgr,
    *,
    reader: Optional[TrOCRLineReader] = None,
    y_offset: float = 0.0,
    margin: int = 6,
) -> List[Run]:
    """Pipeline TrOCR complet : bandes → texte → ``Run``.

    Utilise la segmentation par bandes existante (``detect_voice_bands``),
    puis lit chaque bande avec TrOCR au lieu de Tesseract.
    """
    from .ocr import detect_voice_bands, preprocess_image
    import numpy as np

    if reader is None:
        reader = TrOCRLineReader()

    binary = preprocess_image(bgr)
    page_h = float(binary.shape[0])

    if binary.shape[0] < 200:
        # Image trop courte pour le découpage en bandes.
        text = reader.read_line(binary)
        return _text_to_runs(text, page_h=page_h, y_center=page_h / 2, y_offset=y_offset)

    bands = detect_voice_bands(
        binary, min_gap=6, min_height=10, max_height=48, density=0.015
    )
    if not bands:
        text = reader.read_line(binary)
        return _text_to_runs(text, page_h=page_h, y_center=page_h / 2, y_offset=y_offset)

    runs: List[Run] = []
    for y_start, y_end in bands:
        if (y_end - y_start) < 10:
            continue
        top = max(0, y_start - margin)
        bottom = min(binary.shape[0], y_end + margin)
        strip = binary[top:bottom, :]
        if strip.shape[0] < 12 or strip.shape[1] < 20:
            continue
        # Pad vertical pour TrOCR si trop petit.
        if strip.shape[0] < 32:
            pad = 32 - strip.shape[0]
            strip = np.pad(
                strip,
                ((pad // 2, pad - pad // 2), (0, 0)),
                mode="constant",
                constant_values=255,
            )
        text = reader.read_line(strip)
        y_center = (y_start + y_end) / 2.0
        band_runs = _text_to_runs(
            text, page_h=page_h, y_center=y_center, y_offset=y_offset,
            strip_width=float(strip.shape[1]),
        )
        runs.extend(band_runs)

    return runs


def _text_to_runs(
    text: str,
    *,
    page_h: float,
    y_center: float,
    y_offset: float = 0.0,
    strip_width: float = 900.0,
    x_start: float = 40.0,
) -> List[Run]:
    """Convertit le texte TrOCR d'une bande en ``Run`` avec positions estimées.

    Les positions x sont réparties proportionnellement sur la largeur.
    Le y est fixé au centre de la bande (inversé en PDF-like).
    """
    tokens = _split_trocr_text(text)
    if not tokens:
        return []

    pdf_y = y_offset + (page_h - y_center)

    # Répartir les tokens sur la largeur de la bande.
    usable_width = strip_width - 2 * x_start
    step = usable_width / max(1, len(tokens))

    runs: List[Run] = []
    for i, tok in enumerate(tokens):
        x = x_start + i * step
        runs.append(Run(y=round(pdf_y, 1), x=round(x, 1), font="trocr", text=tok))
    return runs
