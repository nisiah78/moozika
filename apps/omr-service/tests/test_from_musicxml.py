import io
import unittest
import zipfile

from app.solfa.from_musicxml import MusicXmlError, from_musicxml, read_musicxml
from app.solfa.musicxml import to_musicxml, to_musicxml_multi
from app.solfa.parser import parse_solfa
from app.solfa.rhythm import RhythmError


def _score(body: str, divisions=4, fifths=0, beats=4, beat_type=4, mode=None) -> str:
    """Enveloppe partwise minimale à une partie (P1) autour d'un corps de mesures."""
    key_mode = f"<mode>{mode}</mode>" if mode else ""
    return (
        '<score-partwise version="4.0">'
        '<part-list><score-part id="P1"><part-name>Voix</part-name></score-part></part-list>'
        '<part id="P1"><measure number="1"><attributes>'
        f"<divisions>{divisions}</divisions>"
        f"<key><fifths>{fifths}</fifths>{key_mode}</key>"
        f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef>"
        f"</attributes>{body}</measure></part></score-partwise>"
    )


def _note(step, octave, dur, ntype, alter=0, extra=""):
    alt = f"<alter>{alter}</alter>" if alter else ""
    return (
        f"<note><pitch><step>{step}</step>{alt}<octave>{octave}</octave></pitch>"
        f"<duration>{dur}</duration><type>{ntype}</type>{extra}</note>"
    )


class TestRoundTripViaWriter(unittest.TestCase):
    """MusicXML produit par le writer -> relu -> mêmes hauteurs et durées."""

    def _read_one(self, notation, **kw):
        return from_musicxml(to_musicxml(parse_solfa(notation, **kw)))[0]

    def test_pitches_and_types_preserved(self):
        v = self._read_one("d : d : s : s | l : l : s : -", tonic="C")
        self.assertEqual(v.beats, 4)
        self.assertEqual(len(v.measures), 2)
        self.assertEqual(
            [n.pitch.step for n in v.measures[0].notes], ["C", "C", "G", "G"]
        )
        self.assertEqual(v.measures[1].notes[-1].note_type, "half")

    def test_key_signature_recovered(self):
        v = self._read_one("d : f : t : d'", tonic="F")
        self.assertEqual(v.tonic, "F")
        self.assertEqual(v.fifths, -1)

    def test_absolute_pitch_is_stable(self):
        # Les hauteurs absolues doivent survivre à l'aller-retour (le registre du
        # doh peut différer, mais step/alter/octave sont conservés).
        original = parse_solfa("d : r : m : f", tonic="G")
        v = from_musicxml(to_musicxml(original))[0]
        orig = [(n.pitch.step, n.pitch.alter, n.pitch.octave)
                for n in original.measures[0].notes]
        got = [(n.pitch.step, n.pitch.alter, n.pitch.octave)
               for n in v.measures[0].notes]
        self.assertEqual(orig, got)


class TestSatb(unittest.TestCase):
    def test_four_parts_keep_names(self):
        parts = [
            parse_solfa("d : r : m : f", tonic="C", part_name="Soprano"),
            parse_solfa("s, : s, : s, : s,", tonic="C", part_name="Alto"),
            parse_solfa("m, : m, : m, : m,", tonic="C", part_name="Tenor"),
            parse_solfa("d, : d, : d, : d,", tonic="C", part_name="Bass", clef="bass"),
        ]
        models = from_musicxml(to_musicxml_multi(parts))
        self.assertEqual([m.part_name for m in models],
                         ["Soprano", "Alto", "Tenor", "Bass"])

    def test_two_voices_one_staff_via_backup(self):
        # voix 1 (C5..) et voix 2 (C4..) dans la même portée, séparées par backup.
        v1 = "".join(_note("C", 5, 4, "quarter", extra="<voice>1</voice>") for _ in range(4))
        v2 = "".join(_note("C", 4, 4, "quarter", extra="<voice>2</voice>") for _ in range(4))
        xml = _score(v1 + "<backup><duration>16</duration></backup>" + v2)
        models = from_musicxml(xml)
        self.assertEqual(len(models), 2)


def _single_voice_score(part_name: str, clef_extra: str = "") -> str:
    """Partie unique, clé de Sol (+ ``clef_extra`` ex. clef-octave-change),
    4 notes G4 quarter — pour tester la convention d'octave ténor."""
    body = "".join(_note("G", 4, 4, "quarter") for _ in range(4))
    return (
        '<score-partwise version="4.0">'
        f'<part-list><score-part id="P1"><part-name>{part_name}</part-name></score-part></part-list>'
        '<part id="P1"><measure number="1"><attributes><divisions>4</divisions>'
        "<key><fifths>0</fifths></key>"
        "<time><beats>4</beats><beat-type>4</beat-type></time>"
        f"<clef><sign>G</sign><line>2</line>{clef_extra}</clef>"
        f"</attributes>{body}</measure></part></score-partwise>"
    )


class TestTenorOctaveConvention(unittest.TestCase):
    """Convention chorale DÉTERMINISTE : un ténor noté en clé de Sol standard
    (sans <clef-octave-change> déjà présent) sonne 1 octave sous l'écrit. La
    correction n'est appliquée QUE quand le nom de voix la désigne EXPLICITEMENT
    (donnée lue, ex. OCR Audiveris) — jamais par estimation de tessiture."""

    def test_tenor_name_shifts_octave_down(self):
        res = read_musicxml(_single_voice_score("Tenor2"))
        octaves = [n.pitch.octave for n in res.models[0].measures[0].notes]
        self.assertEqual(octaves, [3, 3, 3, 3])  # G4 écrit -> G3 sonnant
        self.assertTrue(any("octave-tenor" in w for w in res.warnings))

    def test_accented_tenor_name_also_matches(self):
        res = read_musicxml(_single_voice_score("Ténor 1"))
        octaves = [n.pitch.octave for n in res.models[0].measures[0].notes]
        self.assertEqual(octaves, [3, 3, 3, 3])

    def test_explicit_octave_change_is_not_double_corrected(self):
        # Le petit "8" EST présent dans la gravure (Audiveris l'a lu) : l'octave
        # sonnante est déjà correcte dans le MusicXML — ne pas re-décaler.
        res = read_musicxml(
            _single_voice_score("Tenor2", clef_extra="<clef-octave-change>-1</clef-octave-change>")
        )
        octaves = [n.pitch.octave for n in res.models[0].measures[0].notes]
        self.assertEqual(octaves, [4, 4, 4, 4])
        self.assertFalse(any("octave-tenor" in w for w in res.warnings))

    def test_soprano_name_not_shifted(self):
        res = read_musicxml(_single_voice_score("Soprano"))
        octaves = [n.pitch.octave for n in res.models[0].measures[0].notes]
        self.assertEqual(octaves, [4, 4, 4, 4])
        self.assertFalse(any("octave-tenor" in w for w in res.warnings))

    def test_generic_name_not_shifted(self):
        # Sans identité lue (nom générique) : aucune correction — pas de
        # supposition statistique, cf. avertissement [part-name] à la place.
        res = read_musicxml(_single_voice_score("Voice"))
        octaves = [n.pitch.octave for n in res.models[0].measures[0].notes]
        self.assertEqual(octaves, [4, 4, 4, 4])
        self.assertFalse(any("octave-tenor" in w for w in res.warnings))


class TestChordPolicy(unittest.TestCase):
    def test_chord_keeps_top_note_and_warns(self):
        body = (
            '<note><pitch><step>C</step><octave>4</octave></pitch>'
            '<duration>16</duration><type>whole</type></note>'
            '<note><chord/><pitch><step>E</step><octave>4</octave></pitch>'
            '<duration>16</duration><type>whole</type></note>'
        )
        res = read_musicxml(_score(body))
        note = res.models[0].measures[0].notes[0]
        self.assertEqual(note.pitch.step, "E")            # note du haut
        self.assertEqual(len(note.chord_pitches), 1)      # C conservé en accord
        self.assertTrue(any("accord" in w for w in res.warnings))


class TestAttributeChanges(unittest.TestCase):
    def test_mid_score_key_change(self):
        # Changement d'armure en cours de pièce : SUPPORTÉ. La mesure 2 passe en
        # Ré (fifths=2) ; le doh bascule (mouvable-do), l'armure est posée sur la
        # mesure et les hauteurs absolues sont conservées.
        body_m1 = _note("C", 4, 16, "whole")
        xml = (
            '<score-partwise version="4.0">'
            '<part-list><score-part id="P1"><part-name>V</part-name></score-part></part-list>'
            '<part id="P1">'
            '<measure number="1"><attributes><divisions>4</divisions>'
            '<key><fifths>0</fifths></key>'
            '<time><beats>4</beats><beat-type>4</beat-type></time>'
            '<clef><sign>G</sign><line>2</line></clef></attributes>'
            f'{body_m1}</measure>'
            '<measure number="2"><attributes><key><fifths>2</fifths></key></attributes>'
            f'{body_m1}</measure>'
            '</part></score-partwise>'
        )
        v = from_musicxml(xml)[0]
        # En-tête = tonalité d'ouverture (Do).
        self.assertEqual((v.tonic, v.fifths), ("C", 0))
        # Mesure 1 : Do, pas de changement ; Do naturel = « d ».
        self.assertIsNone(v.measures[0].key_tonic)
        self.assertEqual(v.measures[0].notes[0].pitch.syllable, "d")
        # Mesure 2 : changement vers Ré (fifths=2) consigné sur la mesure.
        self.assertEqual(v.measures[1].key_tonic, "D")
        self.assertEqual(v.measures[1].key_fifths, 2)
        # Même hauteur absolue (Do4), mais épelée « ta, » (7 abaissé) en Ré.
        m2_note = v.measures[1].notes[0]
        self.assertEqual((m2_note.pitch.step, m2_note.pitch.octave), ("C", 4))
        self.assertEqual(m2_note.pitch.syllable, "ta,")

    def test_transpose_chromatic_warns(self):
        body = _note("C", 4, 16, "whole")
        xml = _score(body).replace(
            "</attributes>",
            "<transpose><chromatic>-2</chromatic></transpose></attributes>",
        )
        res = read_musicxml(xml)
        self.assertTrue(any("transpos" in w for w in res.warnings))

    def test_minor_mode_la_based(self):
        # La mineur (fifths=0, mode=minor) : doh=C, la tonique A -> 'l'.
        body = _note("A", 4, 16, "whole")
        v = from_musicxml(_score(body, fifths=0, mode="minor"))[0]
        self.assertEqual(v.mode, "minor")
        self.assertEqual(v.tonic, "C")
        self.assertTrue(v.measures[0].notes[0].pitch.syllable.startswith("l"))


class TestAnacrusis(unittest.TestCase):
    def test_pickup_measure_is_implicit(self):
        # Une seule noire dans une mesure 4/4 -> levée (implicit) complétée de silences.
        v = from_musicxml(_score(_note("G", 4, 4, "quarter")))[0]
        self.assertTrue(v.measures[0].implicit)


class TestContainerAndErrors(unittest.TestCase):
    def test_mxl_zip(self):
        xml = to_musicxml(parse_solfa("d : r : m : f", tonic="C"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "META-INF/container.xml",
                '<container><rootfiles><rootfile full-path="score.xml"/>'
                "</rootfiles></container>",
            )
            zf.writestr("score.xml", xml)
        models = from_musicxml(buf.getvalue())
        self.assertEqual(len(models[0].measures), 1)

    def test_timewise_raises(self):
        with self.assertRaises(MusicXmlError):
            from_musicxml('<score-timewise version="4.0"></score-timewise>')

    def test_triplet_raises(self):
        # divisions=6 (noire=6), une note de durée 2 -> 2*4/6 non entier.
        body = _note("C", 4, 2, "eighth")
        with self.assertRaises(RhythmError):
            from_musicxml(_score(body, divisions=6, beats=4, beat_type=4))

    def test_pitchless_note_becomes_rest(self):
        # Bruit OMR : une <note> sans <pitch> ni <rest> ne doit pas faire échouer
        # la conversion — elle devient un silence de sa durée (grille préservée).
        body = "<note><duration>16</duration><type>whole</type></note>"
        v = from_musicxml(_score(body))[0]
        self.assertEqual(len(v.measures), 1)
        notes = v.measures[0].notes
        self.assertTrue(notes and all(n.is_rest for n in notes))
        self.assertEqual(sum(n.duration for n in notes), 16)

    def test_meter_change_with_quantize(self):
        xml = (
            '<score-partwise version="4.0">'
            '<part-list><score-part id="P1"><part-name>Voix</part-name></score-part></part-list>'
            "<part id='P1'>"
            "<measure number='1'><attributes>"
            "<divisions>4</divisions><time><beats>6</beats><beat-type>8</beat-type></time>"
            "<clef><sign>G</sign><line>2</line></clef></attributes>"
            + _note("C", 4, 2, "eighth") * 6 +
            "</measure>"
            "<measure number='2'><attributes>"
            "<time><beats>4</beats><beat-type>4</beat-type></time></attributes>"
            + _note("D", 4, 4, "quarter") * 4 +
            "</measure></part></score-partwise>"
        )
        result = read_musicxml(xml, quantize_rhythm=True)
        self.assertEqual(len(result.models[0].measures), 2)
        self.assertTrue(any("[time]" in w for w in result.warnings))


class TestInc4Directions(unittest.TestCase):
    """<direction> : dynamics, wedge, words, metronome attachés à la mesure."""

    def _xml_with_direction(self, direction_body: str) -> str:
        return _score(
            f"<direction placement='above'>{direction_body}</direction>"
            + _note("C", 4, 16, "whole")
        )

    def test_dynamics_stored(self):
        xml = self._xml_with_direction(
            "<direction-type><dynamics><f/></dynamics></direction-type>"
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(len(m.directions), 1)
        d = m.directions[0]
        self.assertEqual(d.kind, "dynamics")
        self.assertEqual(d.value, "f")
        self.assertEqual(d.placement, "above")

    def test_wedge_crescendo_stored(self):
        xml = self._xml_with_direction(
            '<direction-type><wedge type="crescendo" number="1"/></direction-type>'
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(len(m.directions), 1)
        d = m.directions[0]
        self.assertEqual(d.kind, "wedge")
        self.assertEqual(d.value, "crescendo")
        self.assertEqual(d.number, 1)

    def test_words_stored(self):
        xml = self._xml_with_direction(
            "<direction-type><words>Andante</words></direction-type>"
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(m.directions[0].kind, "words")
        self.assertEqual(m.directions[0].value, "Andante")

    def test_metronome_stored(self):
        xml = self._xml_with_direction(
            "<direction-type><metronome>"
            "<beat-unit>quarter</beat-unit><per-minute>72</per-minute>"
            "</metronome></direction-type>"
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(m.directions[0].kind, "metronome")
        self.assertEqual(m.directions[0].value, "72")

    def test_direction_offset_stored(self):
        """<offset> déplace l'ancre de la direction dans la mesure."""
        xml = _score(
            _note("C", 4, 4, "quarter")  # onset 0, curseur passe à 4
            + "<direction><direction-type><dynamics><p/></dynamics></direction-type>"
            "<offset>4</offset></direction>"    # ancré à 4 + 4 = 8 (divisions internes)
            + _note("G", 4, 4, "quarter")       # onset 4
            + _note("E", 4, 4, "quarter")
            + _note("C", 4, 4, "quarter")
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(len(m.directions), 1)
        # offset_divisions = curseur (4) + rescale(4) = 4+4 = 8
        self.assertEqual(m.directions[0].offset_divisions, 8)

    def test_direction_staff_filter_per_voice(self):
        """Directions avec staff≠1 ignorées pour la voix sur staff=1."""
        # voix 1 staff 1, voix 2 staff 2 (backup)
        v1 = _note("C", 5, 4, "quarter", extra="<voice>1</voice><staff>1</staff>") * 4
        v2 = _note("C", 4, 4, "quarter", extra="<voice>2</voice><staff>2</staff>") * 4
        backup = "<backup><duration>16</duration></backup>"
        dir_staff1 = (
            "<direction><direction-type><dynamics><f/></dynamics></direction-type>"
            "<staff>1</staff></direction>"
        )
        dir_staff2 = (
            "<direction><direction-type><dynamics><p/></dynamics></direction-type>"
            "<staff>2</staff></direction>"
        )
        xml = _score(dir_staff1 + v1 + backup + dir_staff2 + v2)
        models = from_musicxml(xml)
        # retrouver les deux voix par tessiture
        s1 = next(m for m in models if m.doh_octave >= 5 or any(
            n.pitch and n.pitch.octave >= 5 for meas in m.measures for n in meas.notes
        ))
        s2 = next(m for m in models if m is not s1)
        m1 = s1.measures[0]
        m2 = s2.measures[0]
        # chaque voix ne reçoit que la direction qui lui appartient
        self.assertEqual([d.value for d in m1.directions], ["f"])
        self.assertEqual([d.value for d in m2.directions], ["p"])


class TestInc4Harmony(unittest.TestCase):
    """<harmony> : accord rattaché à la mesure."""

    def test_harmony_stored(self):
        xml = _score(
            "<harmony>"
            "<root><root-step>G</root-step></root>"
            "<kind>dominant</kind>"
            "</harmony>"
            + _note("G", 4, 16, "whole")
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(len(m.harmonies), 1)
        h = m.harmonies[0]
        self.assertEqual(h.root, "G")
        self.assertEqual(h.kind, "dominant")
        self.assertIsNone(h.bass)

    def test_harmony_with_bass(self):
        xml = _score(
            "<harmony>"
            "<root><root-step>C</root-step></root>"
            "<kind>major</kind>"
            "<bass><bass-step>E</bass-step></bass>"
            "</harmony>"
            + _note("C", 4, 16, "whole")
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(m.harmonies[0].bass, "E")

    def test_harmony_sharp_root(self):
        xml = _score(
            "<harmony>"
            "<root><root-step>F</root-step><root-alter>1</root-alter></root>"
            "<kind>major</kind>"
            "</harmony>"
            + _note("F", 4, 16, "whole", alter=1)
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(m.harmonies[0].root, "F#")

    def test_multiple_harmonies(self):
        xml = _score(
            "<harmony><root><root-step>C</root-step></root><kind>major</kind></harmony>"
            + _note("C", 4, 4, "quarter")
            + "<harmony><root><root-step>G</root-step></root><kind>major</kind></harmony>"
            + _note("G", 4, 4, "quarter")
            + _note("E", 4, 4, "quarter")
            + _note("C", 4, 4, "quarter")
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(len(m.harmonies), 2)
        self.assertEqual(m.harmonies[0].root, "C")
        self.assertEqual(m.harmonies[1].root, "G")


class TestInc4Lyrics(unittest.TestCase):
    """<lyric> sur les notes -> note.lyric."""

    def test_lyric_stored_on_note(self):
        xml = _score(
            '<note><pitch><step>C</step><octave>4</octave></pitch>'
            '<duration>4</duration><type>quarter</type>'
            '<lyric number="1"><syllabic>single</syllabic><text>Ha</text></lyric>'
            '</note>'
            + _note("D", 4, 4, "quarter")
            + _note("E", 4, 4, "quarter")
            + _note("F", 4, 4, "quarter")
        )
        notes = from_musicxml(xml)[0].measures[0].notes
        self.assertEqual(notes[0].lyric, "Ha")
        self.assertIsNone(notes[1].lyric)

    def test_multiple_lyrics(self):
        xml = _score(
            '<note><pitch><step>C</step><octave>4</octave></pitch>'
            '<duration>4</duration><type>quarter</type>'
            '<lyric><text>Je-</text></lyric>'
            '</note>'
            '<note><pitch><step>D</step><octave>4</octave></pitch>'
            '<duration>4</duration><type>quarter</type>'
            '<lyric><text>su</text></lyric>'
            '</note>'
            + _note("E", 4, 4, "quarter")
            + _note("F", 4, 4, "quarter")
        )
        notes = from_musicxml(xml)[0].measures[0].notes
        self.assertEqual(notes[0].lyric, "Je-")
        self.assertEqual(notes[1].lyric, "su")
        self.assertIsNone(notes[2].lyric)


class TestInc4Articulations(unittest.TestCase):
    """Articulations, ornements, slur, fermata sur les notes."""

    def _note_with_notations(self, notations_body: str) -> str:
        return (
            '<note><pitch><step>C</step><octave>4</octave></pitch>'
            '<duration>16</duration><type>whole</type>'
            f'<notations>{notations_body}</notations>'
            '</note>'
        )

    def test_staccato_stored(self):
        xml = _score(self._note_with_notations(
            "<articulations><staccato/></articulations>"
        ))
        note = from_musicxml(xml)[0].measures[0].notes[0]
        self.assertIn("staccato", note.articulations)

    def test_accent_stored(self):
        xml = _score(self._note_with_notations(
            "<articulations><accent/></articulations>"
        ))
        note = from_musicxml(xml)[0].measures[0].notes[0]
        self.assertIn("accent", note.articulations)

    def test_trill_stored(self):
        xml = _score(self._note_with_notations(
            "<ornaments><trill-mark/></ornaments>"
        ))
        note = from_musicxml(xml)[0].measures[0].notes[0]
        self.assertIn("trill-mark", note.ornaments)

    def test_slur_start_stored(self):
        xml = _score(self._note_with_notations(
            '<slur number="1" type="start"/>'
        ))
        note = from_musicxml(xml)[0].measures[0].notes[0]
        self.assertEqual(note.slur, "start")

    def test_fermata_stored(self):
        xml = _score(self._note_with_notations("<fermata/>"))
        note = from_musicxml(xml)[0].measures[0].notes[0]
        self.assertTrue(note.fermata)

    def test_no_notations_empty(self):
        xml = _score(_note("C", 4, 16, "whole"))
        note = from_musicxml(xml)[0].measures[0].notes[0]
        self.assertEqual(note.articulations, [])
        self.assertEqual(note.ornaments, [])
        self.assertIsNone(note.slur)
        self.assertFalse(note.fermata)


class TestInc4Barlines(unittest.TestCase):
    """<barline> : reprises et voltas."""

    def _two_measure_xml(self, bar1_extra="", bar2_extra="") -> str:
        note = _note("C", 4, 16, "whole")
        return (
            '<score-partwise version="4.0">'
            '<part-list><score-part id="P1"><part-name>V</part-name></score-part></part-list>'
            '<part id="P1">'
            '<measure number="1"><attributes>'
            '<divisions>4</divisions>'
            '<key><fifths>0</fifths></key>'
            '<time><beats>4</beats><beat-type>4</beat-type></time>'
            '<clef><sign>G</sign><line>2</line></clef>'
            f'</attributes>{note}{bar1_extra}</measure>'
            f'<measure number="2">{note}{bar2_extra}</measure>'
            '</part></score-partwise>'
        )

    def test_repeat_forward(self):
        xml = self._two_measure_xml(
            bar1_extra='<barline location="left"><bar-style>heavy-light</bar-style>'
                       '<repeat direction="forward"/></barline>'
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertEqual(m.repeat, "forward")

    def test_repeat_backward(self):
        xml = self._two_measure_xml(
            bar2_extra='<barline location="right"><bar-style>light-heavy</bar-style>'
                       '<repeat direction="backward"/></barline>'
        )
        m = from_musicxml(xml)[0].measures[1]
        self.assertEqual(m.repeat, "backward")

    def test_volta_start(self):
        xml = self._two_measure_xml(
            bar1_extra='<barline location="left">'
                       '<ending number="1" type="start"/></barline>'
        )
        m = from_musicxml(xml)[0].measures[0]
        self.assertIsNotNone(m.ending)
        self.assertEqual(m.ending["number"], "1")
        self.assertEqual(m.ending["type"], "start")

    def test_volta_stop(self):
        xml = self._two_measure_xml(
            bar2_extra='<barline location="right">'
                       '<ending number="1" type="stop"/></barline>'
        )
        m = from_musicxml(xml)[0].measures[1]
        self.assertIsNotNone(m.ending)
        self.assertEqual(m.ending["type"], "stop")

    def test_no_barline_none(self):
        xml = self._two_measure_xml()
        m = from_musicxml(xml)[0].measures[0]
        self.assertIsNone(m.repeat)
        self.assertIsNone(m.ending)


class TestChordSplit(unittest.TestCase):
    """on_chord='split' : un accord de portée (SATB condensé) devient deux voix
    haut/bas ; une note seule est mise à l'unisson dans les deux."""

    def _n(self, step, octave, dur=8, ntype="half", voice="1", staff="1", chord=False):
        ch = "<chord/>" if chord else ""
        return (f"<note>{ch}<pitch><step>{step}</step><octave>{octave}</octave></pitch>"
                f"<duration>{dur}</duration><type>{ntype}</type>"
                f"<voice>{voice}</voice><staff>{staff}</staff></note>")

    def _bass_staff_score(self, notes_body: str, name="Choeur") -> str:
        return (
            '<score-partwise version="4.0">'
            f'<part-list><score-part id="P1"><part-name>{name}</part-name>'
            '</score-part></part-list><part id="P1"><measure number="1"><attributes>'
            '<divisions>4</divisions><key><fifths>0</fifths></key>'
            '<time><beats>4</beats><beat-type>4</beat-type></time>'
            '<clef><sign>F</sign><line>4</line></clef></attributes>'
            f'{notes_body}</measure></part></score-partwise>'
        )

    def test_split_makes_two_voices(self):
        # voix unique staff1 : accord G3+C3 (mi-mesure) puis accord A3+D3.
        body = (
            self._n("G", 3, chord=False) + self._n("C", 3, chord=True)
            + self._n("A", 3, chord=False) + self._n("D", 3, chord=True)
        )
        res = read_musicxml(self._bass_staff_score(body), quantize_rhythm=True,
                            on_chord="split")
        self.assertEqual(len(res.models), 2)
        _semi = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
        def height(m):
            p = m.measures[0].notes[0].pitch
            return p.octave * 12 + _semi[p.step]
        by_med = sorted(res.models, key=height)
        bass, tenor = by_med[0], by_med[-1]
        self.assertEqual(
            [n.pitch.step for n in tenor.measures[0].notes], ["G", "A"]
        )
        self.assertEqual(
            [n.pitch.step for n in bass.measures[0].notes], ["C", "D"]
        )
        self.assertTrue(any("scindés en 2 voix" in w for w in res.warnings))

    def test_single_note_is_unison_in_both_voices(self):
        # accord G3+C3 puis note SEULE A3 -> A3 doit apparaître dans les 2 voix.
        body = (
            self._n("G", 3, chord=False) + self._n("C", 3, chord=True)
            + self._n("A", 3, chord=False)
        )
        res = read_musicxml(self._bass_staff_score(body), quantize_rhythm=True,
                            on_chord="split")
        seconds = [m.measures[0].notes[1].pitch.step for m in res.models]
        self.assertEqual(seconds, ["A", "A"])  # unisson

    def test_default_top_does_not_split(self):
        body = self._n("G", 3, chord=False) + self._n("C", 3, chord=True) + \
            self._n("A", 3) + self._n("D", 3, chord=True)
        res = read_musicxml(self._bass_staff_score(body), quantize_rhythm=True)
        self.assertEqual(len(res.models), 1)  # 'top' par défaut : une seule voix
        self.assertEqual(res.models[0].measures[0].notes[0].pitch.step, "G")

    def test_piano_part_not_split(self):
        body = self._n("G", 3, chord=False) + self._n("C", 3, chord=True) + \
            self._n("A", 3) + self._n("E", 3, chord=True)
        res = read_musicxml(self._bass_staff_score(body, name="Piano"),
                            quantize_rhythm=True, on_chord="split")
        self.assertEqual(len(res.models), 1)  # partie piano non scindée

    def test_no_split_when_substantial_sibling_voice(self):
        # Deux vraies voix déjà séparées sur une portée (S=v1 avec un divisi,
        # A=v2) : v1 ne doit PAS être scindée (sinon on crée un doublon qui
        # évince la vraie alto). -> exactement 2 voix.
        v1 = (self._n("C", 5, voice="1") + self._n("E", 5, voice="1", chord=True)
              + self._n("D", 5, voice="1"))                       # v1 avec accord
        v2 = self._n("E", 4, voice="2") + self._n("F", 4, voice="2")  # alto substantielle
        body = v1 + '<backup><duration>16</duration></backup>' + v2
        res = read_musicxml(self._bass_staff_score(body), quantize_rhythm=True,
                            on_chord="split")
        self.assertEqual(len(res.models), 2)
        self.assertFalse(any("scindés" in w for w in res.warnings))


class TestContentMeterInference(unittest.TestCase):
    """Priorité au <time> DÉCLARÉ (fiable même quand les durées OMR sont
    bruitées) ; l'inférence par contenu (plus petite capacité telle que ≤10 %
    des mesures débordent) ne sert que de REPLI quand aucun <time> supporté
    n'est déclaré."""

    def _measures(self, specs, fifths=0, first_time=None):
        """specs : liste de (n_notes_noire) par mesure. first_time : (b,bt) déclaré
        en mesure 1 (peut être FAUX exprès)."""
        q = _note("C", 4, 4, "quarter")
        out = []
        for i, n in enumerate(specs):
            attrs = ""
            if i == 0:
                t = ""
                if first_time:
                    t = f"<time><beats>{first_time[0]}</beats><beat-type>{first_time[1]}</beat-type></time>"
                attrs = ('<attributes><divisions>4</divisions>'
                         '<key><fifths>%d</fifths></key>%s'
                         '<clef><sign>G</sign><line>2</line></clef></attributes>' % (fifths, t))
            out.append(f'<measure number="{i+1}">{attrs}{q * n}</measure>')
        return (
            '<score-partwise version="4.0">'
            '<part-list><score-part id="P1"><part-name>V</part-name></score-part></part-list>'
            f'<part id="P1">{"".join(out)}</part></score-partwise>'
        )

    def test_declared_four_four_wins_over_content(self):
        # 10 mesures de 5 noires (=20 div) mais <time> déclaré 4/4 : le <time>
        # DÉCLARÉ l'emporte désormais (les durées OMR peuvent être bruitées) ;
        # le débordement de contenu est tronqué à la mesure, pas promu en 5/4.
        xml = self._measures([5] * 10, first_time=(4, 4))
        res = read_musicxml(xml, quantize_rhythm=True)
        self.assertEqual(res.predominant_time, (4, 4))

    def test_declared_six_eight_respected(self):
        # Un <time> /8 déclaré est respecté tel quel (pas réinterprété par le contenu).
        xml = self._measures([5] * 10, first_time=(6, 8))
        res = read_musicxml(xml, quantize_rhythm=True)
        self.assertEqual(res.predominant_time, (6, 8))

    def test_content_inference_is_fallback_without_declared_time(self):
        # Aucun <time> déclaré -> REPLI sur l'inférence par contenu : 5 noires
        # (=20 div) -> capacité 20, dénominateur /4 -> 5/4.
        xml = self._measures([5] * 10, first_time=None)
        res = read_musicxml(xml, quantize_rhythm=True)
        self.assertEqual(res.predominant_time, (5, 4))

    def test_single_overflow_outlier_does_not_inflate_meter(self):
        # (Repli inférence, aucun <time> déclaré) 12 mesures de 4 noires (16) +
        # 1 outlier de 5 noires (20) = 1/13 < 10 % -> reste 4/4.
        xml = self._measures([4] * 12 + [5], first_time=None)
        res = read_musicxml(xml, quantize_rhythm=True)
        self.assertEqual(res.predominant_time, (4, 4))

    def test_time_override_forces_meter(self):
        xml = self._measures([4] * 8, first_time=(4, 4))
        res = read_musicxml(xml, quantize_rhythm=True, time_override=(10, 8))
        self.assertEqual(res.predominant_time, (10, 8))
        self.assertEqual((res.models[0].beats, res.models[0].beat_type), (10, 8))

    def test_clean_four_four_stays_four_four(self):
        xml = self._measures([4] * 8, first_time=(4, 4))
        res = read_musicxml(xml, quantize_rhythm=True)
        self.assertEqual(res.predominant_time, (4, 4))


if __name__ == "__main__":
    unittest.main()
