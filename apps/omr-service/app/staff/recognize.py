"""Reconnaissance portée (solfège occidental) via Audiveris → MusicXML → sol-fa."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Tuple, Union

from .consolidate import consolidate_omr_voices
from ..progress import ProgressFn, progress
from ..solfa.from_musicxml import MusicXmlError, read_musicxml
from ..solfa.model import Measure, NoteEl, ScoreModel
from ..solfa.musicxml import to_musicxml_multi
from ..solfa.rhythm import MeterError, classify_meter, split_duration
from ..solfa.to_solfa import to_solfa


def _pad_to_equal_measures(models: List[ScoreModel]) -> None:
    """Aligne toutes les voix sur le même nombre de mesures (silences de mesure
    pleine) pour un MusicXML SATB cohérent sous OSMD. La capacité vient de
    ``classify_meter`` (``beats*divisions`` serait faux en mètre composé/à la croche)."""
    if not models:
        return
    target = max(len(m.measures) for m in models)
    for model in models:
        try:
            cap = classify_meter(model.beats, model.beat_type).measure_divisions
        except MeterError:
            cap = model.beats * model.divisions
        while len(model.measures) < target:
            notes = [
                NoteEl(is_rest=True, duration=v, note_type=t, dots=d)
                for v, t, d in split_duration(cap)
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


def _call_audiveris_http(data: bytes, filename: str) -> str:
    """POST multipart vers audiveris-service → musicxml text."""
    url = _audiveris_url()
    if not url:
        raise StaffRecognizeError("AUDIVERIS_URL non configuré")
    boundary = "moozika-audiveris-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{url}/recognize",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=int(os.environ.get("AUDIVERIS_TIMEOUT", "1800"))) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except json.JSONDecodeError:
            pass
        detail = _clean_jvm_noise(detail) or "reconnaissance échouée"
        raise StaffRecognizeError(f"Audiveris : {detail}") from exc
    except OSError as exc:
        raise StaffRecognizeError(
            f"service Audiveris injoignable ({url}) — "
            f"lancer « docker compose up audiveris »"
        ) from exc

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


def _fetch_musicxml(data: bytes, filename: str) -> str:
    """Appelle Audiveris (HTTP ou local) et renvoie le MusicXML texte."""
    url = _audiveris_url()
    if url and _audiveris_available():
        try:
            return _call_audiveris_http(data, filename)
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
    min_cell: int = 2,
    time_override: "tuple[int, int] | None" = None,
    on_chord: str = "split",
    on_progress: ProgressFn = None,
) -> dict:
    """PDF portée → même forme que pdf_to_score (header, voices, musicxml).

    ``min_cell`` : maille rythmique du texte sol-fa (2 = croche, défaut, pour
    absorber le jitter des durées Audiveris ; 1 = double-croche, fidèle mais
    plus fragmenté).
    ``time_override`` : force la signature (ex. (10, 8)) — le mètre Audiveris est
    peu fiable ; à défaut, il est inféré du contenu (cf. read_musicxml).
    ``on_chord`` : 'split' (défaut) scinde les accords de portée en 2 voix pour
    récupérer le SATB condensé (T+B, S+A) ; 'top' ne garde que la note du haut."""
    progress(
        on_progress,
        phase="audiveris",
        pct=20,
        message="Reconnaissance portée (Audiveris)…",
    )
    musicxml = _fetch_musicxml(data, filename)
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

    models = consolidate_omr_voices(result.models)
    ts = result.predominant_time or (models[0].beats, models[0].beat_type)
    for m in models:
        m.beats, m.beat_type = ts[0], ts[1]
    _pad_to_equal_measures(models)
    display_title = title or Path(filename).stem.replace("_", " ").replace("-", " ")
    # MusicXML régénéré depuis les voix SATB nettoyées (et non le brut Audiveris)
    # -> l'aperçu OSMD colle au sol-fa affiché (mètre, clefs, voix, titre corrigés).
    clean_musicxml = to_musicxml_multi(models, title=display_title)
    warnings = list(result.warnings)
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
