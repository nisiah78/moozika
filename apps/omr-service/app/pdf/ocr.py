"""OCR : PDF/image scanné → runs de texte positionnés (même contrat que extract).

Pipeline (docs/architecture.md §5, Pipeline B) — architecture à 3 niveaux :
  1. **YOLO** (si modèle entraîné disponible) : détection de symboles sol-fa
     avec bounding boxes + classes. Résultat le plus précis.
  2. **TrOCR** (si transformers installé) : lecture par bande via Vision
     Transformer (Microsoft). Meilleur que Tesseract sur la ponctuation.
  3. **Tesseract** (fallback) : OCR classique par bande (PSM 7) ou page (PSM 6).

Prétraitement commun : PyMuPDF → OpenCV (Otsu) → bandes par projection.
Sortie alignée sur ``packages/shared-contracts/solfa-format.md`` (texte +
positions) ; le parseur ``app.solfa`` n'est pas modifié.
"""
from __future__ import annotations

import io
import shutil
import tempfile
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .extract import Run
from ..cancel import CancelFn, check
from ..progress import ProgressFn, progress


def normalize_page_runs(
    page_runs: List[Run], scale: float, y_offset: float = 0.0
) -> List[Run]:
    """Ramène des runs OCR/YOLO (pixels à `dpi`) vers l'échelle **points** (72 dpi)
    attendue par ``layout.py``, et empile la page sous les précédentes via
    ``y_offset``.

    C'est LE point de calibrage : les seuils de ``layout.py`` (_Y_TOL,
    _SYSTEM_GAP, _BAR_GAP…) sont en points ; sans cette division par `scale`
    (= dpi/72 ≈ 4,17 à 300 dpi) tous les écarts sont ~4× trop grands, ce qui
    sur-découpe les systèmes (4 voix → 2) et fabrique des barres/silences fantômes.
    """
    s = scale if scale and scale > 0 else 1.0
    return [
        replace(r, x=round(r.x / s, 1), y=round(y_offset + r.y / s, 1))
        for r in page_runs
    ]

# Charset utile pour sol-fa + en-têtes (titres malgaches / accents).
_TESS_WHITELIST = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    ":!;.|,'\"_-=#/ "
    "ôÔòÒöÖàáâäèéêëìíîïùúûüçÇñÑ"
)

_config_path: Optional[str] = None


def _tesseract_config(*, psm: int = 6) -> str:
    """Écrit la whitelist dans un fichier (évite le shlex de pytesseract)."""
    global _config_path
    if _config_path is None:
        fh = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".cfg", delete=False
        )
        fh.write(f"tessedit_char_whitelist {_TESS_WHITELIST}\n")
        fh.close()
        _config_path = fh.name
    return f"--oem 3 --psm {psm} {_config_path}"


class OcrError(ValueError):
    """Échec du pipeline OCR (dépendances manquantes ou page illisible)."""


def ocr_available() -> bool:
    """True si PyMuPDF, OpenCV, Pillow, pytesseract et le binaire tesseract sont là."""
    try:
        import fitz  # noqa: F401
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def preprocess_image(bgr) -> "Any":
    """OpenCV : gris → débruitage léger → Otsu (entrée BGR ou gris)."""
    import cv2
    import numpy as np

    if bgr is None or getattr(bgr, "size", 0) == 0:
        raise OcrError("image vide")
    if len(bgr.shape) == 3:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = bgr
    # Agrandit les petits scans pour Tesseract (~300 dpi équivalent).
    h, w = gray.shape[:2]
    if max(h, w) < 1200:
        scale = 1200 / max(h, w)
        gray = cv2.resize(
            gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC
        )
    den = cv2.fastNlMeansDenoising(gray, None, h=8, templateWindowSize=7, searchWindowSize=21)
    _, binary = cv2.threshold(den, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def detect_voice_bands(
    binary,
    *,
    min_gap: int = 15,
    density: float = 0.01,
    min_height: int = 8,
    max_height: int = 80,
) -> List[Tuple[int, int]]:
    """Projection horizontale → liste de ``(y_start, y_end)`` des bandes de texte.

    1. Seuil de densité → runs actifs.
    2. Fusion des runs proches (``min_gap``).
    3. Les bandes trop hautes (système SATB collé) sont re-segmentées via les
       minima locaux de la projection (une ligne = un pic).
    """
    import numpy as np

    if binary is None or getattr(binary, "size", 0) == 0:
        return []
    h, w = binary.shape[:2]
    proj = np.sum(binary == 0, axis=1).astype(np.float64)
    threshold = max(1.0, w * density)
    active = proj > threshold

    raw: List[Tuple[int, int]] = []
    i = 0
    while i < h:
        if not active[i]:
            i += 1
            continue
        start = i
        while i < h and active[i]:
            i += 1
        end = i
        if raw and start - raw[-1][1] < min_gap:
            raw[-1] = (raw[-1][0], end)
        else:
            raw.append((start, end))

    bands: List[Tuple[int, int]] = []
    for start, end in raw:
        height = end - start
        if height < min_height:
            continue
        if height <= max_height:
            bands.append((start, end))
            continue
        # Bande trop haute : découper sur les vallées de la projection.
        bands.extend(
            _split_band_by_valleys(
                proj, start, end, min_height=min_height, max_height=max_height
            )
        )
    return bands


def _split_band_by_valleys(
    proj,
    start: int,
    end: int,
    *,
    min_height: int,
    max_height: int,
) -> List[Tuple[int, int]]:
    """Découpe une bande haute en sous-bandes aux minima locaux de projection."""
    import numpy as np

    segment = proj[start:end]
    if len(segment) < min_height * 2:
        return [(start, end)] if (end - start) >= min_height else []

    # Lissage léger pour stabiliser les minima.
    kernel = np.ones(5) / 5.0
    smooth = np.convolve(segment, kernel, mode="same")
    # Seuil local : sous la médiane des valeurs actives → vallée.
    positive = smooth[smooth > 0]
    if len(positive) == 0:
        return [(start, end)]
    valley_thresh = float(np.median(positive)) * 0.35

    # Points de coupure = minima locaux sous le seuil, assez espacés.
    cuts: List[int] = []
    for i in range(2, len(smooth) - 2):
        if (
            smooth[i] <= valley_thresh
            and smooth[i] <= smooth[i - 1]
            and smooth[i] <= smooth[i + 1]
            and smooth[i] <= smooth[i - 2]
            and smooth[i] <= smooth[i + 2]
        ):
            abs_i = start + i
            if not cuts or abs_i - cuts[-1] >= min_height:
                cuts.append(abs_i)

    if not cuts:
        # Repli : découpe à pas fixe si toujours trop haut.
        if end - start > max_height * 2:
            step = max_height
            return [
                (y, min(y + step, end))
                for y in range(start, end, step)
                if min(y + step, end) - y >= min_height
            ]
        return [(start, end)]

    boundaries = [start] + cuts + [end]
    out: List[Tuple[int, int]] = []
    for a, b in zip(boundaries, boundaries[1:]):
        # Écarter le voisinage immédiat de la vallée.
        a2, b2 = a, b
        if a > start:
            a2 = a + 1
        if b < end:
            b2 = b - 1
        if b2 - a2 >= min_height:
            out.append((a2, b2))
    return out if out else [(start, end)]


def _page_images_from_pdf(data: bytes, dpi: int = 300) -> List[Tuple[Any, float]]:
    """Rend chaque page PDF → (image BGR, facteur pt→px = dpi/72)."""
    import fitz
    import numpy as np

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 — surface comme OcrError
        raise OcrError(f"PDF illisible pour OCR : {exc}") from exc
    if doc.page_count == 0:
        raise OcrError("PDF sans page")
    scale = dpi / 72.0
    pages: List[Tuple[Any, float]] = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        # pixmap RGB → BGR pour OpenCV
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        bgr = arr[:, :, ::-1].copy()
        pages.append((bgr, scale))
    return pages


def _image_from_bytes(data: bytes) -> Tuple[Any, float]:
    import cv2
    import numpy as np
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise OcrError(f"image illisible : {exc}") from exc
    rgb = np.array(img)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    # Pas de référence « points » sur une image brute : on estime l'échelle en
    # supposant une page ~792 pt de haut (lettre), pour que les seuils de
    # layout.py (calibrés en points) restent valides quel que soit le dpi du scan.
    scale = max(1.0, round(bgr.shape[0] / 792.0, 3))
    return bgr, scale


def _is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def tesseract_data_to_runs(
    data: Dict[str, Sequence[Any]],
    *,
    y_offset: float = 0.0,
    font: str = "ocr",
    page_h: Optional[float] = None,
    strip_top: float = 0.0,
) -> List[Run]:
    """Convertit la sortie ``image_to_data`` (dict) en runs positionnés.

    Coordonnées image (origine haut-gauche, y vers le bas) : on inverse y pour
    coller au modèle PDF (y croissant vers le haut) attendu par ``layout``.

    ``page_h`` : hauteur de la page (ou strip) pour inverser Y.
    ``strip_top`` : offset Y image du haut du strip dans la page (pour
    repositionner les runs d'une bande découpée).
    """
    texts = data.get("text", [])
    lefts = data.get("left", [])
    tops = data.get("top", [])
    heights = data.get("height", [])
    confs = data.get("conf", [])
    n = len(texts)
    if not (len(lefts) == len(tops) == len(heights) == n):
        raise OcrError("sortie Tesseract incohérente (champs manquants)")

    # Hauteur de page ≈ max(top+height) pour inverser l'axe Y.
    if page_h is None:
        page_h = 0.0
        for i in range(n):
            try:
                page_h = max(page_h, float(tops[i]) + float(heights[i]))
            except (TypeError, ValueError):
                continue
    if page_h <= 0:
        page_h = 1.0

    runs: List[Run] = []
    for i in range(n):
        raw = texts[i]
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        try:
            conf = float(confs[i]) if i < len(confs) else -1.0
        except (TypeError, ValueError):
            conf = -1.0
        # conf == -1 = en-tête de niveau Tesseract (non-mot) ; ignorer si < 0
        # sauf quand confs absents. On garde conf >= 0 (y compris 0).
        if confs and conf < 0:
            continue
        try:
            x = float(lefts[i])
            top = float(tops[i]) + strip_top
            h = float(heights[i])
        except (TypeError, ValueError):
            continue
        # Centre vertical du mot, Y PDF-like (haut = grand y).
        y = y_offset + (page_h - (top + h / 2.0))
        runs.append(Run(y=round(y, 1), x=round(x, 1), font=font, text=text))
    return runs


def _ocr_strip(strip, *, page_h: float, strip_top: float, y_offset: float = 0.0) -> List[Run]:
    """OCR d'une bande isolée en PSM 7 (ligne unique), repli PSM 13.

    Les bandes trop petites ou illisibles sont ignorées (pas d'échec global).
    """
    import pytesseract

    if strip is None or getattr(strip, "size", 0) == 0:
        return []
    if strip.shape[0] < 12 or strip.shape[1] < 20:
        return []

    def _run(psm: int) -> List[Run]:
        try:
            data = pytesseract.image_to_data(
                strip,
                output_type=pytesseract.Output.DICT,
                config=_tesseract_config(psm=psm),
                lang="eng",
            )
        except Exception:  # noqa: BLE001
            return []
        return tesseract_data_to_runs(
            data, y_offset=y_offset, page_h=page_h, strip_top=strip_top
        )

    runs = _run(7)
    # Repli raw_line si PSM 7 n'a presque rien lu.
    if len(runs) < 2:
        alt = _run(13)
        if len(alt) > len(runs):
            runs = alt
    return runs


def ocr_bands(bgr, *, y_offset: float = 0.0, margin: int = 6) -> List[Run]:
    """OCR par bande : chaque bande reçoit ``--psm 7`` (ligne unique).

    Préserve l'assignation verticale des voix SATB que PSM 6 sur page entière
    mélangeait. Petites images / peu de bandes → repli PSM 6 page entière.
    """
    binary = preprocess_image(bgr)
    page_h = float(binary.shape[0])

    # Image courte (ligne de test, crop) : PSM 6 page entière plus fiable.
    if binary.shape[0] < 200:
        return _ocr_bgr_full(binary, y_offset=y_offset)

    bands = detect_voice_bands(
        binary, min_gap=6, min_height=10, max_height=48, density=0.015
    )
    if not bands:
        return _ocr_bgr_full(binary, y_offset=y_offset)

    runs: List[Run] = []
    for y_start, y_end in bands:
        if (y_end - y_start) < 10:
            continue
        top = max(0, y_start - margin)
        bottom = min(binary.shape[0], y_end + margin)
        strip = binary[top:bottom, :]
        if strip.shape[0] < 20:
            import numpy as np

            pad = 20 - strip.shape[0]
            strip = np.pad(
                strip,
                ((pad // 2, pad - pad // 2), (0, 0)),
                mode="constant",
                constant_values=255,
            )
            top = max(0, top - pad // 2)
        strip_runs = _ocr_strip(
            strip, page_h=page_h, strip_top=float(top), y_offset=y_offset
        )
        runs.extend(strip_runs)

    if not runs:
        return _ocr_bgr_full(binary, y_offset=y_offset)
    return runs


def _ocr_bgr_full(processed, *, y_offset: float = 0.0) -> List[Run]:
    """Repli : OCR page entière en PSM 6."""
    import pytesseract

    try:
        data = pytesseract.image_to_data(
            processed,
            output_type=pytesseract.Output.DICT,
            config=_tesseract_config(psm=6),
            lang="eng",
        )
    except pytesseract.TesseractError as exc:
        raise OcrError(f"Tesseract a échoué : {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise OcrError(f"OCR impossible : {exc}") from exc
    return tesseract_data_to_runs(data, y_offset=y_offset)


_SOLFA_SYLLABLES = {"d", "r", "m", "f", "s", "l", "t", "di", "ri", "fi", "si", "ta"}


def _has_solfa_content(runs: List[Run], min_ratio: float = 0.05) -> bool:
    """Vérifie que les runs contiennent un minimum de syllabes sol-fa.

    Rejette les résultats dominés par du bruit (tirets, astérisques, zéros).
    """
    if not runs:
        return False
    total = len(runs)
    solfa_count = sum(
        1 for r in runs
        if r.text.lower().rstrip("',_") in _SOLFA_SYLLABLES
    )
    return solfa_count / total >= min_ratio


def _ocr_bgr(bgr, *, y_offset: float = 0.0) -> List[Run]:
    """OCR d'une page — pipeline à 4 niveaux : YOLO → TrOCR → CC → Tesseract."""
    # Niveau 1 : YOLO (le plus précis, si modèle entraîné disponible).
    try:
        from .yolo_detect import SolfaYoloDetector, yolo_ocr_page

        detector = SolfaYoloDetector()
        if detector.is_ready:
            runs = yolo_ocr_page(bgr, detector, y_offset=y_offset, conf=0.15)
            if len(runs) > 20:
                return runs
    except Exception:  # noqa: BLE001
        pass

    # Niveau 2 : TrOCR par bande — activé uniquement si un modèle fine-tuné sol-fa
    # est disponible (env TROCR_SOLFA_MODEL). Le modèle pré-entraîné generic
    # ne reconnaît pas la notation sol-fa et ralentit le pipeline inutilement.
    import os as _os

    if _os.environ.get("TROCR_SOLFA_MODEL"):
        try:
            from .trocr import trocr_available, trocr_ocr_bands

            if trocr_available():
                runs = trocr_ocr_bands(bgr, y_offset=y_offset)
                if len(runs) > 10 and _has_solfa_content(runs):
                    return runs
        except Exception:  # noqa: BLE001
            pass

    # Niveau 3 : Connected Components + template classifier (pas de dépendance ML).
    try:
        from .cc_pipeline import cc_ocr_page

        runs = cc_ocr_page(bgr, y_offset=y_offset)
        if len(runs) > 10:
            return runs
    except Exception:  # noqa: BLE001
        pass

    # Niveau 4 : Tesseract par bande (fallback).
    return ocr_bands(bgr, y_offset=y_offset)


def header_text_runs(bgr, *, band_frac: float = 0.20, font: str = "text") -> List[Run]:
    """Passe Tesseract sur la BANDE HAUTE (en-tête) pour lire le texte que YOLO
    ne détecte pas : titre, « Do dia X » (tonique), compositeur. Les runs sont
    fusionnés aux glyphes ; ``layout.parse_header`` en extrait tonique/titre/…

    Robuste : retourne [] si Tesseract indisponible/échoue — jamais bloquant, et
    les runs texte (sans séparateurs de temps) ne sont pas pris pour des voix."""
    try:
        import pytesseract
    except ImportError:
        return []
    h = int(getattr(bgr, "shape", [0])[0] or 0)
    band = int(h * band_frac)
    if band < 12:
        return []
    try:
        binary = preprocess_image(bgr[0:band, :])
        data = pytesseract.image_to_data(
            binary,
            output_type=pytesseract.Output.DICT,
            config=_tesseract_config(psm=6),
            lang="eng",
        )
    except Exception:  # noqa: BLE001 — passe optionnelle, jamais bloquante
        return []
    # page_h = hauteur PLEINE pour que l'inversion Y colle aux glyphes YOLO.
    return tesseract_data_to_runs(data, page_h=float(h), strip_top=0.0, font=font)


def ocr_to_runs(
    source: Union[str, bytes], *, dpi: int = 300, on_progress: ProgressFn = None,
    is_cancelled: CancelFn = None,
) -> List[Run]:
    """PDF scanné ou image → liste de ``Run`` (texte + positions)."""
    if not ocr_available():
        raise OcrError(
            "OCR indisponible : installer pymupdf, opencv-python-headless, "
            "pytesseract, Pillow et le binaire tesseract-ocr"
        )
    if isinstance(source, str):
        with open(source, "rb") as fh:
            data = fh.read()
    else:
        data = source

    runs: List[Run] = []
    y_offset = 0.0     # empilement des pages, en POINTS (après normalisation)
    gap = 40.0         # points (cohérent avec _SYSTEM_GAP de layout.py)

    if _is_pdf(data):
        pages = _page_images_from_pdf(data, dpi=dpi)
    else:
        pages = [_image_from_bytes(data)]

    n_pages = len(pages) or 1
    for page_idx, (bgr, scale) in enumerate(pages):
        check(is_cancelled)
        pct = 10 + 55 * page_idx / n_pages
        progress(
            on_progress,
            phase="ocr",
            pct=pct,
            message=f"OCR page {page_idx + 1}/{n_pages}…",
        )
        s = scale if scale and scale > 0 else 1.0
        # Runs page-locaux (y_offset appliqué APRÈS passage en points).
        page_runs = _ocr_bgr(bgr, y_offset=0.0)
        # Page 1 : passe TEXTE (Tesseract) sur l'en-tête, que YOLO ne lit pas
        # (titre, « Do dia X » = tonique, compositeur). Non bloquant.
        if page_idx == 0:
            page_runs = list(page_runs) + header_text_runs(bgr)
        if not page_runs:
            y_offset -= bgr.shape[0] / s + gap
            continue
        norm = normalize_page_runs(page_runs, s, y_offset)
        runs.extend(norm)
        y_offset = min(r.y for r in norm) - gap

    if not runs:
        raise OcrError("OCR : aucun texte reconnu sur le document")
    progress(on_progress, phase="ocr", pct=65, message="OCR terminé")
    return runs
