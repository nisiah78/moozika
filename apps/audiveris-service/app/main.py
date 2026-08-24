"""Micro-service Audiveris : PDF/image portée → MusicXML.

Exposé en HTTP interne (compose :8081). omr-service appelle POST /recognize.
"""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile

from .merge import merge_musicxml

app = FastAPI(title="Moozika Audiveris", version="0.1.0")

_AUDIVERIS_BIN = os.environ.get("AUDIVERIS_BIN", "Audiveris")
_PDF_RESOLUTION_OPT = "org.audiveris.omr.image.ImageLoading.pdfResolution=450"
_DEFAULT_QUALITY_OPT = "org.audiveris.omr.sheet.Profiles.defaultQuality=Poor"
_DISCONNECTED_BRACE_PART_OPT = "org.audiveris.omr.sheet.ProcessingSwitches.disconnectedBracedParts=true"
_BOOK_FOLDERS_OPT = "org.audiveris.omr.sheet.BookManager.useSeparateBookFolders=false"
_TIMEOUT = int(os.environ.get("AUDIVERIS_TIMEOUT", "600"))

# Ghostscript : dépendance de rendu PDF d'Audiveris 5.11 lui-même (vérifiée dans
# /health). N'est PAS utilisé pour du prétraitement image : Audiveris échoue sur
# des TIFF suréchantillonnés — on lui garde donc du PDF (cf. _render_pages).
_GS_BIN = os.environ.get("GHOSTSCRIPT_BIN", "gs")

# Fusion page-par-page. Diagnostic établi : Audiveris lit correctement chaque
# page ISOLÉE (somme des mesures ≈ total réel) mais en PERD ~25 % lors de
# l'assemblage du « book » multi-pages (réconciliation des parts d'une page à
# l'autre, cassée par les divisi). On éclate donc le PDF page par page (pypdf),
# on lance Audiveris sur chacune, puis on recolle les mesures par index de part.
# Repli sur le book PDF entier si indisponible. Désactivable : AUDIVERIS_MERGE_PAGES=0.
_MERGE_PAGES = os.environ.get("AUDIVERIS_MERGE_PAGES", "1").strip().lower() not in (
    "0", "false", "no", "off", "",
)


# Intervalle de scrutation du sous-processus. Assez court pour que l'annulation soit
# ressentie comme immediate, assez long pour ne rien coûter face a une JVM de 15-30 min.
_POLL_SEC = 0.5

# Delai laisse a la JVM pour sortir proprement sur SIGTERM avant le SIGKILL.
_KILL_GRACE_SEC = 5


class Cancelled(Exception):
    """Le client a abandonne : on arrete le travail en cours.

    Pas une sous-classe de RuntimeError : _recognize_book et l'endpoint attrapent
    RuntimeError pour basculer en repli ou repondre 422, et une annulation ne doit
    declencher ni l'un ni l'autre.
    """


def _check(cancel: Optional[threading.Event]) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled("reconnaissance annulee par le client")


def _terminate_group(proc: "subprocess.Popen") -> None:
    """Tue le GROUPE de processus, pas seulement Audiveris.

    Le groupe importe : Audiveris 5.11 lance Ghostscript en enfant pour rasteriser le
    PDF. Un kill sur le seul PID de la JVM laisserait `gs` orphelin en train de brûler
    du CPU — ce qui est precisement le probleme qu'on cherche a supprimer.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError):
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=_KILL_GRACE_SEC)
            return
        except subprocess.TimeoutExpired:
            continue


def _find_audiveris() -> str:
    candidates = (_AUDIVERIS_BIN, "Audiveris", "audiveris")
    for name in candidates:
        if name and Path(name).is_file():
            return name
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError(
        "binaire Audiveris introuvable (installer le .deb ou définir AUDIVERIS_BIN)"
    )


def _unzip_mxl(data: bytes) -> bytes:
    """Archive .mxl → octets XML internes."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    root_path = None
    try:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        for rf in container.iter():
            if rf.tag.rsplit("}", 1)[-1] == "rootfile":
                root_path = rf.get("full-path")
                break
    except KeyError:
        pass
    if root_path is None:
        for name in zf.namelist():
            if name.lower().endswith((".xml", ".musicxml")) and not name.startswith("META-INF"):
                root_path = name
                break
    if root_path is None:
        raise RuntimeError("archive .mxl sans XML racine")
    return zf.read(root_path)


def _run_audiveris(
    input_path: Path, output_dir: Path, cancel: Optional[threading.Event] = None,
) -> subprocess.CompletedProcess:
    """Lance Audiveris. NE lève PAS sur code ≠ 0 : Audiveris sort parfois non-nul
    tout en ayant produit un MusicXML exploitable (avertissements). L'appelant
    décide en cherchant la sortie (cf. _audiveris_one).

    ``cancel`` : levé par l'endpoint quand le client se deconnecte. On scrute au lieu
    d'attendre bêtement, pour pouvoir tuer le groupe de processus."""
    bin_path = _find_audiveris()
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        bin_path,
        "-batch",
        "-export",
        "-output",
        str(output_dir),
        "-constant",
        _PDF_RESOLUTION_OPT,
        "-constant",
        _DEFAULT_QUALITY_OPT,
        "-constant",
        _DISCONNECTED_BRACE_PART_OPT,
        "-constant",
        _BOOK_FOLDERS_OPT,
        "--",
        str(input_path),
    ]
    env = {**os.environ, "JAVA_TOOL_OPTIONS": "-Djava.awt.headless=true"}

    # Sorties vers des FICHIERS et non des tubes : avec Popen + attente, un tube plein
    # bloquerait Audiveris (il est bavard) faute d'etre vide en continu. Des fichiers
    # suppriment ce risque et se relisent apres coup.
    log_out = output_dir / "audiveris.out"
    log_err = output_dir / "audiveris.err"
    # start_new_session : le processus devient chef de son propre groupe, ce qui rend
    # possible de tuer la JVM **et** son Ghostscript enfant d'un seul killpg.
    # Popen en gestionnaire de contexte : garantit que le processus est attendu et ses
    # descripteurs liberes, meme quand on sort par Cancelled ou TimeoutExpired.
    with open(log_out, "w", encoding="utf-8") as fo, \
            open(log_err, "w", encoding="utf-8") as fe, \
            subprocess.Popen(  # noqa: S603
                cmd, stdout=fo, stderr=fe, env=env, start_new_session=True,
            ) as proc:
        deadline = time.monotonic() + _TIMEOUT
        while True:
            if proc.poll() is not None:
                break
            if cancel is not None and cancel.is_set():
                _terminate_group(proc)
                raise Cancelled("reconnaissance annulee pendant le run Audiveris")
            if time.monotonic() > deadline:
                _terminate_group(proc)
                raise subprocess.TimeoutExpired(cmd, _TIMEOUT)
            time.sleep(_POLL_SEC)

    return subprocess.CompletedProcess(
        cmd,
        proc.returncode,
        stdout=log_out.read_text(encoding="utf-8", errors="replace"),
        stderr=log_err.read_text(encoding="utf-8", errors="replace"),
    )


def _collect_musicxml(output_dir: Path) -> bytes:
    """Cherche .mxl puis .xml/.musicxml ; décompresse .mxl si besoin."""
    candidates = sorted(output_dir.rglob("*.mxl"))
    if not candidates:
        candidates = sorted(output_dir.rglob("*.musicxml"))
    if not candidates:
        candidates = sorted(output_dir.rglob("*.xml"))
    if not candidates:
        raise RuntimeError("Audiveris n'a produit aucun MusicXML")
    raw = candidates[0].read_bytes()
    if raw[:2] == b"PK":
        return _unzip_mxl(raw)
    return raw


def _audiveris_one(
    input_path: Path, out_dir: Path, cancel: Optional[threading.Event] = None,
) -> bytes:
    """Un run Audiveris sur UN fichier → octets MusicXML.

    Tolère un code de sortie ≠ 0 : si un MusicXML a été produit, on le prend.
    Sinon on lève avec la VRAIE erreur (bruit JVM « Picked up JAVA_TOOL_OPTIONS »
    filtré, qui masquait jusqu'ici le vrai motif)."""
    proc = _run_audiveris(input_path, out_dir, cancel=cancel)
    try:
        return _collect_musicxml(out_dir)
    except RuntimeError:
        noise = "Picked up JAVA_TOOL_OPTIONS"
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        real = "\n".join(ln for ln in combined.splitlines() if noise not in ln).strip()
        raise RuntimeError(
            f"Audiveris rc={proc.returncode}: {real or 'aucune sortie'}"[-1500:]
        )


def _render_pages(pdf_path: Path, out_dir: Path, dpi: Optional[int] = None) -> List[Path]:
    """Éclate le PDF en un PDF PAR PAGE (pypdf, préserve /Rotate et le contenu).
    On garde le format PDF car Audiveris le lit nativement (le rendu image/TIFF
    le fait échouer). C'est exactement la méthode validée par diagnose_omr.py.
    Renvoie la liste ordonnée des pages, [] si indisponible/échec."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return []
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        reader = PdfReader(str(pdf_path))
        pages: List[Path] = []
        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            fn = out_dir / f"page_{i + 1}.pdf"
            with open(fn, "wb") as f:
                writer.write(f)
            pages.append(fn)
        return pages
    except Exception:
        return []


def _recognize_book(
    pdf_path: Path, tmp: Path, cancel: Optional[threading.Event] = None,
) -> tuple[bytes, dict]:
    """PDF → (MusicXML, meta). Voie principale : split PDF par page + fusion
    (récupère les mesures perdues à l'assemblage du book Audiveris). Repli : book
    PDF brut entier. ``meta`` dit quelle voie a servi et pourquoi (diagnostic)."""
    meta: dict = {"merge_enabled": bool(_MERGE_PAGES)}
    if _MERGE_PAGES:
        pages = _render_pages(pdf_path, tmp / "pages")
        meta["rendered_pages"] = len(pages)
        if len(pages) > 1:
            try:
                xmls = []
                for k, pg in enumerate(pages):
                    # Entre deux pages : le seul endroit ou l'on peut s'arreter sans
                    # attendre la fin d'un run. Borne le gaspillage a UNE page.
                    _check(cancel)
                    xmls.append(
                        _audiveris_one(pg, tmp / f"out_p{k + 1}", cancel=cancel)
                        .decode("utf-8", "replace")
                    )
                meta["method"] = "per-page-merge"
                return merge_musicxml(xmls).encode("utf-8"), meta
            except (RuntimeError, ValueError, ET.ParseError,
                    subprocess.TimeoutExpired) as exc:
                meta["fallback_reason"] = f"{type(exc).__name__}: {exc}"[:300]
        else:
            meta["fallback_reason"] = f"rendered_pages={len(pages)} (pypdf?)"

    meta["method"] = "single-raw-pdf"
    _check(cancel)
    return _audiveris_one(pdf_path, tmp / "out_raw", cancel=cancel), meta


@app.get("/health")
def health() -> dict:
    gs = shutil.which(_GS_BIN)
    config = {
        "ghostscript": gs or "absent",   # Audiveris en a besoin pour lire un PDF
        "merge_pages": _MERGE_PAGES,      # présence de ce champ = nouveau code déployé
    }
    try:
        _find_audiveris()
        return {"status": "ok", "audiveris": _AUDIVERIS_BIN, "config": config}
    except RuntimeError as exc:
        return {"status": "error", "detail": str(exc), "config": config}


def _recognize_sync(
    inp: Path, tmp_path: Path, suffix: str, cancel: threading.Event,
) -> tuple[bytes, dict]:
    """Pipeline bloquant, destine a tourner HORS de la boucle d'evenements."""
    if suffix.lower() == ".pdf":
        return _recognize_book(inp, tmp_path, cancel=cancel)
    # Image : pas de split possible, run direct.
    return _audiveris_one(inp, tmp_path / "out", cancel=cancel), {"method": "image-direct"}


@app.post("/recognize")
async def recognize(request: Request, file: UploadFile = File(...)) -> dict:
    """PDF ou image → MusicXML (texte XML score-partwise)."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="fichier vide")

    suffix = Path(file.filename or "score.pdf").suffix or ".pdf"
    meta: dict = {}
    with tempfile.TemporaryDirectory(prefix="audiveris-") as tmp:
        tmp_path = Path(tmp)
        inp = tmp_path / f"input{suffix}"
        inp.write_bytes(data)

        # Le pipeline part dans un THREAD : jusqu'ici il tournait directement dans un
        # `async def`, donc un `subprocess.run` de 15-30 min bloquait la boucle
        # d'evenements. Consequence mesuree : /health ne repondait plus pendant une
        # reconnaissance, la sonde de 2 s de omr-service concluait « Audiveris
        # indisponible », et l'appelant retentait — aggravant la charge.
        cancel = threading.Event()
        task = asyncio.ensure_future(
            asyncio.to_thread(_recognize_sync, inp, tmp_path, suffix, cancel)
        )
        try:
            while not task.done():
                if await request.is_disconnected():
                    cancel.set()
                    break
                await asyncio.sleep(_POLL_SEC)
            # On attend DANS TOUS LES CAS : asyncio.to_thread n'est pas interruptible,
            # et sortir d'ici sans attendre laisserait le thread ecrire dans un
            # repertoire temporaire deja supprime.
            xml_bytes, meta = await task
        except Cancelled as exc:
            raise HTTPException(status_code=499, detail="annule par le client") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "filename": Path(file.filename or "score").stem + ".xml",
        "size": len(xml_bytes),
        "meta": meta,  # method / rendered_pages / fallback_reason (diagnostic)
        "musicxml": xml_bytes.decode("utf-8", errors="replace"),
    }
