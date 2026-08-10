# Audiveris OMR — portée / solfège PDF → MusicXML (.mxl)
# Wrapper HTTP minimal autour du CLI Audiveris (architecture.md §5 Pipeline A).
#
# Le .deb officiel échoue en Docker (postinst xdg-desktop-menu) : extraction
# manuelle via dpkg-deb -x, le paquet embarque son propre JRE.

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget ca-certificates \
        python3 python3-pip \
        ghostscript \
        libgtk-3-0 libgdk-pixbuf2.0-0 libpango-1.0-0 libcairo2 libasound2 \
        libx11-6 libxext6 libxrender1 libxtst6 libxi6 fontconfig \
    && rm -rf /var/lib/apt/lists/*
# ghostscript : Audiveris 5.11 délègue le rendu PDF à un sous-processus gs
# (le .deb extrait via dpkg-deb -x ne résout pas cette dépendance). Sert aussi
# au prétraitement (rendu droit + suréchantillonné) dans app/main.py.

ARG AUDIVERIS_VERSION=5.11.0
RUN wget -q \
    "https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/Audiveris-${AUDIVERIS_VERSION}-ubuntu22.04-x86_64.deb" \
    -O /tmp/audiveris.deb \
    && mkdir -p /opt \
    && dpkg-deb -x /tmp/audiveris.deb / \
    && rm /tmp/audiveris.deb \
    && ln -sf /opt/audiveris/bin/Audiveris /usr/local/bin/Audiveris

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY app ./app

ENV AUDIVERIS_BIN=/opt/audiveris/bin/Audiveris
ENV JAVA_TOOL_OPTIONS="-Djava.awt.headless=true"
EXPOSE 8081
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
