"""Classifieur de glyphes sol-fa (composantes connexes → label).

Par défaut : matching de templates générés par ``synth`` (stdlib + OpenCV/numpy,
pas de torch). Optionnel : backend Torch (MobileNetV3-Small) si ``torch`` et
``torchvision`` sont installés.

Intégration : ``classify_low_conf_glyphs`` peut remplacer les lectures Tesseract
à faible confiance (``conf < threshold``) une fois un modèle entraîné.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .synth import GLYPH_CLASSES, generate_glyph_dataset, render_glyph_crop

# Seuil de confiance Tesseract sous lequel on consulte le classifieur.
DEFAULT_CONF_THRESHOLD = 40.0


@dataclass
class GlyphPrediction:
    label: str
    confidence: float
    x: int
    y: int
    w: int
    h: int


def extract_connected_components(
    binary,
    *,
    min_area: int = 8,
    max_area: Optional[int] = None,
) -> List[Tuple[Any, Tuple[int, int, int, int]]]:
    """OpenCV ``findContours`` → liste de ``(crop_gray, (x, y, w, h))``."""
    import cv2
    import numpy as np

    if binary is None or getattr(binary, "size", 0) == 0:
        return []
    # Contours sur l'inverse (texte noir sur fond blanc).
    inv = 255 - binary if int(np.mean(binary)) > 127 else binary
    contours, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h_img, w_img = binary.shape[:2]
    if max_area is None:
        max_area = h_img * w_img // 4
    out: List[Tuple[Any, Tuple[int, int, int, int]]] = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        if area < min_area or area > max_area:
            continue
        if w < 2 or h < 2:
            continue
        crop = binary[y : y + h, x : x + w]
        out.append((crop, (x, y, w, h)))
    # Ordre lecture : haut → bas, gauche → droite.
    out.sort(key=lambda item: (item[1][1], item[1][0]))
    return out


def _normalize_crop(crop, size: int = 32):
    import cv2
    import numpy as np

    if crop is None or crop.size == 0:
        return np.full((size, size), 255, dtype=np.uint8)
    resized = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)
    if resized.dtype != np.uint8:
        resized = resized.astype(np.uint8)
    return resized


class TemplateGlyphClassifier:
    """Classifieur par corrélation / distance L2 contre des templates synthétiques.

    Aucune dépendance torch. Suffisant pour remplacer les lectures Tesseract
    à faible confiance sur un alphabet ~20 classes.
    """

    def __init__(self, size: int = 32, n_per_class: int = 8, seed: int = 0):
        import numpy as np

        images, labels = generate_glyph_dataset(
            GLYPH_CLASSES, n_per_class=n_per_class, size=size, seed=seed
        )
        self.size = size
        self.labels = list(labels)
        # Moyenne par classe pour un matching rapide.
        by_class: Dict[str, List[Any]] = {}
        for img, lab in zip(images, labels):
            by_class.setdefault(lab, []).append(img.astype(np.float32))
        self.templates: Dict[str, Any] = {
            lab: np.mean(np.stack(arrs), axis=0) for lab, arrs in by_class.items()
        }

    def predict(self, crop, *, original_w: int = 0, original_h: int = 0) -> Tuple[str, float]:
        """Prédit le label d'un crop.

        Combine heuristiques géométriques (ponctuation/barres) et template
        matching (notes). Les chromatismes (di, ri, …) ne sont renvoyés que
        pour des composantes clairement multi-caractères.
        """
        import numpy as np

        # Heuristiques géométriques pour ponctuation/barres.
        if original_w > 0 and original_h > 0:
            geo = _geometric_classify(original_w, original_h)
            if geo is not None:
                return geo

        norm = _normalize_crop(crop, self.size).astype(np.float32)
        best_lab = "?"
        best_score = float("inf")
        # Ne matcher que les classes diatoniques + séparateurs pour un
        # caractère unique (les chromatismes sont des bigrammes).
        single_char_ok = original_w > 0 and original_w < 25
        for lab, tmpl in self.templates.items():
            if single_char_ok and len(lab) > 1:
                continue
            dist = float(np.mean((norm - tmpl) ** 2))
            if dist < best_score:
                best_score = dist
                best_lab = lab
        conf = max(0.0, 1.0 - best_score / (255.0 ** 2))
        return best_lab, conf

    def predict_components(self, binary) -> List[GlyphPrediction]:
        preds: List[GlyphPrediction] = []
        for crop, (x, y, w, h) in extract_connected_components(binary):
            lab, conf = self.predict(crop, original_w=w, original_h=h)
            preds.append(GlyphPrediction(label=lab, confidence=conf, x=x, y=y, w=w, h=h))
        return preds


def torch_available() -> bool:
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401
    except ImportError:
        return False
    return True


class TorchGlyphClassifier:
    """MobileNetV3-Small fine-tuné sur glyphes sol-fa (torch optionnel).

    Nécessite ``torch`` + ``torchvision``. Charger des poids via ``load(path)``.
    """

    def __init__(self, n_classes: Optional[int] = None, size: int = 32):
        if not torch_available():
            raise ImportError(
                "TorchGlyphClassifier requiert torch et torchvision "
                "(pip install torch torchvision)"
            )
        import torch
        import torch.nn as nn
        from torchvision.models import mobilenet_v3_small

        self.size = size
        self.classes = list(GLYPH_CLASSES)
        n_classes = n_classes or len(self.classes)
        self.model = mobilenet_v3_small(weights=None)
        in_features = self.model.classifier[-1].in_features
        self.model.classifier[-1] = nn.Linear(in_features, n_classes)
        self.model.eval()
        self._device = torch.device("cpu")

    def load(self, path: str) -> None:
        import torch

        state = torch.load(path, map_location=self._device)
        self.model.load_state_dict(state)
        self.model.eval()

    def save(self, path: str) -> None:
        import torch

        torch.save(self.model.state_dict(), path)

    def predict(self, crop) -> Tuple[str, float]:
        import torch
        import torch.nn.functional as F
        import numpy as np

        norm = _normalize_crop(crop, self.size).astype(np.float32) / 255.0
        # MobileNet attend 3 canaux.
        rgb = np.stack([norm, norm, norm], axis=0)
        tensor = torch.from_numpy(rgb).unsqueeze(0)
        with torch.no_grad():
            logits = self.model(tensor)
            probs = F.softmax(logits, dim=1)[0]
            idx = int(torch.argmax(probs).item())
            conf = float(probs[idx].item())
        label = self.classes[idx] if idx < len(self.classes) else "?"
        return label, conf

    def train_on_synthetic(
        self,
        *,
        n_per_class: int = 40,
        epochs: int = 5,
        lr: float = 1e-3,
        seed: int = 0,
    ) -> float:
        """Entraînement rapide sur données synthétiques. Retourne la loss finale."""
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
        import numpy as np

        images, labels = generate_glyph_dataset(
            self.classes, n_per_class=n_per_class, size=self.size, seed=seed
        )
        label_to_idx = {lab: i for i, lab in enumerate(self.classes)}
        ys = np.array([label_to_idx[l] for l in labels], dtype=np.int64)
        xs = images.astype(np.float32) / 255.0
        xs = np.stack([xs, xs, xs], axis=1)  # (N, 3, H, W)
        ds = TensorDataset(torch.from_numpy(xs), torch.from_numpy(ys))
        loader = DataLoader(ds, batch_size=32, shuffle=True)
        opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        crit = nn.CrossEntropyLoss()
        self.model.train()
        last_loss = 0.0
        for _ in range(epochs):
            for xb, yb in loader:
                opt.zero_grad()
                loss = crit(self.model(xb), yb)
                loss.backward()
                opt.step()
                last_loss = float(loss.item())
        self.model.eval()
        return last_loss


def _geometric_classify(w: int, h: int) -> Optional[Tuple[str, float]]:
    """Heuristiques géométriques pour ponctuation et barres."""
    aspect = h / max(1, w)
    area = w * h
    # Très petit et compact → point.
    if area < 80 and w < 8 and h < 8:
        return ".", 0.85
    # Petit, plus haut que large → deux-points ou virgule.
    if area < 150 and w < 8:
        if h > 10 and aspect > 1.8:
            return ":", 0.80
        if h < 10:
            return ",", 0.75
    # Très haut et fin → barre de mesure.
    if aspect > 5.0 and w < 8:
        return "|", 0.85
    # Très plat → tiret.
    if aspect < 0.25 and h < 6:
        return "-", 0.80
    # Apostrophe : très petit en haut.
    if area < 60 and h < 8 and w < 6:
        return "'", 0.70
    return None


def get_default_classifier() -> TemplateGlyphClassifier:
    """Classifieur prêt à l'emploi (templates synthétiques, sans torch)."""
    return TemplateGlyphClassifier()


def classify_band_glyphs(
    binary,
    classifier: Optional[TemplateGlyphClassifier] = None,
) -> List[GlyphPrediction]:
    """Extrait et classifie les glyphes d'une bande binarisée."""
    clf = classifier or get_default_classifier()
    return clf.predict_components(binary)
