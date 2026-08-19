#!/usr/bin/env python3
"""Contrôle de syntaxe Python qui n'ÉCRIT RIEN sur le disque.

`python3 -m py_compile` écrit un .pyc à côté de la source : impossible ici, le
dossier apps/omr-service/app/__pycache__ appartient à root (créé par un ancien
run Docker avec montage des sources) → Permission denied. ast.parse fait le même
contrôle sans effet de bord.

    python3 scripts/quality/syntax_check.py fichier.py [...]
"""

import ast
import sys


def main(paths: list[str]) -> int:
    failed = 0
    for path in paths:
        try:
            with open(path, "rb") as fh:
                ast.parse(fh.read(), filename=path)
        except SyntaxError as exc:
            print(f"{path}:{exc.lineno}:{exc.offset}: {exc.msg}", file=sys.stderr)
            failed += 1
        except OSError as exc:
            print(f"{path}: illisible ({exc})", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
