"""Diagnostic JETABLE : dump des runs OCR + voix produites pour un PDF sol-fa.

À lancer là où l'OCR/YOLO est installé (conteneur Docker `omr-service`).

  # dans le conteneur (depuis /app) :
  python3 -m app.dump_mivavaha /docs/mivavaha.pdf

  # ou en une commande depuis la racine du repo :
  docker compose run --rm --no-deps -v "$(pwd)/docs:/docs:ro" \\
      omr-service python3 -m app.dump_mivavaha /docs/mivavaha.pdf

Colle la sortie à l'assistant. Supprime ensuite ce fichier (jetable).
"""
from __future__ import annotations

import sys
from pathlib import Path


def _find_pdf() -> Path:
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if not p.is_file():
            raise SystemExit(f"PDF introuvable: {p}")
        return p
    here = Path(__file__).resolve()
    for base in here.parents:
        for cand in (base / "docs" / "mivavaha.pdf", base / "mivavaha.pdf"):
            if cand.is_file():
                return cand
    raise SystemExit("Donne le chemin du PDF en argument : python3 -m app.dump_mivavaha <pdf>")


def main() -> None:
    pdf = _find_pdf()
    data = pdf.read_bytes()
    print(f"PDF: {pdf}  ({len(data)} octets)")

    # Diagnostic de l'environnement de détection.
    try:
        from app.pdf.ocr import ocr_available
        print("ocr_available (tesseract+deps):", ocr_available())
    except Exception as exc:  # noqa: BLE001
        print("ocr_available: erreur", exc)
    try:
        from app.pdf.yolo_detect import SolfaYoloDetector, yolo_available
        det = SolfaYoloDetector()
        print("yolo_available:", yolo_available(), "| modèle prêt:", det.is_ready,
              "|", det.model_path)
    except Exception as exc:  # noqa: BLE001
        print("yolo: erreur", exc)

    # 1) Runs bruts (glyphes positionnés) via le pipeline de détection.
    print("\n=== RUNS ===")
    try:
        from app.pdf.ocr import ocr_to_runs
        runs = ocr_to_runs(data)
        print(f"NB RUNS: {len(runs)}")
        for r in runs[:150]:
            print(f"{r.y:9.1f} {r.x:9.1f} {r.font:8} {r.text!r}")
        if len(runs) > 150:
            print(f"... (+{len(runs) - 150} runs)")
    except Exception as exc:  # noqa: BLE001
        print(f"[ocr_to_runs a échoué] {type(exc).__name__}: {exc}")

    # 2) Document reconstruit (voix + en-tête).
    print("\n=== DOCUMENT ===")
    try:
        from app.pdf.document import pdf_to_document
        doc = pdf_to_document(data)
        print("HEADER:", doc.header)
        print("VOICES:", doc.voice_names)
        for name, notation in zip(doc.voice_names, doc.voices):
            print(f"\n[{name}]")
            print(notation[:400])
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
