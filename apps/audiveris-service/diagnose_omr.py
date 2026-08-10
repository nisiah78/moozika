#!/usr/bin/env python3
"""Diagnostic OMR : combien de mesures Audiveris récupère sur un PDF, au global
et PAGE PAR PAGE, pour localiser où les mesures se perdent.

Usage (depuis la racine du repo, avec le service audiveris sur :8081) :

    python3 apps/audiveris-service/diagnose_omr.py [chemin.pdf]

Défaut : docs/solfege/jubilate-deo-peter-anglea.pdf
Nécessite : pypdf (déjà présent), curl, et le conteneur `audiveris` lancé.
N'utilise QUE les réglages par défaut du service (aucun paramètre récent requis).

Lecture des résultats :
  - SOMME par page ≫ global  → perte au RACCORD multi-pages (réglable).
  - une/deux pages à 0        → ces pages ne sont pas segmentées (cible précise).
  - chaque page perd un peu   → dégradation OMR diffuse (piste résolution/qualité).
  - « parts » incohérent      → Audiveris regroupe mal les portées (SATB+piano).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

URL = "http://localhost:8081/recognize"


def _recognize(pdf_path: str) -> str | None:
    """POST le PDF au service audiveris, renvoie le MusicXML (ou None si erreur)."""
    proc = subprocess.run(
        ["curl", "-s", "--max-time", "900", "-F", f"file=@{pdf_path}", URL],
        capture_output=True, text=True,
    )
    try:
        return json.loads(proc.stdout)["musicxml"]
    except Exception:
        sys.stdout.write(f"    [erreur] {(proc.stdout or proc.stderr)[:120]}\n")
        return None


def _summary(xml: str | None) -> tuple[int, str]:
    """(nb de mesures max, texte détaillé parts)."""
    if xml is None:
        return 0, "ERREUR"
    parts = re.findall(r'<part\s+id="[^"]*">(.*?)</part>', xml, re.DOTALL)
    per_part = []
    for body in parts:
        nums = [int(m) for m in re.findall(r'measure number="(\d+)"', body)]
        per_part.append(max(nums) if nums else 0)
    overall = max(per_part) if per_part else 0
    return overall, f"{overall} mesures | {len(parts)} parts {per_part}"


def main() -> None:
    pdf = sys.argv[1] if len(sys.argv) > 1 else "docs/solfege/jubilate-deo-peter-anglea.pdf"
    if not Path(pdf).is_file():
        sys.exit(f"introuvable : {pdf}")
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(pdf)
    n = len(reader.pages)
    print(f"PDF : {pdf} ({n} pages)\n")

    print("== Livre entier (réglage par défaut du service) ==", flush=True)
    _, txt = _summary(_recognize(pdf))
    print("  ->", txt)

    print("\n== Page par page ==", flush=True)
    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, page in enumerate(reader.pages):
            fn = str(Path(tmp) / f"p{i + 1}.pdf")
            writer = PdfWriter()
            writer.add_page(page)
            with open(fn, "wb") as f:
                writer.write(f)
            count, txt = _summary(_recognize(fn))
            print(f"  page {i + 1:2} -> {txt}", flush=True)
            total += count
    print(f"\n  SOMME des mesures par page : {total}")
    print("  (à comparer au « livre entier » ci-dessus)")


if __name__ == "__main__":
    main()
