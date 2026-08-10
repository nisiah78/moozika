"""Diagnostic JETABLE : chemin PaddleOCR bout-en-bout + STRUCTURE des lignes.

But de cette version : voir la **structure verticale réelle** (y + écarts) des
lignes, pour concevoir le regroupement des systèmes (les 24 lignes = N systèmes ×
4 voix S/A/T/B). Puis le résultat pipeline courant (avec normalisation OCR).

  docker compose run --rm --no-deps -v "$(pwd)/docs:/docs:ro" omr-service \\
      sh -c "pip install -q paddleocr paddlepaddle && \\
             python3 -m app.inspect_paddle_pipeline /docs/mivavaha.pdf"

Colle toute la sortie. Supprime ce fichier ensuite.
"""
from __future__ import annotations

import sys
import traceback


def main() -> None:
    pdf = sys.argv[1] if len(sys.argv) > 1 else None
    if not pdf:
        print("(donne un PDF en argument)")
        return
    data = open(pdf, "rb").read()

    from .pdf.paddle_ocr import paddle_to_runs
    from .pdf.layout import (
        _cluster_rows,
        _orient_rows,
        _is_voice_row,
        _row_y,
        _row_text,
    )

    runs = paddle_to_runs(data)
    print("nb runs (points, Y inversé):", len(runs))

    clustered = _cluster_rows(runs)
    rows, y_desc = _orient_rows(clustered)
    print(f"nb lignes (clusters): {len(rows)}  | y_descending={y_desc}")

    # STRUCTURE : y, écart à la ligne précédente, voix?, aperçu texte.
    print("\n=== STRUCTURE DES LIGNES (ordre de lecture) ===")
    prev_y = None
    for row in rows:
        y = _row_y(row)
        gap = "" if prev_y is None else f"{abs(prev_y - y):6.1f}"
        prev_y = y
        tag = "VOIX " if _is_voice_row(row) else "  -  "
        txt = _row_text(row)
        preview = (txt[:60] + "…") if len(txt) > 60 else txt
        print(f"  y={y:8.1f}  gap={gap:>6}  {tag} n={len(row):2d}  {preview}")

    # Écarts entre lignes de VOIX seulement (là où le regroupement opère).
    vrows = [r for r in rows if _is_voice_row(r)]
    print(f"\n=== ÉCARTS entre lignes de VOIX (n={len(vrows)}) ===")
    vy = [_row_y(r) for r in vrows]
    gaps = [round(abs(vy[i] - vy[i - 1]), 1) for i in range(1, len(vy))]
    print("gaps:", gaps)

    # Résultat pipeline courant (avec normalisation OCR).
    from .pdf.layout import build_document
    from .solfa import parse_solfa

    doc = build_document(runs)
    print(f"\n=== VOIX (n={len(doc.voices)}) ===")
    for name, notation in zip(doc.voice_names, doc.voices):
        n_bars = notation.count("|") + 1 if notation.strip() else 0
        try:
            model = parse_solfa(notation, tonic=doc.header.tonic, lenient=True, degrade=True)
            res = f"OK {len(model.measures)} mes, {sum(len(m.notes) for m in model.measures)} notes"
        except Exception as exc:  # noqa: BLE001
            res = f"ERREUR {type(exc).__name__}: {exc}"
        print(f"\n--- {name} ({n_bars} mes-texte) → {res}")
        print(f"    {notation}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
