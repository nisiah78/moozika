"""Introspection JETABLE de l'API Surya installée (surya-ocr 0.22.1).

Découvre empiriquement, dans TON environnement, l'API réelle + la structure du
résultat OCR — pour écrire l'intégration sans rien deviner.

  docker compose run --rm --no-deps -v "$(pwd)/docs:/docs:ro" \\
      omr-service python3 -m app.inspect_surya /docs/mivavaha.pdf

Colle toute la sortie à l'assistant. Supprime ce fichier ensuite.
"""
from __future__ import annotations

import inspect
import sys
import traceback


def _sig(obj, name):
    try:
        print(f"  signature {name}: {inspect.signature(obj)}")
    except (TypeError, ValueError):
        print(f"  signature {name}: (indisponible)")


def _fields(obj, label):
    """Imprime les attributs publics d'un objet (dataclass/pydantic/normal)."""
    print(f"  {label}: type={type(obj).__name__}")
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict) and d:
        for k, v in d.items():
            vs = repr(v)
            print(f"      .{k} = {vs[:120]}")
    else:
        pub = [a for a in dir(obj) if not a.startswith("_")]
        print(f"      attributs: {pub[:40]}")


def main() -> None:
    import surya
    print("surya.__version__ =", getattr(surya, "__version__", "?"))

    # 1) Classes de prédicteurs (on essaie les chemins connus).
    print("\n=== IMPORTS / CLASSES ===")
    predictors = {}
    for modpath, clsname in [
        ("surya.recognition", "RecognitionPredictor"),
        ("surya.detection", "DetectionPredictor"),
        ("surya.foundation", "FoundationPredictor"),
        ("surya.layout", "LayoutPredictor"),
    ]:
        try:
            mod = __import__(modpath, fromlist=[clsname])
            cls = getattr(mod, clsname)
            predictors[clsname] = cls
            print(f"OK  from {modpath} import {clsname}")
            _sig(cls.__init__, f"{clsname}.__init__")
            _sig(cls.__call__, f"{clsname}.__call__")
        except Exception as exc:  # noqa: BLE001
            print(f"KO  from {modpath} import {clsname}  -> {type(exc).__name__}: {exc}")

    # 2) Charger l'image page 1 de mivavaha (via le rendu PDF existant).
    print("\n=== OCR SUR LA PAGE 1 ===")
    pdf = sys.argv[1] if len(sys.argv) > 1 else None
    if not pdf:
        print("(donne un PDF en argument pour l'exécution OCR)")
        return
    try:
        from PIL import Image
        from .pdf.ocr import _page_images_from_pdf
        data = open(pdf, "rb").read()
        pages = _page_images_from_pdf(data, dpi=300)
        bgr, scale = pages[0]
        img = Image.fromarray(bgr[:, :, ::-1])  # BGR->RGB
        print(f"image page1: {img.size} (scale={scale})")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return

    # 3) SCHÉMA des classes de résultat (SANS exécuter — pas besoin de llama).
    print("\n=== SCHÉMA DES RÉSULTATS (sans exécution) ===")
    for modpath, clsname in [
        ("surya.recognition.schema", "OCRResult"),
        ("surya.recognition.schema", "PageOCRResult"),
        ("surya.recognition.schema", "TextLine"),
        ("surya.recognition.schema", "TextWord"),
        ("surya.recognition.schema", "TextChar"),
        ("surya.detection.schema", "TextDetectionResult"),
        ("surya.common.polygon", "PolygonBox"),
        ("surya.layout.schema", "LayoutResult"),
    ]:
        try:
            mod = __import__(modpath, fromlist=[clsname])
            cls = getattr(mod, clsname)
            _schema(cls, f"{modpath}.{clsname}")
        except Exception as exc:  # noqa: BLE001
            print(f"  (absent) {modpath}.{clsname} -> {type(exc).__name__}")

    # 4) DÉTECTION seule (torch, PAS de llama-server) : confirme les boîtes.
    print("\n=== DÉTECTION (boîtes de lignes, sans llama) ===")
    det_cls = predictors.get("DetectionPredictor")
    if det_cls:
        try:
            det = det_cls()
            det_out = det([img])
            print("type:", type(det_out).__name__, "| len:", len(det_out))
            page = det_out[0]
            _fields(page, "det_out[0]")
            boxes = getattr(page, "bboxes", None) or getattr(page, "boxes", None)
            if boxes:
                print(f"  nb boîtes: {len(boxes)}")
                for b in boxes[:5]:
                    _fields(b, "box")
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    # 5) RECONNAISSANCE : appel CORRECT (full_page=True). Échouera sans
    #    llama-server, mais on capture l'erreur / le résultat proprement.
    print("\n=== RECONNAISSANCE (full_page=True) ===")
    rec_cls = predictors.get("RecognitionPredictor")
    if rec_cls:
        try:
            rec = rec_cls()
            preds = rec([img], full_page=True)
            print("OK ! type:", type(preds).__name__, "| len:", len(preds))
            page = preds[0]
            _fields(page, "preds[0]")
            lines = getattr(page, "text_lines", None) or getattr(page, "lines", None)
            if lines:
                print(f"  nb lignes: {len(lines)}")
                for ln in lines[:8]:
                    _fields(ln, "ligne")
        except Exception as exc:  # noqa: BLE001
            print(f"ÉCHEC reconnaissance: {type(exc).__name__}: {exc}")


def _schema(cls, label):
    """Champs d'une classe pydantic/dataclass, sans instancier."""
    fields = None
    mf = getattr(cls, "model_fields", None)          # pydantic v2
    if isinstance(mf, dict):
        fields = {k: str(getattr(v, "annotation", "?")) for k, v in mf.items()}
    if fields is None:
        ann = getattr(cls, "__annotations__", None)  # dataclass / annotations
        if ann:
            fields = {k: str(v) for k, v in ann.items()}
    print(f"  {label}:")
    if fields:
        for k, v in fields.items():
            print(f"      {k}: {v}")
    else:
        print("      (pas de champs introspectables)")


if __name__ == "__main__":
    main()
