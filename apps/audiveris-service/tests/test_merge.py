"""Tests de la fusion MusicXML page-par-page (app/merge.py).

Lancer depuis apps/audiveris-service :
    python3 -m unittest discover -s tests -t .
"""
import unittest
import xml.etree.ElementTree as ET

from app.merge import merge_musicxml


def _condensed_page(nmeasures: int, xmlns: bool = False) -> str:
    """Page à 1 part VOCALE condensée (2 voix sur 1 portée : voice1 aigu E5,
    voice2 grave C4, séparées par <backup>) + 1 part piano (2 portées)."""
    ns = ' xmlns="http://www.musicxml.org/ns"' if xmlns else ""
    vocal = ""
    for j in range(nmeasures):
        vocal += (
            f'<measure number="{j + 1}">'
            "<attributes><divisions>1</divisions></attributes>"
            "<note><pitch><step>E</step><octave>5</octave></pitch>"
            "<duration>4</duration><voice>1</voice></note>"
            "<backup><duration>4</duration></backup>"
            "<note><pitch><step>C</step><octave>4</octave></pitch>"
            "<duration>4</duration><voice>2</voice></note>"
            "</measure>"
        )
    piano = "".join(
        f'<measure number="{j + 1}">'
        "<attributes><divisions>1</divisions><staves>2</staves></attributes>"
        "<note><pitch><step>G</step><octave>3</octave></pitch>"
        "<duration>4</duration><voice>1</voice><staff>1</staff></note>"
        "</measure>"
        for j in range(nmeasures)
    )
    part_list = (
        '<score-part id="P1"><part-name>Altu</part-name></score-part>'
        '<score-part id="P2"><part-name>Piano</part-name></score-part>'
    )
    return (
        f'<score-partwise version="4.0"{ns}><part-list>{part_list}</part-list>'
        f'<part id="P1">{vocal}</part><part id="P2">{piano}</part></score-partwise>'
    )


def _count_sung_notes(root: ET.Element) -> int:
    return sum(
        1
        for p in root.findall("part")
        for m in p.findall("measure")
        for n in m.findall("note")
        if n.find("rest") is None and n.find("chord") is None and n.find("pitch") is not None
    )


def _count_pitched_notes_incl_chords(root: ET.Element) -> int:
    """Notes porteuses de hauteur (accords inclus), silences/agréments exclus —
    utilisé pour vérifier qu'aucune hauteur d'accord n'est perdue lors de la
    redistribution locale d'un accord condensé (contrairement à
    ``_count_sung_notes``, qui exclut délibérément les notes <chord> et ne
    convient donc pas à ce test-là : après redistribution, une des deux notes
    de l'accord perd son marqueur <chord>, ce qui fausserait une comparaison
    avant/après avec le compteur historique)."""
    return sum(
        1
        for p in root.findall("part")
        for m in p.findall("measure")
        for n in m.findall("note")
        if n.find("rest") is None and n.find("grace") is None and n.find("pitch") is not None
    )


def _condensed_page_final_chord(nmeasures: int, second_voice_rest: bool = False) -> str:
    """Comme ``_condensed_page``, mais la DERNIÈRE mesure est un accord collé
    sur voice="1" (racine F4 + <chord/> A4, ronde). voice="2" est soit ABSENTE
    (reproduit le bug confirmé : accord final sans hampe, Audiveris ne sépare
    plus les 2 voix), soit porte un <rest/> explicite (``second_voice_rest`` —
    pour vérifier qu'un silence déjà noté n'est jamais écrasé)."""
    vocal = ""
    for j in range(nmeasures - 1):
        vocal += (
            f'<measure number="{j + 1}">'
            "<attributes><divisions>1</divisions></attributes>"
            "<note><pitch><step>E</step><octave>5</octave></pitch>"
            "<duration>4</duration><voice>1</voice></note>"
            "<backup><duration>4</duration></backup>"
            "<note><pitch><step>C</step><octave>4</octave></pitch>"
            "<duration>4</duration><voice>2</voice></note>"
            "</measure>"
        )
    second_voice_note = (
        "<note><rest/><duration>4</duration><voice>2</voice></note>"
        if second_voice_rest else ""
    )
    vocal += (
        f'<measure number="{nmeasures}">'
        "<attributes><divisions>1</divisions></attributes>"
        '<note><pitch><step>F</step><octave>4</octave></pitch>'
        "<duration>4</duration><voice>1</voice></note>"
        '<note><pitch><step>A</step><octave>4</octave></pitch><chord/>'
        "<duration>4</duration><voice>1</voice></note>"
        f"{second_voice_note}"
        "</measure>"
    )
    piano = "".join(
        f'<measure number="{j + 1}">'
        "<attributes><divisions>1</divisions><staves>2</staves></attributes>"
        "<note><pitch><step>G</step><octave>3</octave></pitch>"
        "<duration>4</duration><voice>1</voice><staff>1</staff></note>"
        "</measure>"
        for j in range(nmeasures)
    )
    part_list = (
        '<score-part id="P1"><part-name>Voix</part-name></score-part>'
        '<score-part id="P2"><part-name>Piano</part-name></score-part>'
    )
    return (
        '<score-partwise version="4.0"><part-list>' + part_list + "</part-list>"
        f'<part id="P1">{vocal}</part><part id="P2">{piano}</part></score-partwise>'
    )


def _page(nparts: int, nmeasures: int, xmlns: bool = False) -> str:
    """Page MusicXML minimale : nparts parts, chacune nmeasures mesures (num. 1..N)."""
    ns = ' xmlns="http://www.musicxml.org/ns"' if xmlns else ""
    part_list = "".join(
        f'<score-part id="P{i + 1}"><part-name>V{i + 1}</part-name></score-part>'
        for i in range(nparts)
    )
    parts = ""
    for i in range(nparts):
        measures = "".join(
            f'<measure number="{j + 1}">'
            f"<note><rest/><duration>4</duration></note></measure>"
            for j in range(nmeasures)
        )
        parts += f'<part id="P{i + 1}">{measures}</part>'
    return f'<score-partwise version="4.0"{ns}><part-list>{part_list}</part-list>{parts}</score-partwise>'


class TestMergeMusicXml(unittest.TestCase):
    def test_measures_concatenated_and_renumbered(self):
        # Reproduit le profil réel : la plupart des pages à 3 parts, une page en
        # divisi à 5 parts (ses 2 parts en trop doivent être ignorées).
        pages = [_page(3, 5), _page(3, 12), _page(5, 4), _page(3, 8)]
        root = ET.fromstring(merge_musicxml(pages))
        parts = root.findall("part")
        # Base = structure la plus fréquente (3 parts).
        self.assertEqual(len(parts), 3)
        for p in parts:
            nums = [int(m.get("number")) for m in p.findall("measure")]
            # Mesures recollées et renumérotées en continu : 5+12+4+8 = 29.
            self.assertEqual(nums, list(range(1, 30)))

    def test_single_page_passthrough(self):
        root = ET.fromstring(merge_musicxml([_page(3, 7)]))
        self.assertEqual(len(root.findall("part")), 3)
        self.assertEqual(len(root.findall("part")[0].findall("measure")), 7)

    def test_namespace_stripped(self):
        # MusicXML avec namespace : doit être fusionné sans plantage.
        root = ET.fromstring(merge_musicxml([_page(2, 3, xmlns=True), _page(2, 3, xmlns=True)]))
        self.assertEqual(len(root.findall("part")), 2)
        self.assertEqual(len(root.findall("part")[0].findall("measure")), 6)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            merge_musicxml([])

    def test_condensed_vocal_part_is_split_by_voice(self):
        # Une part vocale S+A condensée (2 voix) → 2 slots vocaux mono-voix,
        # triés aigu→grave (Soprano E5 avant Alto C4). Le piano reste 1 part.
        root = ET.fromstring(merge_musicxml([_condensed_page(6)]))
        parts = root.findall("part")
        # 2 voix (dé-condensées) + 1 piano = 3 parts.
        self.assertEqual(len(parts), 3)
        # Slot 0 = voix aiguë (E5), slot 1 = voix grave (C4).
        steps0 = {n.findtext("pitch/step") for m in parts[0].findall("measure")
                  for n in m.findall("note") if n.find("pitch") is not None}
        steps1 = {n.findtext("pitch/step") for m in parts[1].findall("measure")
                  for n in m.findall("note") if n.find("pitch") is not None}
        self.assertEqual(steps0, {"E"})
        self.assertEqual(steps1, {"C"})

    def test_decondense_preserves_note_count(self):
        # Aucune note perdue : 6 mes. × (1 E5 + 1 C4) + 6 piano = 18 notes chantées.
        src = ET.fromstring(_condensed_page(6))
        merged = ET.fromstring(merge_musicxml([_condensed_page(6)]))
        self.assertEqual(_count_sung_notes(src), _count_sung_notes(merged))

    def test_single_voice_part_not_split(self):
        # Une part mono-voix ne doit JAMAIS être scindée (pas de faux divisi).
        root = ET.fromstring(merge_musicxml([_page(3, 5)]))
        self.assertEqual(len(root.findall("part")), 3)

    def test_collapsed_final_chord_recovered(self):
        # Reproduit le bug confirmé sur une vraie partition : la dernière
        # mesure est une ronde (donc sans hampe) rendue en accord sur UNE
        # seule voix (F4 racine + A4 <chord/>, voice="1") ; voice="2" est
        # absente de cette mesure précise. Les 2 clusters doivent chacun
        # récupérer une hauteur, aigu → cluster du haut (déjà établi E5>C4
        # sur les mesures précédentes).
        root = ET.fromstring(merge_musicxml([_condensed_page_final_chord(5)]))
        parts = root.findall("part")
        self.assertEqual(len(parts), 3)  # 2 voix dé-condensées + piano
        last0 = parts[0].findall("measure")[-1]
        last1 = parts[1].findall("measure")[-1]
        notes0 = [n for n in last0.findall("note") if n.find("pitch") is not None]
        notes1 = [n for n in last1.findall("note") if n.find("pitch") is not None]
        self.assertEqual(len(notes0), 1)
        self.assertEqual(len(notes1), 1)
        self.assertEqual((notes0[0].findtext("pitch/step"), notes0[0].findtext("pitch/octave")),
                          ("A", "4"))
        self.assertEqual((notes1[0].findtext("pitch/step"), notes1[0].findtext("pitch/octave")),
                          ("F", "4"))

    def test_collapsed_final_chord_preserves_note_count(self):
        # Aucune hauteur perdue : le compteur historique (_count_sung_notes)
        # exclut les notes <chord> par construction, donc inadapté ici (une des
        # 2 notes de l'accord perd son marqueur <chord> après redistribution) —
        # on utilise le compteur dédié qui inclut les accords des deux côtés.
        src = ET.fromstring(_condensed_page_final_chord(5))
        merged = ET.fromstring(merge_musicxml([_condensed_page_final_chord(5)]))
        self.assertEqual(_count_pitched_notes_incl_chords(src), _count_pitched_notes_incl_chords(merged))

    def test_condensed_rest_not_overridden_by_sibling_chord(self):
        # Un <rest> déjà noté explicitement dans le cluster voisin est traité
        # comme un silence INTENTIONNEL : le mécanisme ne doit jamais l'écraser,
        # et l'accord de l'autre cluster doit rester intact (mécanisme inerte).
        root = ET.fromstring(
            merge_musicxml([_condensed_page_final_chord(5, second_voice_rest=True)])
        )
        parts = root.findall("part")
        last0 = parts[0].findall("measure")[-1]
        last1 = parts[1].findall("measure")[-1]
        notes0 = [n for n in last0.findall("note") if n.find("pitch") is not None]
        self.assertEqual(len(notes0), 2)  # accord F4+A4 intact, non redistribué
        self.assertIsNotNone(last1.find("note/rest"))  # silence noté préservé

    def test_condensed_chord_with_other_content_not_split(self):
        # Aucun cluster n'est vide (accord sur voice=1 ET note propre sur
        # voice=2) : le mécanisme ne doit RIEN changer, ce n'est pas un
        # séparateur d'accords général.
        normal_measures = "".join(
            f'<measure number="{j + 1}"><attributes><divisions>1</divisions></attributes>'
            "<note><pitch><step>E</step><octave>5</octave></pitch>"
            "<duration>4</duration><voice>1</voice></note>"
            "<backup><duration>4</duration></backup>"
            "<note><pitch><step>C</step><octave>4</octave></pitch>"
            "<duration>4</duration><voice>2</voice></note></measure>"
            for j in range(4)  # dépasse le seuil "substantiel" des 2 voix
        )
        final_measure = (
            '<measure number="5"><attributes><divisions>1</divisions></attributes>'
            "<note><pitch><step>F</step><octave>4</octave></pitch>"
            "<duration>4</duration><voice>1</voice></note>"
            '<note><pitch><step>A</step><octave>4</octave></pitch><chord/>'
            "<duration>4</duration><voice>1</voice></note>"
            "<backup><duration>4</duration></backup>"
            "<note><pitch><step>D</step><octave>4</octave></pitch>"
            "<duration>4</duration><voice>2</voice></note></measure>"
        )
        page = (
            '<score-partwise version="4.0"><part-list>'
            '<score-part id="P1"><part-name>Voix</part-name></score-part>'
            f'</part-list><part id="P1">{normal_measures}{final_measure}</part>'
            "</score-partwise>"
        )
        root = ET.fromstring(merge_musicxml([page]))
        parts = root.findall("part")
        self.assertEqual(len(parts), 2)
        last0 = parts[0].findall("measure")[-1]
        last1 = parts[1].findall("measure")[-1]
        notes0 = [n for n in last0.findall("note") if n.find("pitch") is not None]
        notes1 = [n for n in last1.findall("note") if n.find("pitch") is not None]
        self.assertEqual(len(notes0), 2)  # accord F4+A4 intact
        self.assertEqual(len(notes1), 1)
        self.assertEqual(notes1[0].findtext("pitch/step"), "D")

    def test_condensed_across_pages_stable_slots(self):
        # Page condensée (S+A) puis page en 2 voix déjà séparées : les slots
        # restent cohérents (S en slot0, A en slot1) et les mesures se recollent.
        root = ET.fromstring(merge_musicxml([_condensed_page(4), _condensed_page(3)]))
        parts = root.findall("part")
        self.assertEqual(len(parts), 3)
        nums = [int(m.get("number")) for m in parts[0].findall("measure")]
        self.assertEqual(nums, list(range(1, 8)))  # 4 + 3 renumérotées


if __name__ == "__main__":
    unittest.main()
