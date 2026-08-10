# Image multi-stage : `test` (lance la suite) et `runtime` (sert l'API).
#
#   docker build --target test    -t moozika-omr-test .   && docker run --rm moozika-omr-test
#   docker build --target runtime -t moozika-omr      .   && docker run -p 8000:8000 moozika-omr
#
# (ou via docker compose : voir compose.yml à la racine)

FROM python:3.12-slim AS base
WORKDIR /app

# Tesseract (fallback OCR) + libgl pour OpenCV/ultralytics.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
# torch CPU-only pour réduire la taille de l'image.
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu .

# Pré-télécharge le modèle TrOCR (évite download à chaque run).
RUN python -c "\
from transformers import ViTImageProcessor, VisionEncoderDecoderModel, XLMRobertaTokenizer; \
ViTImageProcessor.from_pretrained('microsoft/trocr-small-printed'); \
XLMRobertaTokenizer.from_pretrained('microsoft/trocr-small-printed'); \
VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-small-printed'); \
print('TrOCR model cached')"

# Pré-télécharge les modèles PaddleOCR (lecteur sol-fa scanné) : évite le
# download ~80 Mo à la 1re requête via l'interface. oneDNN désactivé (bug PIR).
RUN FLAGS_use_mkldnn=0 python -c "\
import numpy as np; from paddleocr import PaddleOCR; \
ocr = PaddleOCR(enable_mkldnn=False, use_textline_orientation=False, lang='en'); \
ocr.predict(np.full((64, 256, 3), 255, dtype=np.uint8)); \
print('PaddleOCR models cached')"

# --- Étape de test ----------------------------------------------------------
FROM base AS test
COPY tests ./tests
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]

# --- Étape d'exécution : API FastAPI ---------------------------------------
FROM base AS runtime
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
