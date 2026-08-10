"""Fusion de MusicXML page-par-page en un seul score-partwise.

Motivation (diagnostic établi sur des scans de partitions chorales condensées) :
Audiveris lit correctement chaque page ISOLÉE (la somme des mesures par page ≈
le total réel de la partition) mais en PERD lors de l'assemblage de son « book »
multi-pages (réconciliation des parts d'une page à l'autre, cassée notamment par
les passages en divisi / changements de système qui réordonnent les parts). On
traite donc chaque page séparément, puis on recolle ici les mesures.

Recollage — deux mécanismes complémentaires :
  1. Mapping par POSITION (ordre haut→bas des portées, stable d'une page à
     l'autre) sur la structure la PLUS FRÉQUENTE : slot i ← part i. Comportement
     stable, sans régression sur les pages « normales ».
  2. RÉCUPÉRATION divisi : sur une page où Audiveris a produit PLUS de parts que
     la base, le VRAI contenu se loge parfois dans les parts d'indice élevé
     (ex. page en divisi : voix dans P4/P5 tandis que P1-P3 ne sont que du
     silence). On place alors le contenu de ces parts supplémentaires dans les
     slots VIDES (silence ou absent) de la mesure, aigu→haut. Sans ça, on gardait
     les parts de bourrage et on perdait des mesures entières sur toutes les voix.

Les numéros de mesure sont ré-attribués en continu ; un slot resté vide devient
une mesure vide (l'aval la comble d'un silence pleine mesure).

Module volontairement SANS dépendance (stdlib seule) → testable hors conteneur.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from typing import List, Optional

# Demi-tons approx pour classer les parts récupérées (aigu → slot du haut).
_STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Une part de piano/orgue ne doit pas remplir un slot de VOIX : une fois fusionnée
# dans un slot, elle perd son étiquette et serait traitée comme une voix chantée.
_PIANO_HINTS = ("piano", "keyboard", "orgue", "organ", "accompaniment", "accomp")


def strip_ns(root: ET.Element) -> None:
    """Retire les namespaces XML (MusicXML d'Audiveris peut en porter)."""
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def _has_notes(measure_el: ET.Element) -> bool:
    """Mesure porteuse de VRAIES notes (hors silence et note d'agrément)."""
    for n in measure_el.findall("note"):
        if n.find("rest") is None and n.find("grace") is None:
            return True
    return False


def _median_pitch(measure_el: ET.Element) -> float:
    """Hauteur médiane approx des notes d'une mesure (pour ordonner les voix
    récupérées, aigu → slot du haut). 0.0 si aucune hauteur exploitable."""
    hs: List[int] = []
    for n in measure_el.findall("note"):
        if n.find("grace") is not None:
            continue
        p = n.find("pitch")
        if p is None:
            continue
        step = (p.findtext("step") or "C").strip().upper()
        try:
            octave = int(p.findtext("octave", "4") or "4")
            alter = int(float(p.findtext("alter", "0") or "0"))
        except ValueError:
            continue
        hs.append(octave * 12 + _STEP.get(step, 0) + alter)
    if not hs:
        return 0.0
    hs.sort()
    return float(hs[len(hs) // 2])


def _looks_like_piano(name: Optional[str]) -> bool:
    return any(h in (name or "").lower() for h in _PIANO_HINTS)


def _part_names(root: ET.Element) -> dict:
    """id de part → nom (part-list), pour repérer les parts de piano."""
    out: dict = {}
    for sp in root.findall("part-list/score-part"):
        out[sp.get("id")] = sp.findtext("part-name") or ""
    return out


def merge_musicxml(pages: List[str]) -> str:
    """Recolle les MusicXML page-par-page en un seul score-partwise.

    La structure la PLUS FRÉQUENTE (nb de parts) définit le nombre de slots
    (voix). Chaque page alimente ces slots par POSITION, et le contenu de ses
    parts supplémentaires (divisi) est récupéré dans les slots vides (cf.
    docstring du module). Numéros de mesure ré-attribués en continu."""
    if not pages:
        raise ValueError("aucune page à fusionner")

    roots: List[ET.Element] = []
    for xml in pages:
        r = ET.fromstring(xml)
        strip_ns(r)
        roots.append(r)

    counts = [len(r.findall("part")) for r in roots]
    counts = [c for c in counts if c > 0]
    if not counts:
        raise ValueError("aucune part exploitable dans les pages")
    base_count = Counter(counts).most_common(1)[0][0]
    base = next(r for r in roots if len(r.findall("part")) == base_count)
    part_ids = [p.get("id") for p in base.findall("part")]

    merged: dict = {slot: [] for slot in range(base_count)}
    global_num = 0
    for r in roots:
        parts = r.findall("part")
        names = _part_names(r)
        part_measures = [p.findall("measure") for p in parts]
        n_local = max((len(ms) for ms in part_measures), default=0)
        n_primary = min(base_count, len(parts))

        for li in range(n_local):
            global_num += 1
            slots: List[Optional[ET.Element]] = [None] * base_count

            # 1. Mapping par POSITION : slot i ← part i (même si c'est un silence).
            for slot in range(n_primary):
                ms = part_measures[slot]
                if li < len(ms):
                    slots[slot] = ms[li]

            # 2. RÉCUPÉRATION divisi : contenu des parts au-delà de la base, placé
            #    dans les slots VIDES (aigu → haut). Le piano est écarté pour ne
            #    pas polluer un slot de voix.
            extras = []
            for pi in range(base_count, len(parts)):
                ms = part_measures[pi]
                if li >= len(ms):
                    continue
                mel = ms[li]
                if _has_notes(mel) and not _looks_like_piano(names.get(parts[pi].get("id"))):
                    extras.append((_median_pitch(mel), mel))
            extras.sort(key=lambda e: e[0], reverse=True)
            ei = 0
            for slot in range(base_count):
                if ei >= len(extras):
                    break
                cur = slots[slot]
                if cur is None or not _has_notes(cur):
                    slots[slot] = extras[ei][1]
                    ei += 1

            # 3. Écriture : slot resté vide → mesure vide (l'aval comble d'un
            #    silence pleine mesure). Renumérotation continue.
            for slot in range(base_count):
                mel = slots[slot]
                if mel is None:
                    mel = ET.Element("measure")
                mel.set("number", str(global_num))
                merged[slot].append(mel)

    # Reconstruire le document de base : même en-tête + part-list, parts fusionnées.
    for p in base.findall("part"):
        base.remove(p)
    for slot, pid in enumerate(part_ids):
        part_el = ET.SubElement(base, "part")
        if pid is not None:
            part_el.set("id", pid)
        for m in merged[slot]:
            part_el.append(m)
    return ET.tostring(base, encoding="unicode")
