"""Générateur de pages sol-fa synthétiques (données d'entraînement OCR).

Produit une image + annotations bounding-box parfaites à partir de notations
canoniques (``solfa-format.md``). Aucune annotation manuelle requise.

Dépendances : Pillow (déjà dans pyproject). NumPy optionnel pour le bruit.
"""
from __future__ import annotations

import io
import random
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

# Classes de glyphes sol-fa (classifieur Phase 3).
GLYPH_CLASSES = (
    "d", "r", "m", "f", "s", "l", "t",
    ":", "|", ".", ",", "-", "'",
    "di", "ri", "ra", "ma", "fi", "si", "sa", "li", "la", "ta",
)

_FONT_CANDIDATES = (
    # Polices serif prioritaires (plus proches des vrais scans sol-fa).
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
)

# Polices supplémentaires pour varier les données d'entraînement.
_EXTRA_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


@dataclass
class BBoxAnnotation:
    """Annotation d'un glyphe rendu : classe + boîte (x, y, w, h) en pixels image."""

    label: str
    x: int
    y: int
    w: int
    h: int
    voice_index: Optional[int] = None


def _load_font(size: int = 28, font_path: Optional[str] = None):
    from PIL import ImageFont

    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            pass
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _tokenize_notation(notation: str) -> List[str]:
    """Découpe une notation sol-fa en tokens (syllabes + séparateurs)."""
    # Conserve les séparateurs comme tokens isolés.
    parts = re.findall(r"[a-zA-Z]+[',_]*|[:|.,\-!]|[^:\s|.!,]+", notation)
    return [p for p in parts if p.strip()]


_LYRICS_POOL = [
    "Mi- va- vah ia- nao ka a- za",
    "me- ty sa- sa- tra ry o-",
    "lon' An- dria- na ni- tra",
    "fa ny Ray Tsi- to- ha hi",
    "hai- noa- nao no ha- ma-",
    "lia- naa- nao ka ho- dy",
    "va- va- kao ny va- va- kao",
    "ta- rai- na sy ta- la- ho",
    "fe- fi- ka man- jo ny",
    "i- va ny he- ri- nao",
    "naa- tao man- dra- ka- ri-",
    "va na dia e- fa",
]


def generate_solfa_page(
    voices: Sequence[str],
    *,
    font_path: Optional[str] = None,
    font_size: int = 28,
    noise_level: float = 0.02,
    title: str = "SYNTH",
    tonic: str = "C",
    time_sig: str = "4/4",
    margin: int = 40,
    line_gap: int = 36,
    system_gap: int = 56,
    glyph_gap: int = 8,
    page_width: int = 900,
    seed: Optional[int] = None,
    n_systems: int = 1,
) -> Tuple["Any", List[BBoxAnnotation]]:
    """PIL → image synthétique RGB + annotations bounding-box.

    ``voices`` : 1 à 4 notations canoniques (une par voix SATB).
    ``n_systems`` : nombre de systèmes sur la page (répète les voix).
    Retourne ``(image_rgb numpy ou PIL, annotations)``.
    """
    from PIL import Image, ImageDraw, ImageFilter

    rng = random.Random(seed)
    font = _load_font(font_size, font_path)
    header_font = _load_font(max(18, font_size - 4), font_path)
    lyrics_font = _load_font(max(14, font_size - 8), font_path)

    n_voices = max(1, len(voices))
    # Hauteur réaliste : en-tête + n_systems * (voix + paroles intercalées).
    voice_block_h = n_voices * (line_gap + 16)  # 16px pour les paroles
    content_h = margin * 2 + 70 + n_systems * (voice_block_h + system_gap)
    img = Image.new("RGB", (page_width, max(content_h, 200)), "white")
    draw = ImageDraw.Draw(img)
    annotations: List[BBoxAnnotation] = []

    # En-tête.
    y = margin
    draw.text((page_width // 2 - len(title) * 6, y), title, fill="black", font=header_font)
    y += 30
    header = f"Do dia {tonic}:"
    draw.text((margin, y), header, fill="black", font=lyrics_font)
    y += 30

    for sys_idx in range(n_systems):
        for vi, notation in enumerate(voices):
            x = margin
            tokens = _tokenize_notation(notation)
            for tok in tokens:
                if not tok:
                    continue
                bbox = draw.textbbox((x, y), tok, font=font)
                tw = max(1, bbox[2] - bbox[0])
                th = max(1, bbox[3] - bbox[1])
                draw.text((x, y), tok, fill="black", font=font)
                label = tok if tok in GLYPH_CLASSES else tok.lower()
                annotations.append(
                    BBoxAnnotation(
                        label=label,
                        x=int(bbox[0]),
                        y=int(bbox[1]),
                        w=int(tw),
                        h=int(th),
                        voice_index=vi,
                    )
                )
                x += tw + glyph_gap
                if x > page_width - margin:
                    break
            y += line_gap

            # Paroles intercalées (comme dans les vrais scans).
            if vi < n_voices - 1 or rng.random() > 0.3:
                lyrics = rng.choice(_LYRICS_POOL)
                draw.text((margin, y), lyrics, fill="black", font=lyrics_font)
                y += 16

        y += system_gap

    # Bruit / artefacts scan.
    if noise_level > 0:
        img = _add_scan_noise(img, noise_level, rng)

    try:
        import numpy as np

        return np.array(img), annotations
    except ImportError:
        return img, annotations


def _add_scan_noise(img, noise_level: float, rng: random.Random):
    """Bruit gaussien léger + compression JPEG simulée."""
    from PIL import Image, ImageFilter

    # Légère rotation.
    angle = rng.uniform(-0.4, 0.4)
    img = img.rotate(angle, expand=False, fillcolor="white")
    img = img.filter(ImageFilter.GaussianBlur(radius=0.3))

    try:
        import numpy as np

        arr = np.array(img).astype(np.float32)
        noise = rng.gauss(0, 1)
        # Bruit pixel-wise.
        sigma = noise_level * 255.0
        arr += np.random.default_rng(rng.randint(0, 2**31 - 1)).normal(
            0, sigma, arr.shape
        )
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
    except ImportError:
        pass

    # Round-trip JPEG.
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=rng.randint(70, 92))
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def render_glyph_crop(
    label: str,
    *,
    font_path: Optional[str] = None,
    font_size: int = 32,
    pad: int = 4,
    size: int = 32,
) -> "Any":
    """Rend un glyphe isolé en image carrée (entraînement classifieur)."""
    from PIL import Image, ImageDraw
    import numpy as np

    font = _load_font(font_size, font_path)
    tmp = Image.new("L", (size * 2, size * 2), 255)
    draw = ImageDraw.Draw(tmp)
    bbox = draw.textbbox((pad, pad), label, font=font)
    draw.text((pad, pad), label, fill=0, font=font)
    # Crop autour du glyphe.
    crop = tmp.crop(
        (
            max(0, bbox[0] - pad),
            max(0, bbox[1] - pad),
            min(tmp.width, bbox[2] + pad),
            min(tmp.height, bbox[3] + pad),
        )
    )
    crop = crop.resize((size, size), Image.Resampling.LANCZOS)
    return np.array(crop)


def generate_glyph_dataset(
    labels: Optional[Sequence[str]] = None,
    *,
    n_per_class: int = 20,
    size: int = 32,
    seed: int = 0,
) -> Tuple["Any", List[str]]:
    """Dataset (N, size, size) + labels pour entraîner / templates."""
    import numpy as np

    labels = list(labels or GLYPH_CLASSES)
    rng = random.Random(seed)
    images: List[Any] = []
    ys: List[str] = []
    for lab in labels:
        for i in range(n_per_class):
            # Varier légèrement la taille de police.
            fs = rng.randint(24, 36)
            img = render_glyph_crop(lab, font_size=fs, size=size)
            # Bruit léger.
            noise = np.random.default_rng(seed + i).normal(0, 8, img.shape)
            img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
            images.append(img)
            ys.append(lab)
    return np.stack(images), ys


def page_to_png_bytes(image) -> bytes:
    """Sérialise une page (numpy RGB ou PIL) en PNG."""
    from PIL import Image
    import numpy as np

    if hasattr(image, "save"):
        img = image
    else:
        img = Image.fromarray(np.asarray(image))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Export YOLO (images + labels .txt) pour entraînement ultralytics
# ---------------------------------------------------------------------------

# Map label → index de classe YOLO.
YOLO_CLASSES: List[str] = list(GLYPH_CLASSES)
_YOLO_CLS_INDEX = {lab: i for i, lab in enumerate(YOLO_CLASSES)}


def annotations_to_yolo(
    annotations: List[BBoxAnnotation],
    img_w: int,
    img_h: int,
) -> str:
    """Convertit les annotations en lignes YOLO ``cls cx cy w h`` (normalisées)."""
    lines: List[str] = []
    for a in annotations:
        cls = _YOLO_CLS_INDEX.get(a.label)
        if cls is None:
            # Chromatismes / labels inconnus → ignorer.
            continue
        cx = (a.x + a.w / 2.0) / img_w
        cy = (a.y + a.h / 2.0) / img_h
        nw = a.w / img_w
        nh = a.h / img_h
        lines.append(f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
    return "\n".join(lines)


def generate_yolo_dataset(
    out_dir: str,
    *,
    n_pages: int = 100,
    voices_pool: Optional[Sequence[str]] = None,
    seed: int = 42,
) -> str:
    """Génère un dataset YOLO complet (images/ + labels/ + data.yaml).

    Produit des pages avec multiples systèmes, paroles intercalées, polices
    variées et niveaux de bruit différents pour maximiser la généralisation.
    Retourne le chemin vers ``data.yaml`` (prêt pour ``yolo train data=...``).
    """
    import os
    import numpy as np
    from PIL import Image

    rng = random.Random(seed)
    os.makedirs(os.path.join(out_dir, "images", "train"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "labels", "train"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "images", "val"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "labels", "val"), exist_ok=True)

    if voices_pool is None:
        voices_pool = _DEFAULT_VOICE_POOL

    # Polices disponibles.
    all_fonts = list(_FONT_CANDIDATES) + list(_EXTRA_FONTS)
    avail_fonts = [f for f in all_fonts if os.path.exists(f)] or [None]

    n_val = max(5, n_pages // 10)
    n_train = n_pages - n_val

    for i in range(n_pages):
        split = "train" if i < n_train else "val"
        n_voices = rng.choice([2, 3, 4, 4, 4])  # Biais vers 4 voix (cas réel)
        voices = [rng.choice(voices_pool) for _ in range(n_voices)]
        tonic = rng.choice(["C", "D", "Eb", "F", "G", "A", "Bb"])
        # Varier la police, la taille et le nombre de systèmes.
        font_path = rng.choice(avail_fonts)
        font_size = rng.choice([22, 24, 26, 28, 30])
        n_systems = rng.choice([1, 2, 3, 3, 4])
        page_width = rng.choice([800, 900, 1000, 1100])
        noise = rng.uniform(0.005, 0.05)
        img_arr, anns = generate_solfa_page(
            voices,
            noise_level=noise,
            title=rng.choice(_TITLE_POOL),
            tonic=tonic,
            seed=seed + i,
            font_path=font_path,
            font_size=font_size,
            n_systems=n_systems,
            page_width=page_width,
        )
        img_h, img_w = img_arr.shape[:2]
        fname = f"page_{i:04d}"
        Image.fromarray(img_arr).save(
            os.path.join(out_dir, "images", split, f"{fname}.png")
        )
        label_txt = annotations_to_yolo(anns, img_w, img_h)
        with open(
            os.path.join(out_dir, "labels", split, f"{fname}.txt"), "w"
        ) as fh:
            fh.write(label_txt)

    yaml_path = os.path.join(out_dir, "data.yaml")
    with open(yaml_path, "w") as fh:
        fh.write(f"path: {os.path.abspath(out_dir)}\n")
        fh.write("train: images/train\n")
        fh.write("val: images/val\n")
        fh.write(f"nc: {len(YOLO_CLASSES)}\n")
        fh.write(f"names: {YOLO_CLASSES}\n")
    return yaml_path


_TITLE_POOL = [
    "MIVAVAHA", "JESOA TSY MBA MANDAO", "KRISTY VELONA",
    "FIHIRANA FAHASIVY", "HALELOIA", "NY TOMPO MAHATOKY",
    "ISAORANA NY ANARANAO", "MANDRA-PIHAVIN'NY TOMPO",
    "ENDREY NY FITIAVAN'NY RAY", "FA MASINA",
]


# Pool de lignes sol-fa réalistes pour la génération.
_DEFAULT_VOICE_POOL = [
    "d : r : m : f | s : l : t : d'",
    ".m : m.s : t : t.l | s : s.f : m : m.r",
    "d : - : m.r : d | t, : - : r : -",
    "s : -.f : m.r : -.r | l : -.s : f.m : s.f",
    "d : d : d : d | m : m : m : m",
    "s, : s, : d : d | r : r : m : -",
    "d : t,.d : r : d | s : -.f : m.r : -.r",
    "f : m : r : d | t, : l, : s, : d",
    "m : - : s : - | d' : - : t : -",
    "d.r : m.f : s : l | t : d' : - : -",
    "m,.f : s : : s | f . , m : r : d",
    "s : -.s | f,. m : f,. s, | d : - . d | r,. t : d,. r",
    "d : -.d | d,. t : d . r | d : : s | l : : l",
    "s, . s | d : : s | d, . d | d : d . s,",
    "m : -.m | r,. m : r . d | t, : : m | f : : f",
    "d : d | d . s, : d . d | t, : t, . t, | d : d . d",
    "l, : -.l, | s, : s, . s, | s, : : d | d : : d",
    "d : r : m : f | s : : s | l : l : s : -",
    "t : t : d' : d' | t : -.l : s.f : m",
    "s : s | f . , m | d : r , t : | l : : s",
]
