"""Lecture d'un PDF (ou image) de partition sol-fa tonique.

- PDF *typographié* (texte + polices) : décodage ToUnicode, sans OCR.
- PDF *scanné* / image : rendu → OpenCV → bandes (projection) → Tesseract
  PSM 7 → correcteur glyphe/rythme → ``layout`` → notation
  ``packages/shared-contracts/solfa-format.md``.
"""
from .document import pdf_to_score, pdf_to_document, PdfSolfaError

__all__ = ["pdf_to_score", "pdf_to_document", "PdfSolfaError"]
