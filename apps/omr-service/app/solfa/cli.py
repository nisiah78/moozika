"""CLI : sol-fa -> MusicXML / JSON.

Exemples :
    python -m app.solfa.cli --tonic C "d : d : s : s | l : l : s : -"
    python -m app.solfa.cli --tonic F --in feuille.solfa --out sortie.musicxml
    python -m app.solfa.cli --tonic C --json "d : r : m : f"
"""
from __future__ import annotations

import argparse
import json
import sys

from . import parse_solfa, to_musicxml
from .parser import ParseError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Convertit du sol-fa tonique en MusicXML.")
    parser.add_argument("notation", nargs="?", help="notation sol-fa (ou --in)")
    parser.add_argument("--in", dest="infile", help="fichier de notation sol-fa")
    parser.add_argument("--out", dest="outfile", help="fichier de sortie (défaut: stdout)")
    parser.add_argument("--tonic", default="C", help="tonique, ex. C, F, Bb (défaut C)")
    parser.add_argument("--doh-octave", type=int, default=4, help="octave du doh (défaut 4)")
    parser.add_argument("--clef", default="treble", choices=["treble", "bass"])
    parser.add_argument("--json", action="store_true", help="sort le modèle JSON au lieu du MusicXML")
    args = parser.parse_args(argv)

    if args.infile:
        with open(args.infile, "r", encoding="utf-8") as fh:
            notation = fh.read()
    elif args.notation:
        notation = args.notation
    else:
        parser.error("fournir une notation en argument ou via --in")
        return 2

    try:
        model = parse_solfa(notation, tonic=args.tonic, doh_octave=args.doh_octave, clef=args.clef)
    except ParseError as exc:
        print(f"Erreur de parsing : {exc}", file=sys.stderr)
        return 1

    output = json.dumps(model.to_dict(), indent=2, ensure_ascii=False) if args.json else to_musicxml(model)

    if args.outfile:
        with open(args.outfile, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"Écrit : {args.outfile}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
