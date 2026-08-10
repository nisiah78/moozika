#!/usr/bin/env python3
"""Analyse un MusicXML (sortie Audiveris, éventuellement fusionnée) pour séparer
les erreurs OMR des erreurs de conversion.

Affiche :
  1. les <time> BRUTS déclarés par Audiveris (1re part, 16 premières mesures) ;
  2. les warnings de conversion (changements d'armure/mètre, rythme approximatif) ;
  3. les mètres APRÈS conversion (voix 0) + tonique d'en-tête ;
  4. les premières notes du soprano : hauteur absolue -> syllabe sol-fa.

Usage (depuis la racine du repo) :
    # 1) sauver une fois le MusicXML fusionné (lent, ~20 min) :
    curl -s --max-time 2400 -F file=@docs/solfege/jubilate-deo-peter-anglea.pdf \\
      localhost:8081/recognize \\
      | python3 -c "import sys,json;open('/tmp/jub.xml','w').write(json.load(sys.stdin)['musicxml'])"
    # 2) analyser (instantané) :
    python3 apps/omr-service/diagnose_notes.py /tmp/jub.xml
"""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.solfa.from_musicxml import read_musicxml  # noqa: E402
from app.staff.consolidate import consolidate_omr_voices  # noqa: E402


def _strip_ns(root: ET.Element) -> None:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def _acc(alter: int) -> str:
    return "#" * alter if alter > 0 else "b" * (-alter)


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/jub.xml"
    xml = open(path, encoding="utf-8", errors="replace").read()

    root = ET.fromstring(xml)
    _strip_ns(root)
    parts = root.findall("part")
    print(f"MusicXML : {path} — {len(parts)} parts\n")

    print("== <time> BRUTS déclarés par Audiveris (1re part, 16 mesures) ==")
    first = parts[0] if parts else None
    if first is not None:
        for m in first.findall("measure")[:16]:
            t = m.find(".//time")
            if t is not None:
                print(f"  m{m.get('number')}: {t.findtext('beats')}/{t.findtext('beat-type')}")

    res = read_musicxml(xml, quantize_rhythm=True, on_chord="split")
    print("\n== warnings de conversion ==")
    for w in res.warnings[:20]:
        print("  •", w)
    print("  (predominant_time =", res.predominant_time, ")")

    models = consolidate_omr_voices(res.models)
    if not models:
        print("\n(aucune voix après consolidation)")
        return
    m0 = models[0]
    print(f"\n== après conversion — voix « {m0.part_name} » ==")
    print(f"  en-tête : {m0.beats}/{m0.beat_type}  tonic={m0.tonic}  doh_octave={m0.doh_octave}")
    print("  changements de mètre posés sur les mesures :")
    for i, meas in enumerate(m0.measures[:16]):
        if meas.time_signature:
            print(f"    m{i + 1} → {meas.time_signature[0]}/{meas.time_signature[1]}")

    print("\n== premières notes du soprano (hauteur absolue → syllabe) ==")
    cnt = 0
    for meas in m0.measures:
        for n in meas.notes:
            if n.is_rest or not n.pitch:
                continue
            p = n.pitch
            print(f"  {p.step}{_acc(p.alter)}{p.octave}  →  {p.syllable!r}")
            cnt += 1
            if cnt >= 8:
                break
        if cnt >= 8:
            break

    print("\n== TOUTES les voix : clé + 1res notes + position sur la portée ==")
    print("   (pos : ligne du bas = 0 ; 5 lignes = 0..8 ; > 8 = au-dessus = « trop haut »)")
    for m in models:
        clef = "bass" if m.clef == "bass" else "treble"
        bottom = _STAFF_BOTTOM[clef]
        line = f"  {m.part_name} [{clef}] : "
        notes = []
        for meas in m.measures:
            for n in meas.notes:
                if n.is_rest or not n.pitch:
                    continue
                p = n.pitch
                idx = p.octave * 7 + _STEP_IDX.get(p.step.upper(), 0)
                pos = idx - bottom
                notes.append(f"{p.step}{_acc(p.alter)}{p.octave}(pos{pos})")
                if len(notes) >= 5:
                    break
            if len(notes) >= 5:
                break
        print(line + "  ".join(notes))


_STEP_IDX = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
# ligne du bas : treble = E4, bass = G2 (cf. staffPitch.ts).
_STAFF_BOTTOM = {"treble": 4 * 7 + 2, "bass": 2 * 7 + 4}


if __name__ == "__main__":
    main()
