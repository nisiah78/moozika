"""CLI : PDF sol-fa -> MusicXML / JSON / notation canonique.

Exemples :
    python -m app.pdf.cli docs/jesoa-tsy-mba-mandao.pdf
    python -m app.pdf.cli partition.pdf --out sortie.musicxml
    python -m app.pdf.cli partition.pdf --notation   # affiche le sol-fa reconstruit
    python -m app.pdf.cli partition.pdf --json        # en-tête + voix + modèles
"""
from __future__ import annotations

import argparse
import json
import sys

from .document import PdfSolfaError, pdf_to_document, pdf_to_score


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Lit un PDF de partition sol-fa tonique.")
    parser.add_argument("pdf", help="chemin du fichier PDF")
    parser.add_argument("--out", help="fichier de sortie (défaut: stdout)")
    parser.add_argument("--json", action="store_true", help="sort le résultat JSON complet")
    parser.add_argument("--notation", action="store_true", help="sort la notation sol-fa reconstruite")
    args = parser.parse_args(argv)

    try:
        if args.notation:
            doc = pdf_to_document(args.pdf)
            lines = [f"# {doc.header.title}",
                     f"# Doh = {doc.header.tonic}  {doc.header.beats}/{doc.header.beat_type}"
                     f"  tempo={doc.header.tempo}"]
            for name, voice in zip(doc.voice_names, doc.voices):
                lines.append(f"\n[{name}]\n{voice}")
            output = "\n".join(lines) + "\n"
        else:
            result = pdf_to_score(args.pdf)
            output = json.dumps(result, indent=2, ensure_ascii=False) if args.json else result["musicxml"]
    except PdfSolfaError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"Écrit : {args.out}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
