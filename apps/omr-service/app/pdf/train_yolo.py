"""Script d'entraînement YOLO pour la détection de symboles sol-fa.

Usage (depuis apps/omr-service) :
    python -m app.pdf.train_yolo --out /tmp/solfa_yolo --pages 200 --epochs 30

Le modèle entraîné est sauvegardé dans ``out/train/weights/best.pt``.
Copier ce fichier vers ``app/pdf/models/solfa_yolo.pt`` pour l'utiliser
dans le pipeline OCR.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Entraîne YOLOv11 sur données sol-fa synthétiques"
    )
    parser.add_argument(
        "--out",
        type=str,
        default="/tmp/solfa_yolo",
        help="Répertoire de sortie (dataset + modèle)",
    )
    parser.add_argument("--pages", type=int, default=200, help="Nombre de pages synthétiques")
    parser.add_argument("--epochs", type=int, default=30, help="Nombre d'epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Taille d'image YOLO")
    parser.add_argument("--seed", type=int, default=42, help="Seed aléatoire")
    parser.add_argument(
        "--install",
        action="store_true",
        help="Copie best.pt vers app/pdf/models/solfa_yolo.pt",
    )
    args = parser.parse_args()

    from .yolo_detect import train_solfa_yolo

    print(f"=== Entraînement YOLO sol-fa ===")
    print(f"  pages: {args.pages}, epochs: {args.epochs}, imgsz: {args.imgsz}")
    print(f"  sortie: {args.out}")

    best_path = train_solfa_yolo(
        out_dir=args.out,
        n_pages=args.pages,
        epochs=args.epochs,
        imgsz=args.imgsz,
        seed=args.seed,
    )
    print(f"\n✓ Modèle entraîné : {best_path}")

    if args.install:
        dest = Path(__file__).parent / "models" / "solfa_yolo.pt"
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(best_path, dest)
        print(f"✓ Installé : {dest}")

    return best_path


if __name__ == "__main__":
    main()
