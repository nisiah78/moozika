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

import copy
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Dict, List, Optional

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


# Programmes General MIDI (1-based) de clavier : pianos/clavecin/célesta 1-8,
# orgues 17-24. Un tel timbre = accompagnement, pas une voix chantée.
_KEYBOARD_MIDI = frozenset(range(1, 9)) | frozenset(range(17, 25))


def _part_meta(root: ET.Element) -> List[dict]:
    """Métadonnées structurelles par part, ALIGNÉES sur ``root.findall('part')``.

    ``accomp`` = ``staves>=2`` (grand portée = clavier) OU timbre clavier OU nom
    piano/orgue. C'est le signal qui empêche un accompagnement de remplir un slot
    de voix chantée lors de la fusion (cause du bug « orgue → Ténor/Basse »)."""
    names: dict = {}
    midis: dict = {}
    for sp in root.findall("part-list/score-part"):
        pid = sp.get("id")
        names[pid] = sp.findtext("part-name") or ""
        mp = sp.findtext("midi-instrument/midi-program")
        try:
            midis[pid] = int(mp) if mp else None
        except ValueError:
            midis[pid] = None
    out: List[dict] = []
    for p in root.findall("part"):
        pid = p.get("id")
        staves = 1
        for m in p.findall("measure"):
            for a in m.findall("attributes"):
                s = a.findtext("staves")
                if s:
                    try:
                        staves = max(staves, int(s))
                    except ValueError:
                        pass
        name = names.get(pid, "")
        midi = midis.get(pid)
        accomp = (staves >= 2) or (midi in _KEYBOARD_MIDI) or _looks_like_piano(name)
        out.append(
            {"id": pid, "name": name, "midi": midi, "staves": staves, "accomp": accomp}
        )
    return out


# ── Dé-condensation SATB (levier n°1) ───────────────────────────────────────
# Audiveris rend souvent un chœur SATB CONDENSÉ : Soprano+Alto (ou Ténor+Basse)
# écrits sur UNE seule portée, en 2 <voice> distinctes. Une telle part occupe
# alors UN seul slot de voix à la fusion → l'Alto (voix du bas) est écrasé/perdu
# et le mapping de slot devient incohérent d'un système à l'autre (S+A condensé
# vs S/A séparés en divisi). On sépare donc, AVANT le mapping, toute part vocale
# à ≥2 voix substantielles en autant de parts mono-voix (triées aigu→grave),
# pour que slot0=Soprano, slot1=Alto… restent stables sur toute la partition.
# Le cas « Ténor+Basse en ACCORDS sur 1 portée » de façon MAJORITAIRE (chœur
# jamais réellement séparé par Audiveris) reste géré en aval par
# from_musicxml._split_chord_streams (phase 2) — CE garde-fou-là exige une
# fraction d'accords substantielle sur l'ENSEMBLE de la voix et décline sciemment
# dès qu'une voix sœur substantielle existe déjà sur la portée. Il ne couvre donc
# PAS le cas d'une part déjà dé-condensée en 2 voix stables sur la majorité de la
# partition, où UNE SEULE mesure (typiquement l'accord final, en rondes SANS
# hampe donc sans signal de séparation) regresse en un unique <voice> accordé :
# cf. _redistribute_collapsed_chord ci-dessous, qui comble précisément ce vide.

def _voice_note_counts(measures: List[ET.Element]) -> Counter:
    """Notes chantées (hors silence, accord, agrément) par <voice>."""
    c: Counter = Counter()
    for m in measures:
        for n in m.findall("note"):
            if (n.find("rest") is not None or n.find("chord") is not None
                    or n.find("grace") is not None):
                continue
            c[n.findtext("voice") or "1"] += 1
    return c


def _voice_median_pitch(measures: List[ET.Element], voice: str) -> float:
    """Hauteur médiane approx des notes d'une voix (pour trier par tessiture)."""
    hs: List[int] = []
    for m in measures:
        for n in m.findall("note"):
            if (n.findtext("voice") or "1") != voice:
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


def _condensed_clusters(measures: List[ET.Element]) -> Optional[List[List[str]]]:
    """Détecte un SATB condensé (≥2 voix substantielles sur 1 portée) et renvoie
    les clusters de voix à séparer, un par voix substantielle, TRIÉS aigu→grave.
    Chaque voix mineure (bruit OMR / bref reliquat) est rattachée au cluster
    substantiel le plus proche en tessiture — AUCUNE note n'est perdue. Renvoie
    None si la part n'est pas condensée (0 ou 1 voix substantielle)."""
    counts = _voice_note_counts(measures)
    if len(counts) < 2:
        return None
    total = sum(counts.values())
    # Conservateur : une vraie 2e voix pèse une fraction notable du total ; en
    # deçà, c'est un artefact d'OMR (numéro de voix parasite) → pas une voix SATB.
    thresh = max(4, int(total * 0.15))
    substantial = sorted(
        (v for v, c in counts.items() if c >= thresh),
        key=lambda v: _voice_median_pitch(measures, v),
        reverse=True,
    )
    if len(substantial) < 2:
        return None
    clusters: Dict[str, List[str]] = {v: [v] for v in substantial}
    sub_med = {v: _voice_median_pitch(measures, v) for v in substantial}
    for v in counts:
        if v in clusters:
            continue
        mv = _voice_median_pitch(measures, v)
        nearest = min(substantial, key=lambda s: abs(sub_med[s] - mv))
        clusters[nearest].append(v)
    return [clusters[v] for v in substantial]


def _note_semitone(n: ET.Element) -> Optional[int]:
    """Hauteur en demi-tons d'une note, ou None si silence/agrément/hauteur
    non exploitable (mêmes règles que ``_median_pitch``/``_voice_median_pitch``,
    factorisées ici pour le filet de sécurité ci-dessous)."""
    if n.find("rest") is not None or n.find("grace") is not None:
        return None
    p = n.find("pitch")
    if p is None:
        return None
    step = (p.findtext("step") or "C").strip().upper()
    try:
        octave = int(p.findtext("octave", "4") or "4")
        alter = int(float(p.findtext("alter", "0") or "0"))
    except ValueError:
        return None
    return octave * 12 + _STEP.get(step, 0) + alter


def _chord_stacks(notes: List[ET.Element]) -> List[List[ET.Element]]:
    """Découpe une liste de <note> d'UNE MÊME voix (ordre document) en piles
    d'accord : chaque pile = [racine (sans <chord>), notes <chord/> qui suivent
    immédiatement]. Une pile de longueur 1 = note/silence isolé."""
    stacks: List[List[ET.Element]] = []
    for n in notes:
        if n.find("chord") is None or not stacks:
            stacks.append([n])
        else:
            stacks[-1].append(n)
    return stacks


def _redistribute_collapsed_chord(
    measure_el: ET.Element, clusters: List[List[str]]
) -> ET.Element:
    """Filet de sécurité LOCAL, une seule mesure à la fois : si Audiveris a
    rendu un accord (notes SANS hampe → aucun signal de séparation de voix,
    typiquement l'accord final en rondes) sous UN SEUL <voice>, alors qu'un
    cluster déjà établi ailleurs dans la partition n'a AUCUNE note dans cette
    mesure précise, redistribue les hauteurs de l'accord aigu→slot du haut vers
    les clusters vides (même convention que ``_median_pitch`` ailleurs dans ce
    module). Renvoie ``measure_el`` INCHANGÉ dans tous les autres cas — ne
    touche jamais au seuil global de ``_condensed_clusters`` : ce n'est jamais
    un séparateur d'accords général, seulement un filet pour l'unique situation
    où l'alternative est une perte de note certaine (mesure totalement vide)."""
    notes_by_voice: Dict[str, List[ET.Element]] = {}
    for n in measure_el.findall("note"):
        notes_by_voice.setdefault(n.findtext("voice") or "1", []).append(n)

    empty_idxs = [
        k for k, cluster in enumerate(clusters)
        if not any(v in notes_by_voice for v in cluster)
    ]
    if not empty_idxs:
        return measure_el  # aucun cluster vide : rien à récupérer (accord
        # normal ou harmonie doublée légitimement) — cas le plus fréquent,
        # coût nul.

    for donor_k, cluster in enumerate(clusters):
        if donor_k in empty_idxs:
            continue
        for v in cluster:
            notes = notes_by_voice.get(v)
            if not notes:
                continue
            for stack in _chord_stacks(notes):
                if len(stack) != len(notes):
                    continue  # l'accord n'est pas la TOTALITÉ du contenu de
                    # cette voix pour cette mesure → migrer casserait le timing
                    # (pas de <backup> pour repositionner les autres notes).
                heights = [_note_semitone(n) for n in stack]
                if any(h is None for h in heights) or len(set(heights)) != len(heights):
                    continue  # hauteur non lisible, ou doublon/unisson dans
                    # l'accord (ordre <chord> ambigu) : laissé tel quel.
                if len(heights) - 1 != len(empty_idxs):
                    continue  # correspondance non univoque accord↔slots vides
                target_slots = sorted([donor_k] + empty_idxs)
                desc_pitches = sorted(set(heights), reverse=True)
                nm = copy.deepcopy(measure_el)
                nm_by_voice: Dict[str, List[ET.Element]] = {}
                for n in nm.findall("note"):
                    nm_by_voice.setdefault(n.findtext("voice") or "1", []).append(n)
                nm_stack = next(
                    (s for s in _chord_stacks(nm_by_voice.get(v, [])) if len(s) == len(stack)),
                    None,
                )
                if nm_stack is None:
                    continue
                for slot, pitch_val in zip(target_slots, desc_pitches):
                    match = next(n for n in nm_stack if _note_semitone(n) == pitch_val)
                    chord_el = match.find("chord")
                    if chord_el is not None:
                        match.remove(chord_el)
                    if slot != donor_k:
                        ve = match.find("voice")
                        if ve is None:
                            ve = ET.SubElement(match, "voice")
                        ve.text = clusters[slot][0]
                return nm
    return measure_el


def _rebuild_measure(measure_el: ET.Element, voices: List[str]) -> ET.Element:
    """Reconstruit une mesure ne gardant que ``voices`` (ordre = voice 1, 2…),
    avec des <backup> propres entre voix. Conserve les enfants partagés
    (attributes, direction, print…) en tête et <barline> en fin ; supprime les
    <backup>/<forward> d'origine (recalculés). Les silences par voix sont
    conservés (aucune note perdue)."""
    nm = ET.Element("measure", dict(measure_el.attrib))
    leading: List[ET.Element] = []
    trailing: List[ET.Element] = []
    notes_by_v: Dict[str, List[ET.Element]] = {}
    for child in measure_el:
        if child.tag == "note":
            notes_by_v.setdefault(child.findtext("voice") or "1", []).append(child)
        elif child.tag in ("backup", "forward"):
            continue
        elif child.tag == "barline":
            trailing.append(child)
        else:
            leading.append(child)
    for c in leading:
        nm.append(copy.deepcopy(c))
    written = [v for v in voices if notes_by_v.get(v)]
    for i, v in enumerate(written):
        if i > 0:
            prev = notes_by_v[written[i - 1]]
            dur = sum(int(n.findtext("duration", "0") or 0)
                      for n in prev if n.find("chord") is None)
            if dur > 0:
                ET.SubElement(ET.SubElement(nm, "backup"), "duration").text = str(dur)
        for n in notes_by_v[v]:
            nc = copy.deepcopy(n)
            ve = nc.find("voice")
            if ve is None:
                ve = ET.SubElement(nc, "voice")
            ve.text = str(i + 1)
            nm.append(nc)
    for c in trailing:
        nm.append(copy.deepcopy(c))
    return nm


def _decondense_root(root: ET.Element) -> None:
    """Sépare en place toute part VOCALE condensée (≥2 voix) en parts mono-voix
    (aigu→grave). Met à jour part-list et l'ordre des <part>. No-op sinon."""
    plist = root.find("part-list")
    if plist is None:
        return
    metas = _part_meta(root)               # aligné à root.findall('part')
    parts = root.findall("part")
    sp_by_id = {sp.get("id"): sp for sp in plist.findall("score-part")}
    rebuilt: List[tuple] = []              # (score_part | None, part_el)
    changed = False
    for meta, part in zip(metas, parts):
        pid = meta["id"]
        measures = part.findall("measure")
        clusters = None if meta["accomp"] else _condensed_clusters(measures)
        if clusters and len(clusters) >= 2:
            adjusted = [_redistribute_collapsed_chord(m, clusters) for m in measures]
            for k, cluster in enumerate(clusters):
                nid = f"{pid}_v{k + 1}"
                np = ET.Element("part", {"id": nid})
                for m in adjusted:
                    np.append(_rebuild_measure(m, cluster))
                sp = sp_by_id.get(pid)
                nsp = copy.deepcopy(sp) if sp is not None else ET.Element(
                    "score-part", {"id": nid})
                nsp.set("id", nid)
                rebuilt.append((nsp, np))
            changed = True
        else:
            rebuilt.append((sp_by_id.get(pid), part))
    if not changed:
        return
    for sp in plist.findall("score-part"):
        plist.remove(sp)
    for nsp, _ in rebuilt:
        if nsp is not None:
            plist.append(nsp)
    for p in root.findall("part"):
        root.remove(p)
    for _, p in rebuilt:
        root.append(p)


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
        _decondense_root(r)   # SATB condensé → parts mono-voix (avant le mapping)
        roots.append(r)

    counts = [len(r.findall("part")) for r in roots]
    counts = [c for c in counts if c > 0]
    if not counts:
        raise ValueError("aucune part exploitable dans les pages")
    # Base = structure la plus FRÉQUENTE… SAUF si une (ou des) page(s) porte(nt)
    # PLUS de parties AVEC DU VRAI CONTENU (divisi : chaque voix passe sur sa propre
    # portée sur quelques pages, ex. jubilate m62-71). Dans ce cas on adopte la
    # structure LARGE comme base, pour ne pas écraser les voix du divisi. Un simple
    # « plus de parts » ne suffit pas : Audiveris ajoute parfois une part de silence
    # parasite — on exige que ces parts supplémentaires contiennent des NOTES.
    def _part_notes(part_el: ET.Element) -> bool:
        return any(_has_notes(m) for m in part_el.findall("measure"))

    # Base = la page qui porte le PLUS de parties AVEC DE VRAIES NOTES. Sur une
    # partition condensée puis en divisi (jubilate : 3 portées, puis 4 voix + piano
    # aux mesures 62-71), c'est la page de divisi qui définit la structure LARGE —
    # sinon on collapse tout sur les 3 portées et on écrase les voix divisées. Le
    # critère « avec notes » ignore une part de silence parasite (Audiveris en ajoute
    # parfois une) : elle ne doit pas gonfler la base (cf. test synthétique tout-silence
    # qui reste à 3). À égalité, la 1re page de structure la plus fréquente gagne.
    common = Counter(counts).most_common(1)[0][0]
    base = next(r for r in roots if len(r.findall("part")) == common)
    best_notes = sum(1 for p in base.findall("part") if _part_notes(p))
    for r in roots:
        with_notes = sum(1 for p in r.findall("part") if _part_notes(p))
        if with_notes > best_notes:
            base, best_notes = r, with_notes
    base_count = len(base.findall("part"))
    part_ids = [p.get("id") for p in base.findall("part")]

    # Rôle de chaque slot de base (aligné à part_ids) → les slots de voix et
    # d'accompagnement sont alimentés SÉPARÉMENT (cf. boucle) pour qu'un
    # accompagnement ne tombe jamais dans un slot de voix.
    base_roles = [m["accomp"] for m in _part_meta(base)]
    base_vocal_slots = [i for i, a in enumerate(base_roles) if not a]
    base_accomp_slots = [i for i, a in enumerate(base_roles) if a]

    merged: dict = {slot: [] for slot in range(base_count)}
    global_num = 0
    for r in roots:
        parts = r.findall("part")
        metas = _part_meta(r)  # aligné à parts
        part_measures = [p.findall("measure") for p in parts]
        n_local = max((len(ms) for ms in part_measures), default=0)

        # Assignation STABLE part→slot PAR RÔLE (remplace le mapping par index) :
        # les parts vocales remplissent les slots vocaux (dans l'ordre), les
        # accompagnements les slots d'accompagnement. Un accompagnement ne peut
        # donc JAMAIS occuper un slot de voix — c'était le bug (page à 2 parts :
        # l'orgue, en position 1, tombait dans un slot « Voice »). Les parts
        # vocales surnuméraires alimentent la récupération divisi.
        target: dict = {}          # index de part → slot de base
        extra_vocal: List[int] = []
        vi = ai = 0
        for pi, meta in enumerate(metas):
            if meta["accomp"]:
                if ai < len(base_accomp_slots):
                    target[pi] = base_accomp_slots[ai]
                    ai += 1
                # accompagnement surnuméraire (pas de slot) → ignoré ici
            elif vi < len(base_vocal_slots):
                target[pi] = base_vocal_slots[vi]
                vi += 1
            else:
                extra_vocal.append(pi)

        for li in range(n_local):
            global_num += 1
            slots: List[Optional[ET.Element]] = [None] * base_count

            # 1. Mapping stable par rôle (jamais un accompagnement dans une voix).
            for pi, slot in target.items():
                ms = part_measures[pi]
                if li < len(ms):
                    slots[slot] = ms[li]

            # 2. RÉCUPÉRATION divisi : parts VOCALES surnuméraires → slots VOCAUX
            #    vides (aigu → haut). Restreinte aux slots de voix.
            extras = []
            for pi in extra_vocal:
                ms = part_measures[pi]
                if li < len(ms) and _has_notes(ms[li]):
                    extras.append((_median_pitch(ms[li]), ms[li]))
            extras.sort(key=lambda e: e[0], reverse=True)
            ei = 0
            for slot in base_vocal_slots:
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
