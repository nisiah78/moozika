"""Tests de la fusion MusicXML page-par-page (app/merge.py).

Lancer depuis apps/audiveris-service :
    python3 -m unittest discover -s tests -t .
"""
import unittest
import xml.etree.ElementTree as ET

from app.merge import merge_musicxml


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


if __name__ == "__main__":
    unittest.main()
