"""Jeton d'annulation coopérative pour les pipelines longs (OCR, Audiveris).

Stdlib pure — même contrainte que ``app/progress.py``, et pour la même raison :
``app.pdf`` / ``app.staff`` l'importent, ``app.solfa`` **jamais**.

Pourquoi coopératif et pas un kill : le travail tourne dans un thread (``main.py``) et,
pour la portée, dans un sous-processus Java. On ne peut pas interrompre du code natif de
l'extérieur — il faut lui laisser atteindre un point de contrôle. Le prix à payer est la
granularité : l'arrêt survient à la frontière de phase ou de page, jamais au milieu d'un
appel OCR.

Sans ce mécanisme, un client qui abandonne laisse le travail tourner jusqu'au bout :
mesuré à **~700 % de CPU pendant plusieurs minutes** après une annulation, le conteneur
n'étant récupérable qu'en le redémarrant.
"""
from __future__ import annotations

from typing import Callable, Optional

# Rend True dès que le client a abandonné. None = pas d'annulation possible (CLI, tests).
CancelFn = Optional[Callable[[], bool]]


class Cancelled(Exception):
    """Levée à un point de contrôle quand le client a abandonné.

    Volontairement **pas** une sous-classe de ``ValueError`` : toutes les erreurs métier du
    service en sont (``PdfSolfaError``, ``OcrError``…), et une annulation n'est pas une
    erreur — elle ne doit pas être attrapée par les ``except ValueError`` du pipeline ni
    remontée au client comme un échec.
    """


def check(is_cancelled: CancelFn) -> None:
    """Point de contrôle : lève ``Cancelled`` si le client a abandonné, sinon ne fait rien."""
    if is_cancelled is not None and is_cancelled():
        raise Cancelled("transcription annulée par le client")
