# Plan — Conversion inverse : MusicXML (portée/solfège) → sol-fa tonique

## Contexte

Le service `apps/omr-service` sait aujourd'hui faire **un seul sens** : sol-fa tonique (texte ou PDF)
→ `ScoreModel` → MusicXML. On ajoute le **sens inverse** demandé : lire une partition en notation
occidentale (via son MusicXML) et produire du **sol-fa tonique malgache**, en captant **tout le détail
musical** (hauteurs, rythme, octaves, mais aussi paroles, nuances/tempo, reprises/voltas,
articulations/ornements, harmonie), pas seulement les notes.

But : (1) enrichir le modèle de domaine pour porter ces détails ; (2) écrire un lecteur MusicXML
déterministe, stdlib-pur, qui inverse exactement la logique existante ; (3) sérialiser en sol-fa texte
round-trippable ; (4) étendre le contrat de format en conséquence. Le tout reste **zéro-dépendance**
dans `app/solfa` (contrainte CLAUDE.md) — lecture XML via `xml.etree.ElementTree` + `zipfile`, **pas de
music21** (on continue d'assumer l'écart vs `architecture.md` §7, comme le fait déjà `keys.py`).

## Décisions actées (validées avec l'utilisateur)

1. **Mineur = la-based (relatif)** : la tonique mineure se chante `l` ; on garde l'armure de la relative
   majeure. 7e haussé (sensible) = `si`, 6e haussé = `fi`. → à **implémenter** (le contrat le repoussait).
2. **Détails non-notes = modèle riche + texte étendu** : le `ScoreModel`/JSON porte tout ; le format
   texte sol-fa gagne des couches (en-tête, paroles, reprises, indications) pour un round-trip éditable.
3. **Les 4 couches de détail dès la v1** : paroles, nuances/tempo, reprises/voltas,
   articulations/ornements/harmonie (modélisées toutes ; rendu texte selon §Grammaire).
4. **Mètres simples ET composés dès la v1** : 2/4 3/4 4/4 **et** 6/8 9/8 12/8 → généraliser la grille
   rythmique (temps binaire vs ternaire).

Décisions techniques prises sans blocage : `doh_octave` **auto par voix** (calculé sur la tessiture
médiane pour minimiser les marques d'octave, puis **stocké** → round-trip préservé) ; rester dans
`app/solfa` (symétrise les 4 arêtes de conversion), inverses de bas niveau colocalisés dans `keys.py`
et `rhythm.py`.

## Théorie de lecture (le cœur) — hauteur absolue → syllabe mouvable-do

Inverse **exact** de `resolve_pitch` (validé algébriquement). Pour chaque note `(step, alter, octave)`,
tonique connue (→ `tonic_letter, fifths`), `doh_octave`, `mode` :

```
degree       = ((idx(step) - idx(tonic_letter)) % 7) + 1          # 1..7  (idx sur LETTERS=C..B)
delta        = alter - altered_letters(fifths).get(step, 0)        # inflexion chromatique
octave_shift = (octave*7 + idx(step) - doh_octave*7 - idx(tonic_letter) - (degree-1)) // 7
```
Le numérateur d'`octave_shift` est toujours multiple de 7 → division exacte, aucune perte.

**Table (degree, delta) → syllabe canonique** (dialecte malgache ; à mettre dans `keys.py`, miroir de
`DIATONIC`/`CHROMATIC`) :

| degré | 0 (diat.) | +1 (haussé) | −1 (baissé) |
| --- | --- | --- | --- |
| 1 | `d` | `di` | (enharm.) |
| 2 | `r` | `ri` | `ra` |
| 3 | `m` | (enharm.) | `ma` |
| 4 | `f` | `fi` | (enharm.) |
| 5 | `s` | `si` | `sa` |
| 6 | `l` | `li` | `la` |
| 7 | `t` | (enharm.) | `ta` |

**Repli enharmonique** (cases hors table, à implémenter comme re-spelling propre, pas en dur) :
`mi♯ (3,+1)→f` · `ti♯ (7,+1)→d` (octave_shift+1) · `do♭ (1,−1)→t` (octave_shift−1) · `fa♭ (4,−1)→m`.
Double altération (`|delta|≥2`) → **erreur explicite** « altération non représentable ».

**Marques d'octave** : `octave_shift>0` → autant de `'` ; `<0` → autant de `,`. `doh_octave` choisi par
voix (tessiture médiane) et stocké dans `ScoreModel.doh_octave`.

**Mineur (la-based)** : `FIFTHS_TO_TONIC` doit tenir compte de `mode` — un `fifths` donné + `mode=minor`
donne la tonique mineure, mais on **garde le doh de la relative majeure** pour l'épellation (donc la
tonique mineure tombe sur `l`, la sensible haussée sur `si`, etc.). Stocker `mode` sur le modèle.

## Grille rythmique (simple + composé) — inverse de `split_duration`/lexer

`rhythm.py` suppose aujourd'hui `DIVISIONS_PER_BEAT=4` (noire) et subdivisions **paires**. À généraliser :

- **Classification du mètre** depuis `<time>` : *composé* si numérateur multiple de 3 et > 3 avec
  dénominateur 8/16 (6/8, 9/8, 12/8) → temps = **noire pointée**, `beats = numérateur/3` ; sinon
  *simple* (2/4, 3/4, 4/4) → temps = noire, `beats = numérateur`. `:`/`!` séparent des **temps**
  (pulsations), pas l'unité du dénominateur.
- **Résolution par temps** : binaire → 4 divisions (facteurs de subdivision {2,4}) ; ternaire → 6
  divisions (division primaire **÷3** en croches, puis ÷2 → 16es). Généraliser `_split_even` (lexer) et
  `_NOTE_TABLE`/`split_duration` (rhythm) pour accepter le jeu de facteurs du temps courant.
- **Quantizer inverse** (nouveau, `rhythm.py`) : poser les onsets/frontières d'un temps sur sa grille ;
  cellule pleine, `.` (÷2 ou ÷3), `,` (sous-division) selon les offsets ; **`merge_tied`** fusionne
  d'abord les chaînes de liaisons `<tie>`/notes fragmentées en un événement (onset, durée totale) — sinon
  le round-trip diverge des fragments produits par le writer.
- **Tenues/silences** : émettre `-` **explicite** pour toute tenue (ne jamais s'appuyer sur le
  « vide-après-note » que le lexer interprète comme tenue) ; silences sous-temps via les formes `,`/`.`
  documentées. Tout motif inexprimable → **erreur** (jamais un texte faux).
- **Triolet / tuplet** : double garde-fou → présence de `<time-modification>`/`<tuplet>` **ou** onset
  non-aligné après rescale → `RhythmError` « non supporté ».

## Architecture & fichiers

Rester dans `app/solfa` (symétrie des 4 arêtes). Fichiers :

- `app/solfa/keys.py` — **+** `syllable_of_pitch(step, alter, octave, tonic, doh_octave, mode)` →
  `(core, octave_shift)`, `FIFTHS_TO_TONIC` (mode-aware), table inverse + repli enharmonique.
- `app/solfa/rhythm.py` — **+** classification mètre, `merge_tied`, quantizer temps→cellules, extension
  ternaire ; garder `split_duration` (utilisé par le writer).
- `app/solfa/model.py` — champs **optionnels additifs** (défauts vides ; `to_dict` n'émet que si présent
  → rétro-compatible). Voir §Modèle.
- `app/solfa/from_musicxml.py` — **NOUVEAU** : MusicXML → `List[ScoreModel]` (orchestration lecture).
- `app/solfa/to_solfa.py` — **NOUVEAU** : `ScoreModel` → texte sol-fa étendu (orchestration écriture).
- `app/solfa/musicxml.py` — writer **étendu** (increment final) pour émettre les nouvelles couches
  (round-trip modèle→MusicXML complet). Purement additif.
- `app/solfa/__init__.py`, `cli.py`, `app/main.py` — exposition (dernier increment).
- `packages/shared-contracts/solfa-format.md` — extension du contrat (§Grammaire).

## Lecteur MusicXML — pièges à traiter (from stress-test)

- **Curseur temporel, pas liste plate** : un `<measure>` déplace un curseur en divisions.
  `<note>` normale : onset=curseur, curseur+=duration. `<chord/>` : même onset, **n'avance pas**.
  `<grace/>` : n'avance pas. `<backup dur>` : curseur−=. `<forward dur>` : curseur+=.
  `<direction>/<harmony>/<barline>` : durée nulle, s'attachent à l'offset courant (+ `<offset>`, `<staff>`).
- **Split par `(staff, voice)`** → jusqu'à 4 flux monophoniques depuis un `<part>` (SATB condensé :
  staff1=voix1&2, staff2=voix3&4). Puis **combler les trous** de chaque voix par des silences (sinon
  mesures trop courtes). Valider `Σ durées == beats*divisions` par mesure → sinon erreur.
- **Politique `<chord>`** : pas d'erreur → garder la **note supérieure** (`on_chord="top"`), warning ;
  stocker éventuellement `NoteEl.chord_pitches` pour fidélité modèle.
- **Nom des voix** : depuis `<part-name>` ; SATB condensé ordonné par `(staff, hauteur médiane décr.)` ;
  fallback positionnel `_SATB` (Soprano/Alto/Tenor/Bass), Bass en clef `bass` (réutilise
  `app/pdf/document.py`).
- **Conteneur** : `.mxl` = ZIP (magic `PK`) → `zipfile` + `META-INF/container.xml` → rootfile.
  Racine `score-partwise` OK ; `score-timewise` → erreur. Lire `<part-list>`, matcher `id`.
- **Changements en cours** : `divisions` → **rescaler** (×4/current, ou ×6 en ternaire) ; `<time>` ou
  `<key>` réellement différents → **erreur** (re-déclaration identique tolérée).
- **`<transpose>`** : **ignorer pour l'épellation** (le movable-do sur la hauteur *écrite* est
  auto-cohérent) ; `octave-change` sans impact (octaves relatives) ; transpose chromatique réel → warning.
- **Anacrouse** (`implicit="yes"` / mesure 1 courte) : garder `Measure.implicit` dans le modèle, mais
  `to_solfa` **complète la 1ère mesure à `beats` temps** par des silences de tête (le lexer déduit le
  mètre du nb de temps de la 1ère mesure — sinon mètre faux). Round-trip modèle sans perte ; round-trip
  texte normalise la levée (asymétrie documentée). `<rest measure="yes">` → mesure toute-silence.

## Modèle enrichi (`model.py`, additif)

- `NoteEl` : `+ articulations: list`, `slur`, `fermata`, `ornaments: list`, `grace: bool`,
  `lyrics: list` (couplet, syllabic, texte), `chord_pitches: list` (option).
- `Direction(offset_divisions, placement, staff, kind, value)` — dynamics / wedge(cresc,dim) / words
  (rall., a tempo, Andante) / metronome / pedal. Appariement des spans (wedge/pedal/slur) par `number`.
- `Harmony(offset_divisions, root, kind, bass)`.
- `Measure` : `+ directions: list`, `harmonies: list`, `implicit: bool`, `repeat`, `ending`.
- `ScoreModel` : `+ mode: str = "major"`, `doh_octave: int = 4`.

## Grammaire texte étendue (`solfa-format.md`)

Le socle notes/rythme/octave round-trippe déjà. Ajouts documentés + émis par `to_solfa` :
- **Subdivision ternaire** (mètres composés) : sémantique du `.` en 3 dans un temps ternaire.
- **En-tête** intégré au texte (`doh = D`, `4/4`, `= 75`) pour un artefact autonome.
- **Paroles** : ligne alignée sous chaque voix (couplets numérotés).
- **Reprises / voltas** : `|:` `:|` et fins `1.` / `2.`.
- **Indications** (nuances f/p, cresc./dim., rall., a tempo) : ligne d'annotation au-dessus, ancrée au temps.
- Détails fins (articulations, ornements, harmonie) : **portés par le modèle/JSON** ; rendu texte
  optionnel/minimal (le texte sol-fa reste une projection, lossy par nature sur ces couches).

## Politique d'erreurs (jamais de partition fausse)

| Cas | Action |
| --- | --- |
| `divisions` change | **Rescale** |
| `<transpose>` chromatique ≠ 0 | **Warning** |
| Accord dans une voix | **Note du haut + warning** |
| `score-timewise` | Erreur |
| `<time>`/`<key>` réellement changés en cours | Erreur (position indiquée) |
| Mètre non géré (2/2, 5/4, 7/8, x/16 non composé…) | Erreur |
| Triolet/tuplet, onset non-aligné | `RhythmError` |
| Double altération | Erreur épellation |
| Motif rythmique inexprimable en texte | Erreur |
| Σ durées mesure ≠ capacité | Erreur (incohérence curseur) |

## Incréments (ordonnés, chacun testable) et tests

Conventions repo : `unittest`, classes `TestXxx`, méthodes `test_snake_case`, XML re-parsé via
`ET.fromstring(xml[xml.index("<score-partwise"):])`, run `cd apps/omr-service && python3 -m unittest tests.test_xxx -v`.

- **Inc 0 — `keys.syllable_of_pitch` + tables inverses + repli enharmonique + `FIFTHS_TO_TONIC`.**
  Test (`tests/test_keys.py`) : *property test* `syllable_of_pitch(resolve_pitch(...)) == (core, shift)`
  bouclé sur toutes toniques × degrés × octaves ; cas enharmoniques ; mineur la-based.
- **Inc 1 — rythme généralisé (`rhythm.py`)** : classification mètre, `merge_tied`, quantizer,
  extension ternaire. Test (`tests/test_rhythm.py`) : durées → texte → re-parse → durées identiques
  (fusionnées) ; 6/8 ; triolet → `RhythmError`.
- **Inc 2 — `model.py`** champs optionnels. Test : rétro-compat `to_dict` + sérialisation des nouveaux champs.
- **Inc 3 — `from_musicxml.py` cœur** (mxl/zip, partwise, part-list, moteur curseur
  backup/forward/chord/staff/voice, comblement silences, rescale divisions, erreurs time/key,
  transpose→warning, validation durée mesure). Test (`tests/test_from_musicxml.py`) : générer du
  MusicXML avec le writer existant → relire → comparer modèles ; fixtures XML synthétiques SATB condensé.
- **Inc 4 — directions/harmony/lyrics/articulations** (attache par offset+staff, spans par `number`).
  Test : XML synthétiques `<dynamics>`, `<wedge>`, `<lyric>`, `<harmony>`, articulations.
- **Inc 5 — `to_solfa.py`** (model → texte étendu : quantizer + syllabes + octaves + levée paddée +
  en-tête/paroles/reprises/indications). Test (`tests/test_to_solfa.py`) : **round-trip texte** en
  réutilisant le corpus de `tests/test_parser.py` (`parse_solfa(n) → to_solfa → == n normalisé`).
- **Inc 6 — round-trip end-to-end via fixture réelle.** Test (`tests/test_roundtrip.py`) :
  `pdf_to_score(tests/fixtures/jesoa-tsy-mba-mandao.pdf)["musicxml"]` → `from_musicxml` → `to_solfa`
  → comparer aux incipits attendus dans `test_pdf.py` (ex. soprano `.m : m.s : t : t.l`). Aucune
  nouvelle fixture binaire.
- **Inc 7 — writer étendu (`musicxml.py`) + exposition** : émettre les nouvelles couches (round-trip
  modèle→MusicXML complet) ; `__init__` exports ; CLI `python -m app.solfa.from_musicxml <fichier>` ;
  endpoint `POST /musicxml/parse` (mxl/xml) renvoyant `{header, voices:[{name, notation, model}]}`
  (miroir de `pdf_parse`). Exceptions : `class MusicXmlError(ValueError)` de haut niveau, à la
  `PdfSolfaError`.

## Vérification (bout en bout)

1. `make test` (ou `cd apps/omr-service && python3 -m unittest discover -s tests -v`) — tout vert,
   toujours stdlib-pur (aucune install requise pour `app/solfa`).
2. Round-trip texte : chaque chaîne de `tests/test_parser.py` doit se régénérer à l'identique (Inc 5).
3. Round-trip réel : le cantique `jesoa-tsy-mba-mandao.pdf` (PDF → MusicXML déjà fonctionnel) doit
   revenir en sol-fa cohérent (4 voix, 26 mesures, incipits attendus) (Inc 6).
4. CLI : `python -m app.solfa.from_musicxml /tmp/jesoa.musicxml` (après `make pdf-demo`) doit afficher
   le sol-fa reconstruit avec paroles/nuances/reprises.
5. Contrat : `packages/shared-contracts/solfa-format.md` mis à jour (ternaire, en-tête, couches
   d'expression) — l'interface texte reste la frontière stable OCR/saisie/parseur.
```
