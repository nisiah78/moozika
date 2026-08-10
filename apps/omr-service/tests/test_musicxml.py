import unittest
import xml.etree.ElementTree as ET

from app.solfa.parser import parse_solfa
from app.solfa.musicxml import to_musicxml


def _root(notation, **kw):
    xml = to_musicxml(parse_solfa(notation, **kw))
    # On retire l'en-tête + DOCTYPE pour parser uniquement l'arbre.
    body = xml[xml.index("<score-partwise"):]
    return ET.fromstring(body)


class TestWorkTitle(unittest.TestCase):
    """Fix 5 : le MusicXML porte titre (<work-title>) et compositeur (<creator>)."""

    def test_title_and_composer_emitted(self):
        m = parse_solfa("d : r : m : f", tonic="C")
        xml = to_musicxml(m, title="MIVAVAHA", composer="ANDRIAMIADAMAHATRATRA")
        root = ET.fromstring(xml[xml.index("<score-partwise"):])
        self.assertEqual(root.findtext("work/work-title"), "MIVAVAHA")
        creator = root.find("identification/creator")
        self.assertEqual(creator.text, "ANDRIAMIADAMAHATRATRA")
        self.assertEqual(creator.get("type"), "composer")

    def test_no_title_no_work_element(self):
        root = _root("d : r : m : f", tonic="C")
        self.assertIsNone(root.find("work"))
        self.assertIsNone(root.find("identification"))


class TestImplicitMeasure(unittest.TestCase):
    """Une mesure de levée (implicit) est émise avec implicit='yes'."""

    def test_implicit_attribute_emitted(self):
        from app.solfa.musicxml import to_musicxml
        m = parse_solfa("d : r : m : f", tonic="C")
        m.measures[0].implicit = True
        xml = to_musicxml(m)
        root = ET.fromstring(xml[xml.index("<score-partwise"):])
        self.assertEqual(root.find("part/measure").get("implicit"), "yes")

    def test_normal_measure_has_no_implicit(self):
        root = _root("d : r : m : f", tonic="C")
        self.assertIsNone(root.find("part/measure").get("implicit"))


class TestMusicXml(unittest.TestCase):
    def test_well_formed_and_structure(self):
        root = _root("d : d : s : s", tonic="C")
        self.assertEqual(root.tag, "score-partwise")
        self.assertEqual(len(root.findall("part/measure")), 1)
        steps = [s.text for s in root.iter("step")]
        self.assertEqual(steps, ["C", "C", "G", "G"])

    def test_attributes_present(self):
        root = _root("d : r : m", tonic="F")
        self.assertEqual(root.find(".//attributes/divisions").text, "4")
        self.assertEqual(root.find(".//attributes/key/fifths").text, "-1")
        self.assertEqual(root.find(".//attributes/time/beats").text, "3")
        self.assertEqual(root.find(".//attributes/clef/sign").text, "G")

    def test_alter_emitted(self):
        # fah en fa majeur = Bb -> <alter>-1</alter>.
        root = _root("f", tonic="F")
        self.assertEqual(root.find(".//pitch/alter").text, "-1")

    def test_tie_emitted(self):
        root = _root("d : d : d : d | - : d : d : d", tonic="C")
        tie_types = [t.get("type") for t in root.iter("tie")]
        self.assertIn("start", tie_types)
        self.assertIn("stop", tie_types)


if __name__ == "__main__":
    unittest.main()
