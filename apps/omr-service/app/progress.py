"""Reporter de progression optionnel pour les pipelines longs (OCR, Audiveris).

Stdlib pure — utilisable depuis ``app.pdf`` / ``app.staff`` sans dépendances.
``app.solfa`` n'importe **jamais** ce module.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

# event name + payload dict (phase/pct/message, ou voice/index/total, …)
ProgressFn = Optional[Callable[[str, Dict[str, Any]], None]]


def emit(on_progress: ProgressFn, event: str, **payload: Any) -> None:
    """Appelle le callback s'il est fourni ; ignore silencieusement sinon."""
    if on_progress is not None:
        on_progress(event, payload)


def progress(
    on_progress: ProgressFn,
    *,
    phase: str,
    pct: float,
    message: str,
) -> None:
    """Raccourci pour un événement ``progress``."""
    emit(on_progress, "progress", phase=phase, pct=pct, message=message)
