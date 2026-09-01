"""Reconnaissance portée (solfège occidental) via Audiveris → MusicXML → sol-fa."""
from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Tuple, Union

from .consolidate import consolidate_omr_voices
from ..cancel import CancelFn, Cancelled, check
from ..progress import ProgressFn, progress
from ..solfa.from_musicxml import MusicXmlError, read_musicxml
from ..solfa.model import Measure, NoteEl, ScoreModel
from ..solfa.musicxml import to_musicxml_multi
from ..solfa.rhythm import DIVISIONS_PER_BEAT, MeterError, classify_meter, split_duration
from ..solfa.to_solfa import to_solfa


def _pad_to_equal_measures(models: List[ScoreModel]) -> None:
    """Aligne toutes les voix sur le même nombre de mesures (silences de mesure
    pleine) pour un MusicXML SATB cohérent sous OSMD. La capacité vient de
    ``classify_meter`` (``beats*divisions`` serait faux en mètre composé/à la croche)."""
    if not models:
        return
    target = max(len(m.measures) for m in models)
    for model in models:
        # Échelle de grille du modèle : ×3 (noire=12) si triolets, sinon ×1.
        scale = max(1, model.divisions // DIVISIONS_PER_BEAT)
        try:
            cap = classify_meter(model.beats, model.beat_type).measure_divisions * scale
        except MeterError:
            cap = model.beats * model.divisions
        while len(model.measures) < target:
            notes = [
                NoteEl(is_rest=True, duration=v, note_type=t, dots=d)
                for v, t, d in split_duration(cap, scale)
            ]
            model.measures.append(
                Measure(number=len(model.measures) + 1, notes=notes)
            )


class StaffRecognizeError(ValueError):
    """Erreur lors de la reconnaissance Audiveris (portée → MusicXML)."""


def _clean_jvm_noise(text: str) -> str:
    """Retire les notices JVM bénignes (« Picked up JAVA_TOOL_OPTIONS… ») qui,
    sinon, masquent le vrai message d'erreur Audiveris."""
    lines = [
        ln for ln in (text or "").splitlines()
        if ln.strip() and not ln.startswith("Picked up ")
    ]
    return "\n".join(lines).strip()


def _audiveris_url() -> str | None:
    url = os.environ.get("AUDIVERIS_URL", "").strip().rstrip("/")
    return url or None


def _audiveris_available() -> bool:
    url = _audiveris_url()
    if url:
        try:
            req = urllib.request.Request(f"{url}/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = json.loads(resp.read().decode())
                return body.get("status") == "ok"
        except (OSError, json.JSONDecodeError, urllib.error.URLError):
            pass
    return shutil.which(os.environ.get("AUDIVERIS_BIN", "Audiveris")) is not None


def _call_audiveris_http(data: bytes, filename: str, is_cancelled: CancelFn = None) -> str:
    """POST multipart vers audiveris-service → musicxml text.

    Utilise ``http.client`` et non ``urllib.request.urlopen`` pour UNE raison :
    ``urlopen`` bloque jusqu'au retour et ne laisse aucune prise pour interrompre.
    Or la reconnaissance dure 15-30 min et l'annulation doit atteindre le service
    Audiveris — sinon la JVM continue de tourner dans le vide. Ici on garde une
    reference sur la connexion, qu'un veilleur ferme sur annulation : la lecture
    bloquee leve alors OSError et on remonte ``Cancelled``.
    """
    url = _audiveris_url()
    if not url:
        raise StaffRecognizeError("AUDIVERIS_URL non configuré")

    boundary = "moozika-audiveris-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

    parts = urllib.parse.urlsplit(url)
    timeout = int(os.environ.get("AUDIVERIS_TIMEOUT", "1800"))
    cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = cls(parts.hostname or "localhost", parts.port, timeout=timeout)

    stop = threading.Event()

    def _watch() -> None:
        # Scrute l'annulation et ferme la connexion : c'est ce qui debloque la lecture
        # et, cote audiveris-service, provoque la deconnexion client qui tue la JVM.
        while not stop.wait(0.5):
            if is_cancelled is not None and is_cancelled():
                # shutdown() et PAS seulement close() : sous Linux, fermer un descripteur
                # ne reveille PAS un recv() deja bloque dans un autre thread — seul
                # shutdown() le fait sortir. Mesure a l'appui : avec close() seul, la
                # lecture restait bloquee et Audiveris continuait de tourner.
                sock = getattr(conn, "sock", None)
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                try:
                    conn.close()
                except OSError:
                    pass
                return

    watcher = threading.Thread(target=_watch, daemon=True)
    watcher.start()

    base_path = parts.path.rstrip("/")
    try:
        conn.request(
            "POST",
            f"{base_path}/recognize",
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        resp = conn.getresponse()
        status = resp.status
        raw = resp.read().decode(errors="replace")
    except OSError as exc:
        # Si c'est NOUS qui avons ferme la connexion, ce n'est pas une panne du service.
        check(is_cancelled)
        raise StaffRecognizeError(
            f"service Audiveris injoignable ({url}) — "
            f"lancer « docker compose up audiveris »"
        ) from exc
    finally:
        stop.set()
        try:
            conn.close()
        except OSError:
            pass

    if status >= 400:
        detail = raw
        try:
            detail = json.loads(raw).get("detail", raw)
        except json.JSONDecodeError:
            pass
        # 499 = annulation propagee par audiveris-service : ce n'est pas un echec.
        if status == 499:
            raise Cancelled("reconnaissance annulée par le client")
        detail = _clean_jvm_noise(detail) or "reconnaissance échouée"
        raise StaffRecognizeError(f"Audiveris : {detail}")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StaffRecognizeError("réponse Audiveris illisible (JSON invalide)") from exc

    musicxml = payload.get("musicxml")
    if not musicxml:
        raise StaffRecognizeError("Audiveris n'a renvoyé aucun MusicXML")
    return musicxml


def _call_audiveris_local(data: bytes, filename: str) -> str:
    """Subprocess Audiveris local (dev hors Docker)."""
    bin_path = shutil.which(os.environ.get("AUDIVERIS_BIN", "Audiveris"))
    if not bin_path:
        raise StaffRecognizeError("binaire Audiveris local introuvable")

    suffix = Path(filename).suffix or ".pdf"
    with tempfile.TemporaryDirectory(prefix="moozika-staff-") as tmp:
        tmp_path = Path(tmp)
        inp = tmp_path / f"input{suffix}"
        out = tmp_path / "out"
        inp.write_bytes(data)
        out.mkdir()
        cmd = [
            bin_path,
            "-batch",
            "-export",
            "-output",
            str(out),
            "-constant",
            "org.audiveris.omr.sheet.BookManager.useSeparateBookFolders=false",
            "--",
            str(inp),
        ]
        env = {**os.environ, "JAVA_TOOL_OPTIONS": "-Djava.awt.headless=true"}
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
        if proc.returncode != 0:
            detail = _clean_jvm_noise(proc.stderr or proc.stdout) or "échec Audiveris"
            raise StaffRecognizeError(detail[-1500:])

        for pattern in ("*.mxl", "*.musicxml", "*.xml"):
            found = sorted(out.rglob(pattern))
            if found:
                raw = found[0].read_bytes()
                if found[0].suffix.lower() == ".mxl":
                    from ..solfa.from_musicxml import _unzip_mxl  # noqa: SLF001
                    raw = _unzip_mxl(raw)
                return raw.decode("utf-8", errors="replace")
        raise StaffRecognizeError("Audiveris n'a produit aucun MusicXML")


def _fetch_musicxml(data: bytes, filename: str, is_cancelled: CancelFn = None) -> str:
    """Appelle Audiveris (HTTP ou local) et renvoie le MusicXML texte."""
    url = _audiveris_url()
    if url and _audiveris_available():
        try:
            return _call_audiveris_http(data, filename, is_cancelled=is_cancelled)
        except StaffRecognizeError:
            if shutil.which(os.environ.get("AUDIVERIS_BIN", "Audiveris")):
                return _call_audiveris_local(data, filename)
            raise
    if shutil.which(os.environ.get("AUDIVERIS_BIN", "Audiveris")):
        return _call_audiveris_local(data, filename)
    raise StaffRecognizeError(
        "Audiveris indisponible. Lancer le stack Docker "
        "(docker compose up audiveris omr-service) ou installer Audiveris localement."
    )


def staff_pdf_to_musicxml(data: bytes, filename: str = "score.pdf") -> Tuple[str, List[str]]:
    """PDF portée → texte MusicXML + avertissements du lecteur sol-fa."""
    xml = _fetch_musicxml(data, filename)
    result = read_musicxml(xml, quantize_rhythm=True)
    return xml, result.warnings


def staff_pdf_to_score(
    data: bytes,
    filename: str = "score.pdf",
    title: str = "",
    min_cell: int = 1,
    time_override: "tuple[int, int] | None" = None,
    on_chord: str = "split",
    on_progress: ProgressFn = None,
    is_cancelled: CancelFn = None,
) -> dict:
    """PDF portée → même forme que pdf_to_score (header, voices, musicxml).

    ``min_cell`` : maille rythmique du texte sol-fa (1 = double-croche, défaut,
    fidèle : sinon un temps « croche + 2 doubles-croches » perd la 3e note ;
    2 = croche, plus lissé mais supprime toutes les doubles-croches).
    ``time_override`` : force la signature (ex. (10, 8)) — le mètre Audiveris est
    peu fiable ; à défaut, il est inféré du contenu (cf. read_musicxml).
    ``on_chord`` : 'split' (défaut) scinde les accords de portée en 2 voix pour
    récupérer le SATB condensé (T+B, S+A) ; 'top' ne garde que la note du haut."""
    # Dernier point de controle avant la JVM. Une fois l'appel parti on ne peut plus
    # l'interrompre depuis ici (c'est l'objet de N3, cote audiveris-service) ; au moins on
    # ne demarre pas 15-30 min de reconnaissance pour un client deja parti.
    check(is_cancelled)
    progress(
        on_progress,
        phase="audiveris",
        pct=20,
        message="Reconnaissance portée (Audiveris)…",
    )
    musicxml = _fetch_musicxml(data, filename, is_cancelled=is_cancelled)
    progress(
        on_progress,
        phase="convert",
        pct=75,
        message="Conversion MusicXML → sol-fa…",
    )
    result = read_musicxml(
        musicxml, quantize_rhythm=True, time_override=time_override, on_chord=on_chord
    )
    if not result.models:
        raise StaffRecognizeError("MusicXML Audiveris sans voix exploitable")

    warnings = list(result.warnings)
    models = consolidate_omr_voices(result.models, warnings=warnings)
    # Mètre d'OUVERTURE affiché = celui de la 1re mesure (model.beats, posé par
    # from_musicxml), PAS le prédominant : sur une pièce à mètre variable (jubilate
    # ouvre en 10/8 puis 6/8 puis 4/4), le prédominant 4/4 afficherait à tort 4/4
    # en tête et un faux changement dès la m1. Les changements en cours de pièce
    # restent portés par Measure.time_signature.
    ts = (models[0].beats, models[0].beat_type)
    for m in models:
        m.beats, m.beat_type = ts[0], ts[1]
    _pad_to_equal_measures(models)
    display_title = title or Path(filename).stem.replace("_", " ").replace("-", " ")
    # MusicXML régénéré depuis les voix SATB nettoyées (et non le brut Audiveris)
    # -> l'aperçu OSMD colle au sol-fa affiché (mètre, clefs, voix, titre corrigés).
    clean_musicxml = to_musicxml_multi(models, title=display_title)
    if len(models[0].measures) < 70:
        warnings.append(
            f"[omr] {len(models[0].measures)} mesures reconnues — "
            "les PDF scannés perdent souvent des mesures vs la portée originale "
            "(qualité Audiveris, pas le convertisseur sol-fa)."
        )

    progress(on_progress, phase="convert", pct=95, message="Génération MusicXML…")
    return {
        "header": {
            "title": display_title,
            "tonic": models[0].tonic,
            "timeSignature": {"beats": ts[0], "beatType": ts[1]},
            "tempo": models[0].tempo,
        },
        "voices": [
            {
                "name": m.part_name,
                "notation": to_solfa(m, min_cell=min_cell),
                "model": m.to_dict(),
            }
            for m in models
        ],
        "musicxml": clean_musicxml,
        "warnings": warnings,
        "source": "audiveris",
    }
