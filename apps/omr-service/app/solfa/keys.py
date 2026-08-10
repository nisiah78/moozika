"""Tonalité, gammes et épellation des hauteurs.

Le sol-fa tonique est *mouvable-do* : les syllabes sont relatives à la
tonique. Pour produire une hauteur absolue (indispensable pour la portée
et le MusicXML), il faut connaître la tonique déclarée par la feuille
(« Doh = X »). Ce module fait cette résolution de façon déterministe.
"""
from __future__ import annotations

from .model import Pitch

# Ordre scientifique des lettres : l'octave s'incrémente au passage de B -> C.
LETTERS = ["C", "D", "E", "F", "G", "A", "B"]

# tonique -> (lettre de base, nombre de quintes = armure MusicXML)
TONIC_MAP = {
    "C": ("C", 0),
    "G": ("G", 1),
    "D": ("D", 2),
    "A": ("A", 3),
    "E": ("E", 4),
    "B": ("B", 5),
    "F#": ("F", 6),
    "C#": ("C", 7),
    "F": ("F", -1),
    "Bb": ("B", -2),
    "Eb": ("E", -3),
    "Ab": ("A", -4),
    "Db": ("D", -5),
    "Gb": ("G", -6),
    "Cb": ("C", -7),
}

_SHARP_ORDER = ["F", "C", "G", "D", "A", "E", "B"]
_FLAT_ORDER = ["B", "E", "A", "D", "G", "C", "F"]

# Syllabes diatoniques -> degré de la gamme (1..7).
DIATONIC = {"d": 1, "r": 2, "m": 3, "f": 4, "s": 5, "l": 6, "t": 7}

# Syllabes chromatiques -> (degré de base, delta d'altération relatif au diatonique).
# Le dialecte malgache hausse avec le suffixe « -i » (di ri fi si li) et
# abaisse avec « -a/-e » (ta ra ma la...). On accepte aussi les formes
# Curwen classiques (de fe se) comme alias.
CHROMATIC = {
    # haussés (dièses)
    "di": (1, +1),   # do dièse
    "de": (1, +1),   # (alias)
    "ri": (2, +1),   # ré dièse
    "fi": (4, +1),   # fa dièse
    "fe": (4, +1),   # (alias)
    "si": (5, +1),   # sol dièse
    "se": (5, +1),   # (alias)
    "li": (6, +1),   # la dièse
    # abaissés (bémols)
    "ra": (2, -1),   # ré bémol
    "ma": (3, -1),   # mi bémol
    "sa": (5, -1),   # sol bémol
    "la": (6, -1),   # la bémol
    "lo": (6, -1),   # (alias)
    "ta": (7, -1),   # si bémol (te abaissé)
}


def altered_letters(fifths: int) -> dict:
    """Lettres altérées par l'armure (ex. G majeur -> {'F': +1})."""
    out: dict = {}
    if fifths > 0:
        for letter in _SHARP_ORDER[:fifths]:
            out[letter] = +1
    elif fifths < 0:
        for letter in _FLAT_ORDER[: -fifths]:
            out[letter] = -1
    return out


def normalize_tonic(tonic: str) -> str:
    """Accepte 'c', 'bb', 'F#', 'F♯', 'B♭'... -> clé de TONIC_MAP."""
    t = tonic.strip().replace("♯", "#").replace("♭", "b")
    if not t:
        raise KeyError("tonique vide")
    t = t[0].upper() + t[1:].lower()
    if t not in TONIC_MAP:
        raise KeyError(f"tonique inconnue: {tonic!r}")
    return t


def fifths_of(tonic: str) -> int:
    return TONIC_MAP[normalize_tonic(tonic)][1]


def resolve_pitch(core: str, octave_shift: int, tonic: str, doh_octave: int) -> Pitch:
    """Résout une syllabe sol-fa en hauteur absolue.

    core          : syllabe sans marque d'octave, en minuscules ('d', 's', 'fe'...)
    octave_shift  : nombre d'octaves (marques ' et _), relatif à l'octave du doh
    tonic         : ex. 'C', 'F', 'Bb'
    doh_octave    : octave scientifique de la tonique (défaut 4)
    """
    key = normalize_tonic(tonic)
    tonic_letter, fifths = TONIC_MAP[key]
    key_alter = altered_letters(fifths)

    if core in DIATONIC:
        degree, delta = DIATONIC[core], 0
    elif core in CHROMATIC:
        degree, delta = CHROMATIC[core]
    else:
        raise KeyError(f"syllabe sol-fa inconnue: {core!r}")

    tonic_index = LETTERS.index(tonic_letter)
    letter = LETTERS[(tonic_index + degree - 1) % 7]
    alter = key_alter.get(letter, 0) + delta

    # Position diatonique absolue : octave * 7 + index_lettre.
    tonic_position = doh_octave * 7 + tonic_index
    position = tonic_position + (degree - 1) + 7 * octave_shift
    octave = position // 7

    return Pitch(step=letter, alter=alter, octave=octave, syllable=core)


# ---------------------------------------------------------------------------
# Sens inverse : hauteur absolue -> syllabe sol-fa (mouvable-do).
# ---------------------------------------------------------------------------

# fifths (armure MusicXML) -> tonique. Le doh se déduit directement de l'armure.
# En mineur *la-based* (convention Curwen / fihirana), on garde le doh de la
# relative majeure, qui partage exactement la même armure (La mineur = Do
# majeur = 0 altération) : le doh est donc fonction de `fifths` seul, quel que
# soit le mode. La tonique mineure retombe alors sur le degré 6 (« l »).
FIFTHS_TO_TONIC = {fifths: tonic for tonic, (_letter, fifths) in TONIC_MAP.items()}

# Degré diatonique -> syllabe.
DIATONIC_REVERSE = {v: k for k, v in DIATONIC.items()}

# (degré, delta) -> syllabe canonique (dialecte malgache : haussé -i, baissé -a).
CHROMATIC_REVERSE = {
    (1, +1): "di", (2, +1): "ri", (4, +1): "fi", (5, +1): "si", (6, +1): "li",
    (2, -1): "ra", (3, -1): "ma", (5, -1): "sa", (6, -1): "la", (7, -1): "ta",
}

# Cas hors table : re-épellation enharmonique -> (syllabe, décalage d'octave).
# mi♯ = fa ; ti♯ = doh de l'octave au-dessus ; do♭ = te de l'octave en dessous ;
# fa♭ = mi. Ces quatre combinaisons complètent les 14 (degré, ±1) possibles.
ENHARMONIC_REVERSE = {
    (3, +1): ("f", 0),
    (7, +1): ("d", +1),
    (1, -1): ("t", -1),
    (4, -1): ("m", 0),
}


def tonic_from_fifths(fifths: int) -> str:
    """Tonique (doh) déduite de l'armure MusicXML. Vaut aussi pour le mineur
    la-based (même armure que la relative majeure)."""
    try:
        return FIFTHS_TO_TONIC[fifths]
    except KeyError as exc:
        raise KeyError(f"armure hors plage: fifths={fifths}") from exc


def _syllable_for(degree: int, delta: int) -> tuple:
    """(degré 1..7, delta d'altération) -> (syllabe, décalage d'octave enharm.)."""
    if delta == 0:
        return DIATONIC_REVERSE[degree], 0
    if (degree, delta) in CHROMATIC_REVERSE:
        return CHROMATIC_REVERSE[(degree, delta)], 0
    if (degree, delta) in ENHARMONIC_REVERSE:
        return ENHARMONIC_REVERSE[(degree, delta)]
    raise KeyError(
        f"altération non représentable en sol-fa (degré {degree}, delta {delta})"
    )


def syllable_of_pitch(
    step: str, alter: int, octave: int, tonic: str, doh_octave: int
) -> tuple:
    """Inverse exact de `resolve_pitch` : hauteur absolue -> (core, octave_shift).

    step/alter/octave : hauteur MusicXML (lettre A..G, altération, octave scient.).
    tonic             : le doh (ex. 'C', 'F', 'Bb') — cf. `tonic_from_fifths`.
    doh_octave        : octave scientifique du doh (registre de référence).

    Renvoie la syllabe sans marque (`core`) et le nombre d'octaves relatif au
    doh (`octave_shift` : >0 = marques ', <0 = marques ,). Déterministe.
    """
    step = step.upper()
    if step not in LETTERS:
        raise KeyError(f"lettre de note invalide: {step!r}")

    key = normalize_tonic(tonic)
    tonic_letter, fifths = TONIC_MAP[key]
    key_alter = altered_letters(fifths)

    tonic_index = LETTERS.index(tonic_letter)
    letter_index = LETTERS.index(step)

    degree = ((letter_index - tonic_index) % 7) + 1
    delta = alter - key_alter.get(step, 0)

    core, octave_bump = _syllable_for(degree, delta)

    # Inversion de la formule de position de resolve_pitch. Le numérateur est
    # toujours un multiple exact de 7 (car letter_index ≡ tonic_index+degree-1
    # [mod 7]) -> division entière sans perte.
    tonic_position = doh_octave * 7 + tonic_index
    position = octave * 7 + letter_index
    octave_shift = (position - tonic_position - (degree - 1)) // 7 + octave_bump

    return core, octave_shift
