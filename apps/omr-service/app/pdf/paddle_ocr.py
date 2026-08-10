"""Lecteur PaddleOCR : PDF/image sol-fa scanné → runs de texte positionnés.

PaddleOCR (torch) lit le sol-fa scanné bien mieux que YOLO/Tesseract sur ces
recueils malgaches (titre, tonique « Do dia X », compositeur, paroles, ET les
syllabes sol-fa avec une précision ~élevée). Il rend des **segments de ligne**
(une phrase par boîte), coupés aux grands trous horizontaux ≈ barres de mesure.

Contrat de sortie identique à ``ocr.ocr_to_runs`` : liste de ``Run(y, x, font,
text)`` en **points** (72 dpi), Y inversé (croissant vers le haut, comme le
modèle PDF) — c'est ``layout.build_document`` qui reconstruit les voix.

Les runs sont marqués ``font="paddle"`` : ``layout`` route alors vers le chemin
« segments de ligne » (concaténation + lexer) au lieu du tokenizer glyphe.

Dépendances : ``paddleocr`` + ``paddlepaddle`` (optionnelles, non installées par
défaut). ``paddle_available()`` est faux sans elles → aucun impact sur le
pipeline historique (YOLO/Tesseract).
"""
from __future__ import annotations

import os
import threading
from typing import Any, List, Optional, Tuple

# Contourne le bug oneDNN/PIR de paddlepaddle (NotImplementedError
# ConvertPirAttribute2RuntimeAttribute dans onednn_instruction.cc) : doit être
# posé AVANT tout import de paddle.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
# Paddle/OpenMP se DEADLOCK quand l'inférence tourne dans un thread de fond (le
# worker du stream SSE) au lieu du thread principal : forcer le mono-thread OMP
# lève ce blocage. Doit être posé AVANT l'import de paddle.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("FLAGS_use_omp", "0")

from .extract import Run
from ..progress import ProgressFn, progress

_PADDLE: Optional[Any] = None
# L'inférence PaddleOCR n'est PAS thread-safe : on sérialise (une seule prédiction
# à la fois) pour éviter qu'une 2e requête ne deadlocke sur l'instance partagée.
_PREDICT_LOCK = threading.Lock()


def paddle_available() -> bool:
    """True si ``paddleocr`` et ``paddlepaddle`` sont importables."""
    try:
        import paddleocr  # noqa: F401
        import paddle  # noqa: F401
    except Exception:  # noqa: BLE001 — import lourd, tout échec = indisponible
        return False
    return True


def _get_paddle() -> Any:
    """Instancie (une fois) PaddleOCR, oneDNN désactivé.

    L'instanciation confirmée dans l'environnement cible est
    ``PaddleOCR(enable_mkldnn=False, use_textline_orientation=False, lang="en")``
    ; on garde une échelle de replis pour les autres versions du paquet.
    """
    global _PADDLE
    if _PADDLE is not None:
        return _PADDLE
    try:
        import paddle

        paddle.set_flags({"FLAGS_use_mkldnn": False})  # double sécurité oneDNN
        try:
            paddle.set_num_threads(1)  # mono-thread : évite le deadlock en thread
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    from paddleocr import PaddleOCR

    # ``use_doc_orientation_classify``/``use_doc_unwarping`` = False : on N'A PAS
    # besoin de la détection d'orientation ni du redressement de page (nos rendus
    # PDF sont droits et plats) — ça retire 2 modèles (doc_ori/UVDoc), allège la
    # mémoire, accélère, et écarte un composant suspect du blocage en thread.
    last_exc: Optional[Exception] = None
    for kw in (
        dict(use_doc_orientation_classify=False, use_doc_unwarping=False,
             use_textline_orientation=False, enable_mkldnn=False, lang="en"),
        dict(use_doc_orientation_classify=False, use_doc_unwarping=False,
             use_textline_orientation=False, lang="en"),
        dict(enable_mkldnn=False, use_textline_orientation=False, lang="en"),
        dict(use_textline_orientation=False, lang="en"),
        dict(use_angle_cls=False, lang="en"),
        dict(lang="en"),
        dict(),
    ):
        try:
            _PADDLE = PaddleOCR(**kw)
            return _PADDLE
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    from .ocr import OcrError

    raise OcrError(f"PaddleOCR : instanciation impossible ({last_exc})")


def _predict(bgr) -> Any:
    """Appel OCR : ``.predict`` (3.x, confirmé) puis ``.ocr`` (2.x).

    Sérialisé par ``_PREDICT_LOCK`` : PaddleOCR n'est pas thread-safe, une 2e
    requête concurrente deadlockait sur l'instance partagée."""
    ocr = _get_paddle()
    with _PREDICT_LOCK:
        for call in (lambda: ocr.predict(bgr), lambda: ocr.ocr(bgr)):
            try:
                return call()
            except Exception:  # noqa: BLE001
                continue
    from .ocr import OcrError

    raise OcrError("PaddleOCR : aucun appel (.predict/.ocr) n'a abouti")


def _page_dict(res: Any) -> Optional[dict]:
    """Extrait le dict page (format 3.x : rec_texts/rec_polys/rec_scores)."""
    page = res[0] if isinstance(res, (list, tuple)) and res else res
    if isinstance(page, dict):
        return page
    for attr in ("json", "res", "__dict__"):
        d = getattr(page, attr, None)
        if isinstance(d, dict) and ("rec_texts" in d or "rec_scores" in d):
            return d
    return None


def _box_x_cy(box: Any) -> Tuple[Optional[float], Optional[float]]:
    """(x gauche, y centre) d'une boîte, polygone [[x,y]…] ou [x1,y1,x2,y2]."""
    if box is None:
        return None, None
    arr = box.tolist() if hasattr(box, "tolist") else list(box)
    try:
        if arr and isinstance(arr[0], (list, tuple)):
            xs = [float(p[0]) for p in arr]
            ys = [float(p[1]) for p in arr]
        elif len(arr) >= 4:
            xs = [float(arr[0]), float(arr[2])]
            ys = [float(arr[1]), float(arr[3])]
        else:
            return None, None
    except (TypeError, ValueError, IndexError):
        return None, None
    return min(xs), (min(ys) + max(ys)) / 2.0


def paddle_ocr_page(bgr, *, font: str = "paddle") -> List[Run]:
    """Une page (image BGR) → runs (pixels, Y inversé PDF-like).

    Y est inversé (``page_h - y_centre``) pour coller au modèle PDF attendu par
    ``layout`` (y croissant vers le haut) ; la mise à l'échelle points est faite
    ensuite par ``normalize_page_runs``.
    """
    res = _predict(bgr)
    d = _page_dict(res)
    runs: List[Run] = []
    page_h = float(getattr(bgr, "shape", [1])[0] or 1)

    if d is not None:
        texts = d.get("rec_texts", []) or []
        polys = d.get("rec_polys") or d.get("dt_polys") or d.get("rec_boxes") or []
        for i, raw in enumerate(texts):
            text = str(raw).strip()
            if not text:
                continue
            x, cy = _box_x_cy(polys[i] if i < len(polys) else None)
            if x is None or cy is None:
                continue
            runs.append(
                Run(y=round(page_h - cy, 1), x=round(x, 1), font=font, text=text)
            )
        return runs

    # Repli format 2.x : [[ [box, (text, score)], ... ]]
    page = res[0] if isinstance(res, (list, tuple)) and res else res
    for item in page if isinstance(page, (list, tuple)) else []:
        try:
            box, (text, _score) = item
        except Exception:  # noqa: BLE001
            continue
        text = str(text).strip()
        if not text:
            continue
        x, cy = _box_x_cy(box)
        if x is None or cy is None:
            continue
        runs.append(Run(y=round(page_h - cy, 1), x=round(x, 1), font=font, text=text))
    return runs


def paddle_to_runs(
    source, *, dpi: int = 300, on_progress: ProgressFn = None
) -> List[Run]:
    """PDF scanné ou image → runs (texte + positions en points), via PaddleOCR.

    Miroir de ``ocr.ocr_to_runs`` mais sans la passe d'en-tête Tesseract (PaddleOCR
    lit déjà titre/tonique/compositeur) et sans exiger le binaire tesseract.
    """
    from .ocr import (
        OcrError,
        _image_from_bytes,
        _is_pdf,
        _page_images_from_pdf,
        normalize_page_runs,
    )

    data = source if isinstance(source, (bytes, bytearray)) else open(source, "rb").read()
    if not paddle_available():
        raise OcrError("PaddleOCR indisponible (paddleocr/paddlepaddle non installés)")

    pages = _page_images_from_pdf(data, dpi=dpi) if _is_pdf(data) else [_image_from_bytes(data)]
    n_pages = len(pages) or 1

    runs: List[Run] = []
    y_offset = 0.0     # empilement des pages, en POINTS (après normalisation)
    gap = 40.0         # cohérent avec _SYSTEM_GAP de layout.py
    for page_idx, (bgr, scale) in enumerate(pages):
        pct = 10 + 55 * page_idx / n_pages
        progress(
            on_progress,
            phase="ocr",
            pct=pct,
            message=f"OCR page {page_idx + 1}/{n_pages}…",
        )
        s = scale if scale and scale > 0 else 1.0
        page_runs = paddle_ocr_page(bgr)
        if not page_runs:
            y_offset -= bgr.shape[0] / s + gap
            continue
        norm = normalize_page_runs(page_runs, s, y_offset)
        runs.extend(norm)
        y_offset = min(r.y for r in norm) - gap

    if not runs:
        raise OcrError("PaddleOCR : aucun texte reconnu sur le document")
    progress(on_progress, phase="ocr", pct=65, message="OCR terminé")
    return runs
