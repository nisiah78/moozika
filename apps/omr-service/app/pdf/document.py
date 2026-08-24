"""Orchestration : fichier PDF/image -> voix sol-fa -> ScoreModel(s) + MusicXML."""
from __future__ import annotations

from pathlib import Path
from typing import List, Union

from ..cancel import CancelFn, check
from ..progress import ProgressFn, emit, progress
from ..solfa import ScoreModel, parse_solfa, to_musicxml_multi, to_solfa
from ..solfa.model import Measure, NoteEl
from ..solfa.parser import ParseError
from ..solfa.rhythm import MeterError, classify_meter, split_duration
from ..staff.recognize import StaffRecognizeError, staff_pdf_to_score
from .correct import correct_ocr_runs
from .detect import classify_runs, detect_pdf_kind
from .extract import ExtractError, extract_runs, extract_runs_and_barlines
from .layout import SolfaDocument, build_document
from .ocr import OcrError, ocr_to_runs

# Portées : soprano/alto/ténor en clé de sol, basse en clé de fa.
_CLEF_BY_NAME = {"Bass": "bass"}

# Au-delà de ce nombre de pages, un PDF scanné n'est presque sûrement PAS un
# fihirana sol-fa (1-4 pages en général) mais une PARTITION de portée → on l'envoie
# direct à Audiveris au lieu de lancer PaddleOCR sur des dizaines de pages (rendu
# 300 dpi + OCR = pic mémoire qui fait tomber le conteneur).
_MAX_SOLFA_SCAN_PAGES = 8


class PdfSolfaError(ValueError):
    """Erreur exposable lors de la lecture d'un PDF sol-fa."""


def _pdf_page_count(data: bytes) -> int:
    """Nombre de pages d'un PDF, sans le rendre (léger)."""
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001
        return 0


def _read(source: Union[str, bytes]) -> bytes:
    if isinstance(source, bytes):
        return source
    with open(source, "rb") as fh:
        return fh.read()


def _runs_from_source(
    source: Union[str, bytes], *, on_progress: ProgressFn = None,
    is_cancelled: CancelFn = None,
):
    """Texte embarqué (ToUnicode) si possible, sinon OCR (PDF/image scanné)."""
    data = _read(source)
    try:
        return extract_runs(data)
    except ExtractError as extract_exc:
        # PDF scanné. PaddleOCR (torch) est le lecteur principal du sol-fa
        # scanné quand il est installé — segments de ligne exploités par
        # ``layout`` sans le correcteur glyphe. Sinon repli Tesseract+correcteur.
        try:
            from .paddle_ocr import paddle_available, paddle_to_runs
        except Exception:  # noqa: BLE001 — module optionnel
            paddle_available = None
        if paddle_available is not None and paddle_available():
            # Laisse remonter une erreur paddle explicite (l'utilisateur a
            # installé paddle pour s'en servir : on ne la masque pas).
            return paddle_to_runs(data, on_progress=on_progress, is_cancelled=is_cancelled)
        try:
            # OCR → correcteur glyphe/rythme avant layout.
            return correct_ocr_runs(ocr_to_runs(data, on_progress=on_progress, is_cancelled=is_cancelled))
        except OcrError as ocr_exc:
            raise PdfSolfaError(
                f"{extract_exc} ; fallback OCR : {ocr_exc}"
            ) from ocr_exc


def pdf_to_document(
    source: Union[str, bytes], *, on_progress: ProgressFn = None,
    is_cancelled: CancelFn = None,
) -> SolfaDocument:
    """Extrait la structure sol-fa (en-tête + voix en notation canonique)."""
    try:
        runs, barlines = extract_runs_and_barlines(_read(source))
        if classify_runs(runs) == "solfa_text":
            progress(on_progress, phase="layout", pct=70, message="Reconstruction des voix…")
            return build_document(runs, barlines)
    except ExtractError:
        pass

    try:
        check(is_cancelled)
        runs = _runs_from_source(source, on_progress=on_progress, is_cancelled=is_cancelled)
        progress(on_progress, phase="layout", pct=70, message="Reconstruction des voix…")
        return build_document(runs)
    except PdfSolfaError:
        raise
    except ValueError as exc:
        raise PdfSolfaError(str(exc)) from exc


def _pad_models_to_equal_length(models: List[ScoreModel]) -> None:
    """Aligne les parties sur le même nombre de mesures (silences) pour OSMD."""
    if not models:
        return
    target = max(len(m.measures) for m in models)
    for model in models:
        # Capacité réelle via classify_meter : `beats*divisions` serait faux en
        # mesure composée (ex. 6/8 -> 6*4=24 au lieu de 12).
        try:
            cap = classify_meter(model.beats, model.beat_type).measure_divisions
        except MeterError:
            cap = model.beats * model.divisions
        while len(model.measures) < target:
            notes = [
                NoteEl(is_rest=True, duration=value, note_type=ntype, dots=dots)
                for value, ntype, dots in split_duration(cap)
            ]
            model.measures.append(Measure(number=len(model.measures) + 1, notes=notes))


_STEP_SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _median_midi(model: ScoreModel) -> int:
    hs = sorted(
        n.pitch.octave * 12 + _STEP_SEMI.get(n.pitch.step, 0) + n.pitch.alter
        for meas in model.measures for n in meas.notes if n.pitch
    )
    return hs[len(hs) // 2] if hs else 48  # 48 = do central (C4)


def _assign_clefs_by_tessiture(models: List[ScoreModel]) -> None:
    """Voix aux noms génériques (« Voix N », OCR) : clef par tessiture — la voix
    dont la médiane est sous le do central passe en clé de fa. Les voix déjà
    nommées SATB gardent la clef posée par `_CLEF_BY_NAME`."""
    for m in models:
        if m.part_name.startswith("Voix"):
            m.clef = "bass" if _median_midi(m) < 48 else "treble"


def _source_is_scanned(source: Union[str, bytes]) -> bool:
    """Vrai si le PDF est scanné (pas de texte embarqué) → chemin OCR bruité."""
    try:
        extract_runs(_read(source))
        return False
    except ExtractError:
        return True


def _strip_leading_empty_measures(models: List[ScoreModel]) -> None:
    """Retire les mesures de tête où TOUTES les voix sont muettes.

    ⚠ Réservé au chemin **OCR/scanné** : une pièce typographiée peut légitimement
    démarrer par un silence général (ex. « The Lord Bless You » : soprano entre à
    la mesure 2). Sur un scan, ces mesures vides de tête sont en revanche un
    artefact (anacrouse mal segmentée, cf. mivavaha)."""
    def empty(meas) -> bool:
        return not meas.notes or all(n.is_rest for n in meas.notes)

    while models and all(m.measures for m in models) and all(
        empty(m.measures[0]) for m in models
    ):
        for m in models:
            m.measures.pop(0)
    for m in models:
        for i, meas in enumerate(m.measures):
            meas.number = i + 1


def pdf_to_models(
    source: Union[str, bytes], *, tonic_override: str | None = None,
    doc: SolfaDocument | None = None, scanned: bool | None = None,
    on_progress: ProgressFn = None,
    is_cancelled: CancelFn = None,
) -> List[ScoreModel]:
    """Une voix -> un ScoreModel (longueurs alignées).

    Entrée OCR/PDF bruitée : parse en mode ``lenient`` (subdivisions impaires
    tolérées par arrondi) et une voix qui échoue malgré tout est **sautée** —
    on ne lève que si AUCUNE voix n'est exploitable, pour ne pas perdre tout
    l'import à cause d'une seule ligne mal reconnue.

    ``tonic_override`` : force la tonique (« Doh = X ») — utile sur un scan où
    l'en-tête « Do dia X » n'est pas lu et où la tonique tombe à C par défaut.

    ``doc`` / ``scanned`` : pré-calculés par l'appelant pour **éviter de relancer
    l'OCR** (coûteux — PaddleOCR) ; sinon calculés ici.
    """
    if doc is None:
        doc = pdf_to_document(source, on_progress=on_progress, is_cancelled=is_cancelled)
    if scanned is None:
        scanned = _source_is_scanned(source)
    tonic = tonic_override or doc.header.tonic
    models: List[ScoreModel] = []
    errors: List[str] = []
    pairs = [
        (name, notation)
        for name, notation in zip(doc.voice_names, doc.voices)
        if notation.strip()
    ]
    total = len(pairs) or 1
    for idx, (name, notation) in enumerate(pairs):
        check(is_cancelled)
        try:
            model = parse_solfa(
                notation,
                tonic=tonic,
                clef=_CLEF_BY_NAME.get(name, "treble"),
                tempo=doc.header.tempo,
                part_name=name,
                # NE PAS imposer le mètre de l'en-tête : l'inférence par pulsations
                # + les marqueurs (N/M) par mesure gèrent le mètre VARIABLE (jubilate
                # 10/8→6/8→10/8…). Forcer l'en-tête écrasait cette détection.
                lenient=True,
                # Dégradation (legato + silence de complément) : SCAN OCR bruité,
                # OU reconstruction par barres vectorielles (grille à mètre variable,
                # ex. 11.pdf) qui peut porter du bruit de grille. PDF typographié
                # ordinaire (rythme fiable) → pas touché.
                degrade=scanned or doc.degrade_hint,
            )
        except ParseError as exc:
            errors.append(f"voix {name!r}: {exc}")
            continue
        models.append(model)
        pct = 75 + 15 * (idx + 1) / total
        progress(
            on_progress,
            phase="convert",
            pct=pct,
            message=f"Voix {name} ({idx + 1}/{total})…",
        )
        emit(
            on_progress,
            "voice",
            index=idx,
            total=total,
            voice={
                "name": model.part_name,
                "notation": notation,
                "model": model.to_dict(),
            },
        )
    if not models:
        detail = " ; ".join(errors) if errors else "aucune voix détectée"
        raise PdfSolfaError(f"aucune voix exploitable dans le PDF ({detail})")
    # #1 : mesures vides de tête = artefact seulement sur scan (typographié fiable).
    if scanned is None:
        scanned = _source_is_scanned(source)
    if scanned:
        _strip_leading_empty_measures(models)
    _assign_clefs_by_tessiture(models)      # #3 : clé de fa pour les voix graves
    _pad_models_to_equal_length(models)
    return models


def _solfa_pdf_to_score(
    source: Union[str, bytes], *, tonic_override: str | None = None,
    on_progress: ProgressFn = None,
    is_cancelled: CancelFn = None,
) -> dict:
    """Pipeline B : PDF sol-fa tonique malgache typographié ou OCR."""
    doc = pdf_to_document(source, on_progress=on_progress, is_cancelled=is_cancelled)  # OCR UNE SEULE FOIS
    check(is_cancelled)
    scanned = _source_is_scanned(source)        # bon marché (extract_runs échoue vite)
    models = pdf_to_models(
        source,
        tonic_override=tonic_override,
        doc=doc,
        scanned=scanned,
        on_progress=on_progress,
    )
    notation_by_name = dict(zip(doc.voice_names, doc.voices))
    progress(on_progress, phase="convert", pct=95, message="Génération MusicXML…")

    def _clean_notation(m: ScoreModel) -> str:
        """Notation affichée (onglet sol-fa). Régénérée **depuis le modèle parsé**
        (``to_solfa``, format canonique) dans deux cas où le texte brut n'est pas
        fiable/canonique pour l'affichage :
          - SCAN OCR (espaces, ``,`` mis pour ``.``) ;
          - reconstruction par barres vectorielles (``degrade_hint`` — grille à
            mètre variable, ex. 11.pdf) dont la chaîne brute porte des espaces et
            des artefacts → l'onglet sol-fa doit refléter le MÊME modèle que la
            portée (sinon incohérence : portée juste, sol-fa cassé).
        Sinon (PDF typographié ordinaire) : le texte brut est déjà canonique."""
        if scanned or doc.degrade_hint:
            try:
                return to_solfa(m)
            except (ValueError, MeterError):
                pass
        return notation_by_name.get(m.part_name, "")

    return {
        "header": {
            "title": doc.header.title,
            "composer": doc.header.composer,
            "tonic": tonic_override or doc.header.tonic,
            "mode": models[0].mode if models else "major",
            "fifths": models[0].fifths if models else 0,
            "timeSignature": {"beats": doc.header.beats, "beatType": doc.header.beat_type},
            "tempo": doc.header.tempo,
        },
        "voices": [
            {
                "name": m.part_name,
                "notation": _clean_notation(m),
                "model": m.to_dict(),
            }
            for m in models
        ],
        "musicxml": to_musicxml_multi(
            models, title=doc.header.title, composer=doc.header.composer
        ),
        "source": "solfa_pdf",
    }


def pdf_to_score(
    source: Union[str, bytes], *, filename: str | None = None,
    tonic_override: str | None = None,
    on_progress: ProgressFn = None,
    is_cancelled: CancelFn = None,
) -> dict:
    """Import PDF unifié : sol-fa malgache (pipeline B) ou portée (Audiveris → sol-fa).

    Détection automatique (``detect.py``) :
      - sol-fa texte → extraction ToUnicode ;
      - **scan → sol-fa malgache d'abord (PaddleOCR)**, repli Audiveris (portée) :
        un scan de portée n'a aucune ligne de voix sol-fa → l'OCR sol-fa lève une
        erreur → bascule Audiveris. Évite d'attendre la JVM sur un fihirana scanné ;
      - portée gravée / inconnu → Audiveris → MusicXML → ``from_musicxml`` → sol-fa.

    ``tonic_override`` : force la tonique du sol-fa (utile sur scan où l'en-tête
    « Do dia X » n'est pas lu). Sans effet sur le chemin portée (Audiveris).
    """
    data = _read(source)
    fname = filename or (Path(source).name if isinstance(source, (str, Path)) else "score.pdf")

    if data.startswith(b"%PDF"):
        check(is_cancelled)
        progress(on_progress, phase="detect", pct=5, message="Analyse du PDF…")
        kind = detect_pdf_kind(data)
        if kind == "scanned" and 0 < _pdf_page_count(data) <= _MAX_SOLFA_SCAN_PAGES:
            # Petit scan : tenter d'abord le sol-fa malgache (PaddleOCR — rapide,
            # pas de JVM). Un scan de PORTÉE ne contient aucune ligne de voix
            # sol-fa → l'OCR sol-fa lève PdfSolfaError → repli Audiveris.
            try:
                return _solfa_pdf_to_score(
                    source, tonic_override=tonic_override, on_progress=on_progress, is_cancelled=is_cancelled
                )
            except PdfSolfaError as solfa_exc:
                try:
                    return staff_pdf_to_score(
                        data, filename=fname, on_progress=on_progress, is_cancelled=is_cancelled
                    )
                except StaffRecognizeError as staff_exc:
                    raise PdfSolfaError(
                        f"{solfa_exc} ; repli portée Audiveris : {staff_exc}"
                    ) from solfa_exc
        if kind != "solfa_text":
            # Portée gravée / PDF inconnu → Audiveris (OMR portée).
            try:
                return staff_pdf_to_score(
                    data, filename=fname, on_progress=on_progress, is_cancelled=is_cancelled
                )
            except StaffRecognizeError as exc:
                raise PdfSolfaError(str(exc)) from exc

    return _solfa_pdf_to_score(
        source, tonic_override=tonic_override, on_progress=on_progress, is_cancelled=is_cancelled
    )
