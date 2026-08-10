"""Introspection JETABLE : Surya 0.22.1 a-t-il une alternative à llama-server ?

Cherche, dans le package installé, un backend d'inférence configurable (torch /
transformers) au lieu de llama.cpp. Ne devine rien : lit le code réel.

  docker compose run --rm --no-deps omr-service python3 -m app.inspect_surya_backend

Colle toute la sortie. Supprime ce fichier ensuite.
"""
from __future__ import annotations

import os
import re
from pathlib import Path


def main() -> None:
    import surya
    root = Path(os.path.dirname(surya.__file__))
    print("surya:", getattr(surya, "__version__", "?"), "@", root)

    # 1) SETTINGS (options configurables par env — c'est là que serait un toggle).
    print("\n=== SETTINGS (options / env) ===")
    try:
        from surya.settings import settings
        mf = getattr(type(settings), "model_fields", None)
        keys = list(mf) if mf else list(vars(settings))
        for k in keys:
            try:
                print(f"  {k} = {getattr(settings, k)!r}")
            except Exception:  # noqa: BLE001
                print(f"  {k} = (?)")
    except Exception as exc:  # noqa: BLE001
        print("  settings introuvable:", type(exc).__name__, exc)

    # 2) SuryaInferenceManager : signature + attributs (backend ?).
    print("\n=== SuryaInferenceManager ===")
    mgr_cls = None
    for modpath in ("surya.common.surya", "surya.common.inference", "surya.inference",
                    "surya.recognition", "surya.common"):
        try:
            mod = __import__(modpath, fromlist=["SuryaInferenceManager"])
            mgr_cls = getattr(mod, "SuryaInferenceManager", None)
            if mgr_cls:
                print(f"trouvé dans {modpath}")
                break
        except Exception:  # noqa: BLE001
            continue
    if mgr_cls:
        import inspect
        try:
            print("  __init__:", inspect.signature(mgr_cls.__init__))
        except (TypeError, ValueError):
            pass
        print("  fichier:", inspect.getfile(mgr_cls))

    # 3) Toutes les références llama / backend / SpawnError dans le package.
    print("\n=== RÉFÉRENCES llama / backend / spawn ===")
    pat = re.compile(r"llama|LLAMA|SpawnError|backend|use_torch|transformers|"
                     r"inference_mode|engine|DISABLE_|_SERVER|onnx", re.I)
    for f in sorted(root.rglob("*.py")):
        try:
            lines = f.read_text(errors="replace").splitlines()
        except Exception:  # noqa: BLE001
            continue
        for i, line in enumerate(lines, 1):
            if pat.search(line):
                rel = f.relative_to(root)
                print(f"  {rel}:{i}: {line.strip()[:150]}")


if __name__ == "__main__":
    main()
