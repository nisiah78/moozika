"""Introspection JETABLE : API réelle de PaddleOCR + QUALITÉ sur mivavaha.

Découvre, dans TON environnement : la version, comment instancier/appeler
PaddleOCR, la structure exacte du résultat, ET imprime les lignes reconnues sur
la page 1 (pour juger si PaddleOCR lit correctement le sol-fa avant d'intégrer).

  docker compose run --rm --no-deps -v "$(pwd)/docs:/docs:ro" omr-service \\
      sh -c "pip install -q paddleocr paddlepaddle && python3 -m app.inspect_paddle /docs/mivavaha.pdf"

Colle toute la sortie. Supprime ce fichier ensuite.
"""
from __future__ import annotations

import os
import sys
import traceback

# Contourne le bug oneDNN/PIR de paddle (NotImplementedError onednn_instruction) :
# doit être posé AVANT tout import de paddle.
os.environ.setdefault("FLAGS_use_mkldnn", "0")


def _dump(obj, label, depth=0):
    pad = "  " * depth
    t = type(obj).__name__
    if isinstance(obj, dict):
        print(f"{pad}{label}: dict clés={list(obj.keys())[:15]}")
    elif isinstance(obj, (list, tuple)):
        print(f"{pad}{label}: {t} len={len(obj)}")
        if obj:
            _dump(obj[0], f"{label}[0]", depth + 1)
    else:
        d = getattr(obj, "__dict__", None)
        if isinstance(d, dict) and d:
            print(f"{pad}{label}: {t} attrs={list(d.keys())[:15]}")
        else:
            pub = [a for a in dir(obj) if not a.startswith("_")][:15]
            print(f"{pad}{label}: {t} pub={pub}")


def main() -> None:
    import paddleocr
    print("paddleocr:", getattr(paddleocr, "__version__", "?"))
    try:
        import paddle
        print("paddle:", getattr(paddle, "__version__", "?"))
        try:
            paddle.set_flags({"FLAGS_use_mkldnn": False})  # double sécurité oneDNN
            print("oneDNN désactivé (FLAGS_use_mkldnn=0)")
        except Exception as exc:  # noqa: BLE001
            print("set_flags:", exc)
    except Exception as exc:  # noqa: BLE001
        print("paddle import:", exc)

    from paddleocr import PaddleOCR

    # 1) Instancier (on essaie kwargs 3.x puis 2.x puis nu).
    ocr = None
    for kw in (
        dict(enable_mkldnn=False, use_textline_orientation=False, lang="en"),
        dict(use_textline_orientation=False, lang="en"),
        dict(use_angle_cls=False, lang="en"),
        dict(lang="en"),
        dict(),
    ):
        try:
            ocr = PaddleOCR(**kw)
            print(f"\nOK instanciation: PaddleOCR({kw})")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"KO PaddleOCR({kw}) -> {type(exc).__name__}: {exc}")
    if ocr is None:
        print("Impossible d'instancier PaddleOCR."); return

    # 2) Image page 1 de mivavaha.
    pdf = sys.argv[1] if len(sys.argv) > 1 else None
    if not pdf:
        print("(donne un PDF en argument)"); return
    from .pdf.ocr import _page_images_from_pdf
    bgr, scale = _page_images_from_pdf(open(pdf, "rb").read(), dpi=300)[0]
    print(f"image page1: {bgr.shape} (scale={scale})")

    # 3) Appel OCR : .predict (3.x) puis .ocr (2.x).
    res = None
    for name, call in (
        ("ocr.predict(bgr)", lambda: ocr.predict(bgr)),
        ("ocr.ocr(bgr)", lambda: ocr.ocr(bgr)),
        ("ocr.ocr(bgr, cls=False)", lambda: ocr.ocr(bgr, cls=False)),
    ):
        try:
            res = call()
            print(f"\nAPPEL QUI MARCHE: {name}")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"KO {name} -> {type(exc).__name__}: {exc}")
    if res is None:
        print("Aucun appel OCR n'a marché."); return

    # 4) Structure du résultat.
    print("\n=== STRUCTURE ===")
    _dump(res, "res")
    page = res[0] if isinstance(res, (list, tuple)) and res else res
    _dump(page, "page")

    # 5) Extraire (texte, box, conf) de façon générique et imprimer ~20 lignes.
    print("\n=== LIGNES RECONNUES (page 1, ~20 premières) ===")
    lines = []
    # format 3.x : dict/objet avec rec_texts / rec_polys / rec_scores
    d = page if isinstance(page, dict) else getattr(page, "json", None) or getattr(page, "__dict__", {})
    if isinstance(d, dict) and ("rec_texts" in d or "rec_scores" in d):
        texts = d.get("rec_texts", []); polys = d.get("rec_polys") or d.get("dt_polys") or d.get("rec_boxes") or []
        scores = d.get("rec_scores", [])
        for i, t in enumerate(texts):
            box = polys[i] if i < len(polys) else None
            sc = scores[i] if i < len(scores) else None
            lines.append((t, sc, box))
    else:
        # format 2.x : [[ [box,(text,score)], ... ]]
        seq = page if isinstance(page, (list, tuple)) else []
        for item in seq:
            try:
                box, (t, sc) = item
                lines.append((t, sc, box))
            except Exception:  # noqa: BLE001
                pass
    def _yx(box):
        try:
            pts = box.tolist() if hasattr(box, "tolist") else list(box)
            ys = [float(p[1]) for p in pts]
            xs = [float(p[0]) for p in pts]
            return round(min(ys), 1), round(min(xs), 1)
        except Exception:  # noqa: BLE001
            return None, None

    print(f"nb lignes: {len(lines)}")
    # tri par ligne (y décroissant image = haut d'abord) puis x, pour lecture.
    enriched = [(*_yx(b), t, s) for (t, s, b) in lines]
    enriched.sort(key=lambda e: (-(e[0] or 0), e[1] or 0))
    for y, x, t, sc in enriched:
        scv = f"{sc:.2f}" if isinstance(sc, float) else sc
        print(f"  y={y} x={x} conf={scv} texte={t!r}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
