"""API FastAPI du service de reconnaissance.

Point d'entrée unique appelé par le backend Symfony (jamais par le navigateur
directement). Pipelines :
  - sol-fa texte / PDF sol-fa malgache ;
  - portée (solfège occidental) via Audiveris → MusicXML → sol-fa éditable.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import urllib.error
import urllib.request
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


def _parse_time(spec: str | None) -> "tuple[int, int] | None":
    """« 10/8 » -> (10, 8). None/invalide -> None (on infère alors le mètre)."""
    if not spec:
        return None
    try:
        nb, nbt = spec.split("/")
        return int(nb), int(nbt)
    except ValueError:
        return None

from .pdf import PdfSolfaError, pdf_to_score
from .solfa import parse_solfa, to_musicxml, to_musicxml_multi
from .solfa.from_musicxml import MusicXmlError, read_musicxml, read_musicxml_metadata
from .solfa.model import ScoreModel
from .solfa.parser import ParseError
from .solfa.to_solfa import to_solfa
from .staff.recognize import StaffRecognizeError, staff_pdf_to_score

app = FastAPI(title="Moozika OMR Service", version="0.2.0")

# Heartbeat fréquent : proxies (Next/nginx) et Chrome coupent sinon les
# connexions muettes → net::ERR_NETWORK_IO_SUSPENDED.
_HEARTBEAT_SEC = 5.0
_SENTINEL = object()


class SolfaParseRequest(BaseModel):
    notation: str = Field(..., description="Notation sol-fa tonique")
    tonic: str = Field("C", description="Tonique déclarée (Doh = X), ex. C, F, Bb")
    doh_octave: int = Field(4, ge=0, le=8, description="Octave scientifique du doh")
    clef: str = Field("treble", pattern="^(treble|bass)$")
    beats: int | None = Field(
        None,
        description=(
            "Numérateur de la signature (ex. 10 pour 10/8). Fourni, il autorise "
            "les mètres composés/irréguliers et évite que le re-parse ne retombe "
            "sur 4/4 (ex. 10/8 édité → 10/4 rejeté). Absent = déduit du contenu."
        ),
    )
    beat_type: int = Field(4, description="Dénominateur de la signature (4, 8, 16…)")
    lyrics: str | None = Field(
        None,
        description=(
            "Paroles (optionnel). Même structure que la notation : barres | "
            "et séparateurs : / !. Ex. : 'Hi- : tahy : a- : nao | a- : nie : ny : Tom-'"
        ),
    )
    triplets: list[dict] | None = Field(
        None,
        description=(
            "Triolets annotés (optionnel) : "
            "[{startMeasure, startBeat, spanBeats}] 0-based. "
            "Notation cellule = 3 syllabes collées (ex. drm)."
        ),
    )


class SolfaParseResponse(BaseModel):
    model: dict
    musicxml: str


class FromModelsRequest(BaseModel):
    models: list[dict] = Field(..., description="Liste de ScoreModel.to_dict()")
    title: str = Field("", description="Titre de la partition MusicXML")
    composer: str = Field("", description="Compositeur")
    work: str = Field("", description="Numéro d'œuvre (work-number)")


class FromModelsResponse(BaseModel):
    musicxml: str
    voices: list[dict] = Field(default_factory=list)


def _sse_line(event: str, data: Dict[str, Any]) -> str:
    """Formate un événement SSE (event + data JSON)."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@app.get("/health")
def health() -> dict:
    audiveris_url = os.environ.get("AUDIVERIS_URL", "").strip().rstrip("/")
    audiveris_status = "not_configured"
    if audiveris_url:
        try:
            req = urllib.request.Request(f"{audiveris_url}/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                audiveris_status = json.loads(resp.read().decode()).get("status", "ok")
        except (OSError, json.JSONDecodeError, urllib.error.URLError):
            audiveris_status = "unavailable"
    return {"status": "ok", "audiveris": audiveris_status}


@app.post("/musicxml/from-models", response_model=FromModelsResponse)
def musicxml_from_models(req: FromModelsRequest) -> FromModelsResponse:
    """Régénère un MusicXML multi-voix depuis des ScoreModel JSON (édition)."""
    if not req.models:
        raise HTTPException(status_code=422, detail="models[] est requis")
    try:
        models = [ScoreModel.from_dict(m) for m in req.models]
        xml = to_musicxml_multi(
            models,
            title=req.title or "",
            composer=req.composer or "",
            work=req.work or "",
        )
        voices = [
            {
                "name": m.part_name,
                "notation": to_solfa(m),
                "model": m.to_dict(),
            }
            for m in models
        ]
    except (TypeError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"modèle invalide: {exc}") from exc
    return FromModelsResponse(musicxml=xml, voices=voices)


@app.post("/solfa/parse", response_model=SolfaParseResponse)
def solfa_parse(req: SolfaParseRequest) -> SolfaParseResponse:
    try:
        score = parse_solfa(
            req.notation,
            tonic=req.tonic,
            doh_octave=req.doh_octave,
            clef=req.clef,
            beats=req.beats,
            beat_type=req.beat_type,
            lyrics=req.lyrics,
            triplets=req.triplets,
        )
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SolfaParseResponse(model=score.to_dict(), musicxml=to_musicxml(score))


@app.post("/pdf/parse")
async def pdf_parse(
    file: UploadFile = File(...),
    tonic: str | None = Form(None),
) -> dict:
    """Import PDF unifié : sol-fa malgache ou portée (Audiveris → sol-fa éditable).

    ``tonic`` (optionnel, ex. « A ») force la tonique du sol-fa scanné quand
    l'en-tête « Do dia X » n'est pas lu (YOLO ne détecte pas le texte).
    """
    data = await file.read()
    try:
        return pdf_to_score(
            data, filename=file.filename or "score.pdf",
            tonic_override=(tonic.strip() if tonic else None),
        )
    except PdfSolfaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MusicXmlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/pdf/parse/stream")
async def pdf_parse_stream(
    file: UploadFile = File(...),
    tonic: str | None = Form(None),
) -> StreamingResponse:
    """Même pipeline que ``/pdf/parse``, en Server-Sent Events.

    Événements : ``progress``, ``voice``, ``done``, ``error`` — voir
    ``packages/shared-contracts/omr-stream.md``. Heartbeat commentaire SSE
    toutes les 15 s pour garder la connexion ouverte (Audiveris).
    """
    data = await file.read()
    filename = file.filename or "score.pdf"
    tonic_override = tonic.strip() if tonic else None
    out: queue.Queue = queue.Queue()

    def on_progress(event: str, payload: Dict[str, Any]) -> None:
        out.put({"event": event, **payload})

    def worker() -> None:
        try:
            result = pdf_to_score(
                data,
                filename=filename,
                tonic_override=tonic_override,
                on_progress=on_progress,
            )
            out.put({"event": "done", "result": result})
        except (PdfSolfaError, StaffRecognizeError, MusicXmlError) as exc:
            out.put({"event": "error", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 — surface au client SSE
            out.put({"event": "error", "detail": str(exc)})
        finally:
            out.put(_SENTINEL)

    # Premier event avant le thread (chargement Paddle peut être long et silencieux).
    out.put(
        {
            "event": "progress",
            "phase": "detect",
            "pct": 1,
            "message": "Fichier reçu, démarrage…",
        }
    )
    threading.Thread(target=worker, daemon=True).start()

    async def generate() -> AsyncIterator[bytes]:
        # Commentaire SSE immédiat → TTFB < 100 ms côté proxy/navigateur.
        yield b": connected\n\n"
        while True:
            try:
                item = await asyncio.to_thread(out.get, True, _HEARTBEAT_SEC)
            except queue.Empty:
                yield b": ping\n\n"
                continue
            if item is _SENTINEL:
                break
            event = item.pop("event")
            yield _sse_line(event, item).encode("utf-8")
            if event in ("done", "error"):
                while True:
                    try:
                        drained = out.get_nowait()
                    except queue.Empty:
                        break
                    if drained is _SENTINEL:
                        break
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/recognize")
async def recognize(
    file: UploadFile = File(...),
    time: str | None = Form(None),
    tonic: str | None = Form(None),
) -> dict:
    """Alias explicite pour l'import portée (Audiveris) ou sol-fa PDF.

    Retourne ``{header, voices, musicxml, source, warnings?}`` — même forme
    que ``/pdf/parse``. ``source`` vaut ``audiveris`` ou ``solfa_pdf``.
    ``time`` (ex. « 10/8 ») force le mètre ; ``tonic`` (ex. « A ») force la
    tonique du sol-fa scanné.
    """
    data = await file.read()
    filename = file.filename or "score.pdf"
    tonic_override = tonic.strip() if tonic else None
    try:
        if data.startswith(b"%PDF"):
            from .pdf.detect import detect_pdf_kind
            kind = detect_pdf_kind(data)
            if kind == "staff_notation":
                # Portée GRAVÉE déclarée → Audiveris direct (override de mesure possible).
                return staff_pdf_to_score(
                    data, filename=filename, time_override=_parse_time(time)
                )
            # solfa_text / scanned / unknown → routeur unifié pdf_to_score (comme
            # /pdf/parse) : un SCAN peut être sol-fa OU portée → il tente le sol-fa
            # (OCR) puis bascule Audiveris. Router « scanned » direct vers Audiveris
            # cassait l'import d'un fihirana SCANNÉ (ex. mivavaha).
            return pdf_to_score(data, tonic_override=tonic_override)
        return pdf_to_score(data, tonic_override=tonic_override)
    except (PdfSolfaError, StaffRecognizeError, MusicXmlError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/musicxml/parse")
async def musicxml_parse(
    file: UploadFile = File(...),
    time: str | None = Form(None),
) -> dict:
    """Lit un MusicXML ou .mxl (portée classique) -> sol-fa tonique + modèles.

    Retourne :
    - ``header``  : informations globales (tonique, mesure, tempo).
    - ``voices``  : liste de voix ``{name, notation, model}``.
    - ``warnings``: liste d'avertissements (instrument transpositeur, accord…).

    ``time`` (optionnel, ex. « 10/8 ») force le mètre ; sinon il est inféré du
    contenu (le `<time>` du fichier peut être erroné, surtout en sortie OMR).
    """
    data = await file.read()
    try:
        result = read_musicxml(data, time_override=_parse_time(time))
    except MusicXmlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not result.models:
        raise HTTPException(status_code=422, detail="Aucune voix exploitable")

    first = result.models[0]
    meta = read_musicxml_metadata(data)
    header = {
        "title": meta.get("title") or "",
        "composer": meta.get("composer") or "",
        "work": meta.get("work") or "",
        "tonic": first.tonic,
        "mode": first.mode,
        "fifths": first.fifths,
        "beats": first.beats,
        "beatType": first.beat_type,
        "tempo": first.tempo,
    }
    voices = [
        {
            "name": m.part_name,
            "notation": to_solfa(m),
            "model": m.to_dict(),
        }
        for m in result.models
    ]
    return {"header": header, "voices": voices, "warnings": result.warnings}
