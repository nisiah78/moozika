"""Nettoyage des voix OMR (Audiveris) avant affichage sol-fa."""
from __future__ import annotations

from typing import List, Optional

from ..solfa.model import Measure, NoteEl, ScoreModel
from ..solfa.rhythm import split_duration

_PIANO_NAMES = frozenset({"piano", "keyboard", "orgue", "organ"})
_STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Programmes General MIDI (1-based) de clavier : pianos 1-8, orgues 17-24.
_KEYBOARD_MIDI = frozenset(range(1, 9)) | frozenset(range(17, 25))


def _part_base(name: str) -> str:
    return name.split(" v")[0].strip().lower()


def _is_generic_name(name: str) -> bool:
    """« Voice » (placeholder propre à Audiveris pour une part sans titre lu
    sur la partition) / « Voix » (notre repli quand <part-name> manque) / id de
    part brut — aucun n'est un VRAI nom de voix. Miroir de la même notion dans
    ``from_musicxml._assign_satb_names`` (même cause racine, deux points de
    nommage SATB dans le pipeline portée)."""
    base = _part_base(name)
    return base in ("", "voix", "voice", "p1", "p2", "p3", "p4") or base.startswith(
        ("voix", "voice")
    )


def _is_piano(name: str) -> bool:
    return _part_base(name) in _PIANO_NAMES


_CANONICAL_LABELS = ("Soprano", "Alto", "Tenor", "Bass")


def _detected_label(name: str) -> Optional[str]:
    """Label SATB canonique si ``name`` le désigne EXPLICITEMENT (donnée lue
    sur la partition via l'OCR Audiveris, ex. « Tenor2 », « Basse » — pas une
    estimation par tessiture). None si le nom ne porte aucune identité
    reconnaissable (generique, ou role hors SATB comme « Baryton »)."""
    base = _part_base(name)
    if "soprano" in base:
        return "Soprano"
    if "alto" in base:
        return "Alto"
    if "tenor" in base or "ténor" in base:
        return "Tenor"
    if "bass" in base or "basse" in base:
        return "Bass"
    return None


def _is_accompaniment(model: ScoreModel) -> bool:
    """Rôle STRUCTUREL (pas seulement le nom). Précédence : nombre de portées
    (2 = grand portée clavier) > nom piano/orgue > timbre MIDI clavier. Le nom
    d'Audiveris pouvant être faux, la structure prime."""
    if getattr(model, "staff_count", 1) >= 2:
        return True
    if _is_piano(model.part_name):
        return True
    if getattr(model, "midi_program", None) in _KEYBOARD_MIDI:
        return True
    return False


def _pitch_height(step: str, alter: int, octave: int) -> int:
    return octave * 12 + _STEPS.get(step.upper(), 0) + alter


def _note_count(model: ScoreModel) -> int:
    return sum(
        1
        for meas in model.measures
        for n in meas.notes
        if not n.is_rest and n.pitch
    )


def _median_height(model: ScoreModel) -> float:
    hs = [
        _pitch_height(n.pitch.step, n.pitch.alter, n.pitch.octave)
        for meas in model.measures
        for n in meas.notes
        if n.pitch
    ]
    if not hs:
        return 0.0
    hs.sort()
    return hs[len(hs) // 2]


def _overlay_notes(base: List[NoteEl], donor: List[NoteEl]) -> List[NoteEl]:
    """Superpose les notes de ``donor`` sur les SILENCES de ``base`` (même mesure).

    Composition (§7.3) : une voix ne « se tait » sur un temps que si l'OMR a mis
    sa note dans un flux de voix séparé. On lit donc la note du donneur LÀ où la
    voix de base est silencieuse — jamais par-dessus une vraie note (pas de
    conflit), et sans changer la durée totale de la mesure (le temps reste juste).
    """
    cap = sum(n.duration for n in base)
    if cap <= 0:
        return base
    # grille des « propriétaires » par division : None = silence.
    grid: List = [None] * cap
    pos = 0
    for n in base:
        if not n.is_rest and pos < cap:
            grid[pos] = ("start", n)
            for j in range(pos + 1, min(pos + n.duration, cap)):
                grid[j] = ("cont", None)
        pos += n.duration
    # superpose le donneur uniquement sur des plages entièrement silencieuses.
    pos = 0
    changed = False
    for n in donor:
        span_end = pos + n.duration
        if not n.is_rest and pos < cap and span_end <= cap:
            if all(grid[j] is None for j in range(pos, span_end)):
                grid[pos] = ("start", n)
                for j in range(pos + 1, span_end):
                    grid[j] = ("cont", None)
                changed = True
        pos = span_end
    if not changed:
        return base
    # reconstruit la séquence NoteEl (notes conservées telles quelles ; les
    # silences restants re-décomposés proprement).
    out: List[NoteEl] = []
    i = 0
    while i < cap:
        cell = grid[i]
        if cell is None:
            j = i
            while j < cap and grid[j] is None:
                j += 1
            for value, ntype, dots in split_duration(j - i):
                out.append(NoteEl(True, value, ntype, dots))
            i = j
        elif cell[0] == "start":
            note = cell[1]
            out.append(note)
            i += max(1, note.duration)
        else:  # 'cont' sans start (ne devrait pas arriver) — on avance
            i += 1
    return out


def _recover_dropped_voice(target: ScoreModel, donor: ScoreModel) -> None:
    """Récupère le contenu d'une voix OMR écartée dans la voix gardée la plus
    proche (par registre), mesure par mesure, en comblant ses silences."""
    n = min(len(target.measures), len(donor.measures))
    for i in range(n):
        dmeas = donor.measures[i]
        if any(not x.is_rest for x in dmeas.notes):
            target.measures[i].notes = _overlay_notes(
                target.measures[i].notes, dmeas.notes
            )


def _select_piano_lines(piano: List[ScoreModel], *, min_notes: int = 8) -> List[ScoreModel]:
    """Piano → au plus une ligne par main : la voix la plus fournie de chaque
    portée (aiguë = main droite, grave = main gauche). Les accords de piano ont
    déjà été réduits à leur note supérieure (le piano n'est pas scindé)."""
    lines: List[ScoreModel] = []
    for clef, label in (("treble", "Piano (main droite)"), ("bass", "Piano (main gauche)")):
        cands = [m for m in piano if m.clef == clef and _note_count(m) >= min_notes]
        if cands:
            best = max(cands, key=_note_count)
            best.part_name = label
            lines.append(best)
    return lines


def _name_voices(kept: List[ScoreModel]) -> None:
    """Nomme les voix triées par registre (aigu→grave). ≤4 voix : SATB — en
    priorité par IDENTITÉ RÉELLE (nom lu sur la partition, ex. « Tenor2 » via
    l'OCR Audiveris) quand elle désigne explicitement un pupitre SATB ; jamais
    une estimation par tessiture quand une donnée lue existe (cf. TTBB pris à
    tort pour SATB : 2 voix nommées « Tenor » ne doivent plus ressortir
    Soprano/Alto). Les positions restantes (identité non détectée) sont
    comblées par tessiture, comportement historique inchangé. Au-delà de 4 voix
    (divisi), on garde les repères SATB par registre et on suffixe les voix
    d'un même pupitre ``I``/``II`` (ex. 2 voix aiguës → Soprano I / Soprano
    II) — l'identité réelle n'est pas encore branchée sur ce chemin (divisi
    franc, cas rare)."""
    n = len(kept)
    if n <= 4:
        canonical = _CANONICAL_LABELS[:n]
        detected = [_detected_label(m.part_name) for m in kept]
        # 1. Ancrer les identités RÉELLEMENT détectées, dans l'ordre de
        #    tessiture (kept est déjà trié aigu→grave) : la 1re occurrence d'un
        #    label prend le label nu, une 2e occurrence (même pupitre en 2 voix,
        #    ex. 2 ténors) prend le suffixe I/II.
        counts: dict = {}
        for d in detected:
            if d in canonical:
                counts[d] = counts.get(d, 0) + 1
        assigned: List[Optional[str]] = [None] * n
        seen: dict = {}
        used_labels = set()
        for i, d in enumerate(detected):
            if d in canonical:
                seen[d] = seen.get(d, 0) + 1
                assigned[i] = f"{d} {_roman(seen[d])}" if counts[d] > 1 else d
                used_labels.add(d)
        # 2. Compléter les positions non ancrées avec les labels canoniques
        #    RESTANTS, dans l'ordre de tessiture — comportement historique quand
        #    aucune identité n'est détectée nulle part.
        free_labels = [l for l in canonical if l not in used_labels]
        fi = 0
        for i in range(n):
            if assigned[i] is None:
                assigned[i] = free_labels[fi] if fi < len(free_labels) else canonical[i]
                fi += 1
        for m, name in zip(kept, assigned):
            m.part_name = name
        return
    # >4 voix : répartir les n voix (triées aigu→grave) en 4 pupitres par rang,
    # au plus équilibré, puis numéroter les pupitres qui portent plusieurs voix.
    labels = ("Soprano", "Alto", "Tenor", "Bass")
    # base par pupitre + répartition du surplus vers les pupitres AIGUS (le divisi
    # de soprano est le plus courant), sans dépasser 4 pupitres.
    per = [1, 1, 1, 1]
    extra = n - 4
    idx = 0
    while extra > 0:
        per[idx % 4] += 1
        extra -= 1
        idx += 1
    out = 0
    for band, count in enumerate(per):
        for k in range(count):
            if out >= n:
                break
            label = labels[band]
            kept[out].part_name = f"{label} {_roman(k + 1)}" if count > 1 else label
            out += 1


def _roman(i: int) -> str:
    return {1: "I", 2: "II", 3: "III", 4: "IV"}.get(i, str(i))


def _temporally_disjoint(a: ScoreModel, b: ScoreModel) -> bool:
    """Vrai si a et b ne chantent JAMAIS sur la même mesure (fragments d'une même
    ligne répartis entre sections) — par opposition à un divisi simultané."""
    n = min(len(a.measures), len(b.measures))
    for i in range(n):
        if (any(not x.is_rest for x in a.measures[i].notes)
                and any(not x.is_rest for x in b.measures[i].notes)):
            return False
    return True


def _cluster_lines(models: List[ScoreModel]) -> List[ScoreModel]:
    """Regroupe les modèles vocaux en lignes SATB. Les plus fournis servent
    d'ANCRES ; un modèle plus petit est FUSIONNÉ (comble les silences de l'ancre)
    dans l'ancre du même registre s'il ne chante JAMAIS en même temps qu'elle —
    c'est le même pupitre éclaté entre sections (ex. Ténor condensé mesures 1-61
    + Ténor séparé mesures 62-73). Deux vraies voix simultanées (divisi) restent
    distinctes. Évite ainsi les voix-fragments quasi-vides après la fusion OMR."""
    lines: List[ScoreModel] = []
    for m in sorted(models, key=_note_count, reverse=True):
        mh = _median_height(m)
        mc = _note_count(m)
        target = None
        best = 1e9
        for k in lines:
            # fragment (nettement plus petit), même registre (≤ quinte), disjoint.
            if mc > 0.6 * _note_count(k):
                continue
            d = abs(_median_height(k) - mh)
            if d <= 7 and d < best and _temporally_disjoint(k, m):
                best, target = d, k
        if target is not None:
            _recover_dropped_voice(target, m)
        else:
            lines.append(m)
    return lines


def consolidate_omr_voices(
    models: List[ScoreModel], *, max_voices: int = 8, include_piano: bool = True,
    warnings: Optional[List[str]] = None,
) -> List[ScoreModel]:
    """Nettoie le bruit OMR → lignes chorales SATB nommées par IDENTITÉ.

    Trois temps : (1) les FRAGMENTS d'un même pupitre éclatés entre sections par
    la fusion (ex. Ténor condensé mes.1-61 + Ténor séparé mes.62-73) sont
    recollés en une ligne continue via ``_cluster_lines`` (fusion des flux de
    même registre JAMAIS simultanés) ; (2) les 4 lignes les plus fournies sont les
    ANCRES S/A/T/B, tout reliquat n'étant promu voix distincte (divisi I/II) que
    s'il est substantiel ET simultané, sinon absorbé (§7.3 : comble les silences,
    jamais par-dessus une vraie note) ; (3) nommage par tessiture (aigu→grave).
    ``max_voices`` borne le nombre de lignes (garde-fou anti-explosion).
    ``warnings`` (optionnel) reçoit un avertissement quand le nommage S/A/T/B
    est une ESTIMATION par tessiture faute de tout nom lisible sur la partition
    (Audiveris ne préserve alors aucun libellé exploitable) — à distinguer d'un
    nommage confirmé par un vrai ``<part-name>``."""
    choral = [m for m in models if not _is_accompaniment(m)]
    piano = [m for m in models if _is_accompaniment(m)]
    if not choral:
        choral = list(models)
        piano = []

    # 1. Regrouper les FRAGMENTS d'un même pupitre (éclatés entre sections par la
    #    fusion OMR) en lignes continues — sans fusionner deux voix simultanées.
    active = [m for m in choral if _note_count(m) > 0] or choral[:1]
    lines = _cluster_lines(active)

    # 2. Les 4 lignes les plus fournies sont les ANCRES SATB. Un reliquat au-delà
    #    n'est promu voix distincte (vrai divisi → I/II) que s'il est SUBSTANTIEL
    #    (≥ moitié de son ancre) ET chante EN MÊME TEMPS qu'elle ; sinon c'est du
    #    bruit / de la sur-segmentation → absorbé dans l'ancre la plus proche
    #    (comble ses silences). Évite les voix-fragments quasi-vides mal étiquetées.
    lines.sort(key=_note_count, reverse=True)
    kept = lines[:4]
    for donor in lines[4:]:
        dh = _median_height(donor)
        anchor = min(kept, key=lambda m: abs(_median_height(m) - dh))
        is_divisi = (
            _note_count(donor) >= 0.5 * _note_count(anchor)
            and not _temporally_disjoint(anchor, donor)
        )
        if is_divisi and len(kept) < max_voices:
            kept.append(donor)
        else:
            _recover_dropped_voice(anchor, donor)

    # 3. Nommer par tessiture (aigu→grave) : S/A/T/B (+ I/II pour les vrais divisi).
    kept.sort(key=_median_height, reverse=True)
    generic_before = bool(kept) and all(_is_generic_name(m.part_name) for m in kept)
    _name_voices(kept)
    if generic_before and warnings is not None:
        entry = (
            "[part-name] noms de voix non fournis par Audiveris — attribution "
            "Soprano/Alto/Tenor/Bass par tessiture (estimation, pas une donnée "
            "lue). Une voix de ténor notée en clé de Sol classique peut sonner "
            "une octave plus bas que noté : vérifiez au son, corrigez via le "
            "bouton d'octave de la vue Partition si besoin."
        )
        if entry not in warnings:
            warnings.append(entry)

    if include_piano and piano:
        kept.extend(_select_piano_lines(piano))
    return kept
