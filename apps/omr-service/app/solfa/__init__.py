"""
Sol-fa tonique (notation malgache) → modèle interprétable → MusicXML, et
sens inverse (MusicXML → sol-fa tonique).

Format d'entrée/sortie : voir packages/shared-contracts/solfa-format.md
"""

from .parser import parse_solfa, ParseError
from .musicxml import to_musicxml, to_musicxml_multi
from .model import ScoreModel
from .from_musicxml import from_musicxml, read_musicxml, MusicXmlError
from .to_solfa import to_solfa

__all__ = [
    "parse_solfa",
    "to_musicxml",
    "to_musicxml_multi",
    "ScoreModel",
    "ParseError",
    "from_musicxml",
    "read_musicxml",
    "MusicXmlError",
    "to_solfa",
]
