"""Détection de symboles sol-fa via YOLOv11.

Pipeline :
  1. ``train_solfa_yolo()`` → entraîne sur données synthétiques (synth.py)
  2. ``SolfaYoloDetector`` → charge un modèle entraîné et détecte
  3. ``detections_to_runs()`` → convertit en ``Run`` (même contrat que Tesseract)

Le modèle est entraîné sur ~13 classes (d r m f s l t : | . , - ')
et fournit les bounding boxes + classes avec confiance.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from .extract import Run
from .synth import YOLO_CLASSES

# Chemin par défaut du modèle entraîné (dans le conteneur).
_DEFAULT_MODEL_PATH = Path(__file__).parent / "models" / "solfa_yolo.pt"
_MODEL_ENV = "SOLFA_YOLO_MODEL"


@dataclass
class Detection:
    """Un symbole détecté par YOLO."""

    label: str
    confidence: float
    x: float
    y: float
    w: float
    h: float


def yolo_available() -> bool:
    try:
        from ultralytics import YOLO  # noqa: F401

        return True
    except ImportError:
        return False


def train_solfa_yolo(
    *,
    out_dir: Optional[str] = None,
    n_pages: int = 200,
    epochs: int = 30,
    imgsz: int = 640,
    seed: int = 42,
    model_base: str = "yolo11n.pt",
) -> str:
    """Génère des données synthétiques et entraîne YOLOv11.

    Retourne le chemin vers le meilleur modèle (``best.pt``).
    """
    from ultralytics import YOLO

    from .synth import generate_yolo_dataset

    if out_dir is None:
        out_dir = tempfile.mkdtemp(prefix="solfa_yolo_")

    data_dir = os.path.join(out_dir, "dataset")
    yaml_path = generate_yolo_dataset(data_dir, n_pages=n_pages, seed=seed)

    model = YOLO(model_base)
    results = model.train(
        data=yaml_path,
        epochs=epochs,
        imgsz=imgsz,
        batch=16,
        project=out_dir,
        name="train",
        exist_ok=True,
        verbose=False,
    )

    best_path = os.path.join(out_dir, "train", "weights", "best.pt")
    if not os.path.exists(best_path):
        # Repli sur last.pt.
        best_path = os.path.join(out_dir, "train", "weights", "last.pt")
    return best_path


class SolfaYoloDetector:
    """Détecteur sol-fa basé sur un modèle YOLOv11 entraîné."""

    def __init__(self, model_path: Optional[str] = None):
        from ultralytics import YOLO

        if model_path is None:
            model_path = os.environ.get(_MODEL_ENV, str(_DEFAULT_MODEL_PATH))
        self.model_path = model_path
        self._model: Optional[Any] = None
        self.classes = list(YOLO_CLASSES)

    def _load(self):
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self.model_path)
        return self._model

    @property
    def is_ready(self) -> bool:
        return os.path.exists(self.model_path)

    def detect(
        self,
        image,
        *,
        conf: float = 0.25,
        imgsz: int = 640,
    ) -> List[Detection]:
        """Détecte les symboles sol-fa dans une image (BGR numpy ou chemin).

        Retourne une liste de ``Detection`` triée par position (y puis x).
        """
        model = self._load()
        results = model.predict(
            image, conf=conf, imgsz=imgsz, verbose=False, max_det=2000
        )
        dets: List[Detection] = []
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls_idx = int(box.cls[0].item())
                label = (
                    self.classes[cls_idx]
                    if cls_idx < len(self.classes)
                    else "?"
                )
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                dets.append(
                    Detection(
                        label=label,
                        confidence=float(box.conf[0].item()),
                        x=x1,
                        y=y1,
                        w=x2 - x1,
                        h=y2 - y1,
                    )
                )
        dets.sort(key=lambda d: (d.y, d.x))
        return dets


def detections_to_runs(
    dets: List[Detection],
    *,
    page_h: float,
    y_offset: float = 0.0,
) -> List[Run]:
    """Convertit les détections YOLO en ``Run`` (même contrat que Tesseract).

    Les coordonnées sont inversées en Y (PDF-like : y croissant vers le haut).
    """
    runs: List[Run] = []
    for d in dets:
        cy = d.y + d.h / 2.0
        pdf_y = y_offset + (page_h - cy)
        runs.append(
            Run(
                y=round(pdf_y, 1),
                x=round(d.x, 1),
                font="yolo",
                text=d.label,
            )
        )
    return runs


def yolo_ocr_page(
    bgr,
    detector: SolfaYoloDetector,
    *,
    y_offset: float = 0.0,
    conf: float = 0.10,
    imgsz: int = 2048,
) -> List[Run]:
    """Pipeline YOLO complet pour une page : détection → runs.

    Résolution 2048 par défaut pour capter les petits symboles sol-fa.
    """
    page_h = float(bgr.shape[0])
    dets = detector.detect(bgr, conf=conf, imgsz=imgsz)
    return detections_to_runs(dets, page_h=page_h, y_offset=y_offset)
