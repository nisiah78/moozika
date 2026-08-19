# Théorie musicale — référence d'implémentation (Moozika)

Ce document distille la théorie musicale **utile à l'algorithme** de conversion
portée ⇄ sol-fa tonique malgache. Ce n'est **pas** un cours : c'est la base de
règles que le code (`apps/omr-service/app/solfa`, `app/pdf`, `app/staff`) doit
respecter pour ne jamais produire une partition fausse.

- **Source primaire :** *Understanding Basic Music Theory*, Catherine
  Schmidt-Jones (Connexions, 2015), **CC-BY-SA 4.0** — `docs/music_theory.pdf`.
  Le PDF est de la théorie **classique occidentale** (solfège). Ce document
  **filtre** ce qui s'applique au sol-fa tonique et ce qui n'en relève pas.
- **À lire avec :** `packages/shared-contracts/solfa-format.md` (le format texte,
  interface stable) et `docs/architecture.md` (décisions actées). En cas de
  contradiction sur le **format**, `solfa-format.md` fait foi ; sur
  l'**architecture**, `architecture.md` fait foi ; ce document fait foi sur la
  **théorie musicale sous-jacente**.
- **Rappel du pivot :** tout passe par **MusicXML**. Les règles ci-dessous
  décrivent des invariants musicaux, pas un format de sortie.

### Légende des marqueurs

| Marqueur | Sens |
| --- | --- |
| 🎼 | Concerne la **portée / solfège** (chaîne `app/staff`, Audiveris). |
| 🎵 | Concerne le **sol-fa tonique** (chaînes `app/solfa`, `app/pdf`). |
| ⚙️ | **Règle algorithmique / invariant** que le code doit appliquer. |
| 🚧 | **Hors périmètre v1** : lever une erreur explicite plutôt que deviner. |

---

## 1. Hauteur (pitch)

- Une octave = **12 demi-tons** (semi-tons) également espacés (tempérament égal).
- **7 noms naturels** : `A B C D E F G` (touches blanches). Le 8ᵉ recommence
  l'octave. Les 5 autres hauteurs (touches noires) se nomment avec un **dièse**
  (`#`, +1 demi-ton) ou un **bémol** (`b`, −1 demi-ton) sur une naturelle.
- **Double dièse / double bémol** : ±2 demi-tons. Rares mais légaux.
- **Enharmonie :** deux écritures différentes pour la même hauteur (G♯ = A♭,
  E♯ = F, C♭ = B). Elles **sonnent pareil** mais **n'ont pas la même fonction**
  dans la tonalité.
- **Octaves nommées** : notation scientifique. **C4 = do central** (`doh_octave`
  par défaut = 4). L'octave s'incrémente au passage **B → C**.

Classe de hauteur (pitch class, 0–11, référence C=0) :

| Note | C | C♯/D♭ | D | D♯/E♭ | E | F | F♯/G♭ | G | G♯/A♭ | A | A♯/B♭ | B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pc | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |

> ⚙️ **Ne jamais normaliser l'orthographe (spelling).** G♯ et A♭ sont la même
> touche mais deux notes différentes. Le modèle `Pitch(step, alter, octave)`
> (`app/solfa/model.py`) conserve `step` (lettre) **et** `alter` séparément
> précisément pour cela. La hauteur absolue seule (pitch class) perd
> l'information de fonction — utile pour l'audio/MIDI, **jamais** comme identité
> canonique d'une note.

---

## 2. Portée et clés 🎼

- La portée = 5 lignes ; barres de mesure ; double barre = fin de section/pièce.
- La **clé** fixe la lettre de chaque ligne/espace :
  - **clé de sol (treble)** : 2ᵉ ligne (bas) = **G4** ;
  - **clé de fa (bass)** : 4ᵉ ligne (2ᵉ du haut) = **F3** ;
  - **clé d'ut (C clef)** : mobile, centre sur **do central** (rare) ;
  - **treble-8** : petit « 8 » sous la clé de sol → sonne une octave plus bas.
- Do central (C4) est **juste au-dessus** de la clé de fa et **juste en dessous**
  de la clé de sol : les deux clés ensemble couvrent l'ambitus voix/instruments.
- **Lignes supplémentaires** (*ledger lines*) : courtes lignes ajoutées au-dessus
  ou en dessous de la portée pour une note hors ambitus. Elles ne changent que la
  **hauteur** (octave), pas la durée — un piège OMR : une note très aiguë/grave
  s'y lit, ne pas la rejeter comme bruit.

> 🎵 Le sol-fa est *mouvable-do* : il n'a **pas** de clé de hauteur. La `clef`
> (`treble`/`bass`, cf. `solfa-format.md` §1) reste une **métadonnée** utile au
> rendu MusicXML et à l'octave par défaut de chaque voix, pas à la lecture des
> syllabes.

### 2.1 Anatomie de la note, hampes et ligatures (beams) 🎼⚙️

Une note écrite porte : une **tête** (*head*) qui fixe la **hauteur** (ligne/espace),
éventuellement une **hampe** (*stem*), un ou plusieurs **crochets** (*flags*), des
**ligatures** (*beams*) la reliant à d'autres notes, et des **points**. Tout cela
n'encode que la **durée** (§6), sauf la tête qui seule porte la hauteur.

- **Sens de la hampe (haut/bas)** = **purement cosmétique** : il n'affecte ni la
  hauteur ni la durée. En revanche, sur une portée à plusieurs voix, *hampes en
  haut* = voix « du dessus », *hampes en bas* = voix « du dessous » : c'est le
  signal typographique qui **sépare deux voix partageant une portée** (cf. §8.4,
  mémoire *OMR staff meter & merge*). ⚙️ Ne jamais fusionner deux hampes de sens
  opposés en un accord.
- **Note sans tête** = **pas de hauteur définie** (percussion, ou tête remplacée
  par un symbole d'accord). ⚙️ En sol-fa, l'ignorer plutôt que d'inventer une
  syllabe.
- ⚙️ **Ligatures et musique vocale (crucial pour le sol-fa).** Un *beam* ne change
  jamais la durée (chaque note garde le nombre de barres qu'elle aurait de
  crochets). Mais en **musique vocale**, une ligature **regroupe souvent les notes
  chantées sur une même syllabe de texte** ; de même, un **slur (liaison de
  phrasé)** couvrant plusieurs hauteurs = **mélisme** (plusieurs notes sur une
  syllabe). C'est l'indice typographique du **rattachement note ↔ syllabe** : il
  guide l'attribution de `NoteEl.lyric` / `Measure.beat_lyrics` (`model.py`) et ne
  doit **pas** être perdu, sous peine de désaligner paroles et notes.

---

## 3. Armure (key signature) et cercle des quintes

L'armure = liste des dièses/bémols valables sur toute la pièce (sauf altérations
accidentelles ponctuelles).

- **Ordre des dièses** : `F C G D A E B` (quintes ascendantes).
- **Ordre des bémols** : l'inverse, `B E A D G C F`.
- **Nommer une clé majeure d'après l'armure :**
  - dièses : la clé est **un demi-ton au-dessus du dernier dièse** ;
  - bémols : la clé est l'**avant-dernier bémol** (exceptions à mémoriser :
    C majeur = 0 altération, F majeur = 1 bémol).

Le nombre signé d'altérations est le champ **`fifths`** de MusicXML/du modèle
JSON (cf. `solfa-format.md` §6). Table (implémentée dans `keys.py: TONIC_MAP`) :

| `fifths` | −7 | −6 | −5 | −4 | −3 | −2 | −1 | 0 | +1 | +2 | +3 | +4 | +5 | +6 | +7 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Majeur** | C♭ | G♭ | D♭ | A♭ | E♭ | B♭ | F | C | G | D | A | E | B | F♯ | C♯ |
| **Mineur relatif** | a♭ | e♭ | b♭ | f | c | g | d | a | e | b | f♯ | c♯ | g♯ | d♯ | a♯ |

> ⚙️ **`tonic` → `fifths`** est déterministe (`keys.py: fifths_of`). C'est de là
> que sort l'armure MusicXML. La tonique est **déclarée hors notation** (jamais
> devinée depuis les syllabes) ; cf. §9 et CLAUDE.md.

Le **cercle des quintes** ordonne les clés par proximité (une quinte = ±1
altération). Il sert à mesurer la **parenté tonale** (modulation, §8), pas la
proximité chromatique.

---

## 4. Gammes et système mouvable-do 🎵 (cœur de l'algorithme)

### 4.1 Intervalles élémentaires

- **Demi-ton** (semi-ton) = plus petit écart (note voisine).
- **Ton** = 2 demi-tons.

### 4.2 Gamme majeure — le patron du mouvable-do

Depuis la tonique, la gamme majeure suit **T-T-½-T-T-T-½** (`do ré mi fa sol la
si do`). Les degrés tombent donc à ces distances en demi-tons de la tonique :

| Degré | 1 | 2 | 3 | 4 | 5 | 6 | 7 | (8) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Syllabe | `d` | `r` | `m` | `f` | `s` | `l` | `t` | `d'` |
| Demi-tons/tonique | 0 | 2 | 4 | 5 | 7 | 9 | 11 | 12 |
| Solfège fixe (do majeur) | do | ré | mi | fa | sol | la | si | do |

> ⚙️ **Invariance du mouvable-do :** la même mélodie en Do et en Sol donne
> **les mêmes syllabes**. La syllabe encode un **degré** (fonction), pas une
> hauteur. C'est ce qui fait du sol-fa une notation *transposée par nature*
> (cf. §9).

**Résolution syllabe → hauteur absolue** (implémentée dans
`keys.py: resolve_pitch`). Deux façons équivalentes de voir le calcul :

1. *Par pitch class* (audio/MIDI) :
   `pc = (pc(tonique) + offset_degré + altération_chromatique) mod 12`, avec
   `offset_degré ∈ {0,2,4,5,7,9,11}`.
2. *Par lettre + armure* (ce que fait le code, pour **préserver l'orthographe**) :
   `lettre = lettres[(index_tonique + degré − 1) mod 7]`, puis
   `alter = altération_d'armure(lettre) + delta_chromatique`.
   L'octave se déduit de la position diatonique absolue
   (`octave·7 + index_lettre`) et des marques d'octave (`'` / `,`).

Les deux donnent la même hauteur en majeur ; la 2ᵉ garde le bon `step`/`alter`
(ex. en Fa majeur, le degré 4 est **B♭**, pas A♯).

### 4.3 Chromatismes (dialecte malgache)

Les syllabes altérées haussent (`-i` : `di ri fi si li`) ou abaissent
(`-a` : `ra ma sa la ta`) un degré d'un demi-ton. Table canonique et alias
Curwen : voir `solfa-format.md` §2 et `keys.py: CHROMATIC`. Une altération
chromatique est un `delta` ±1 ajouté au degré diatonique — **pas** un nouveau
degré.

### 4.4 Gammes mineures 🚧

Le mineur suit un autre patron d'intervalles — on **ne peut pas** transposer du
majeur au mineur par simple décalage.

| Type | Patron (montant) | Note |
| --- | --- | --- |
| **Naturelle** | T-½-T-T-½-T-T | notes de l'armure seules |
| **Harmonique** | naturelle + **7ᵉ haussée** ½ ton | tension vers la tonique (harmonie) |
| **Mélodique** | 6ᵉ **et** 7ᵉ haussées ½ ton en montant, naturelles en descendant | usage mélodique |

- **Relative mineure** = 3 demi-tons **sous** la majeure de même armure
  (ex. la mineur ↔ do majeur). **Parallèle** = même tonique, armure différente
  (do mineur ≠ do majeur).
- **Convention Moozika / fihirana : mineur *la-based*** (Curwen). Le `doh` reste
  celui de la relative majeure (même `fifths`) ; la tonique mineure tombe sur le
  degré 6 (`l`). C'est déjà pris en compte dans le sens inverse
  (`keys.py: FIFTHS_TO_TONIC`, commentaire), **mais le mode mineur n'est pas
  encore géré de bout en bout** → cohérent avec `solfa-format.md` §5.

> ⚙️ Tant que le mineur n'est pas livré : **erreur de parsing explicite**, jamais
> une partition majeure fausse plaquée sur une mélodie mineure.

### 4.5 Autres gammes 🚧

Chromatique (12 demi-tons), tons entiers (6 tons, sans centre tonal),
**pentatonique** (5 notes), blues, octatonique, modes… Hors périmètre v1.
Documentées ici pour que l'OCR **ne les invente pas** : une suite de notes
inattendue relève de l'erreur/du bruit, pas d'une gamme exotique supposée.

---

## 5. Intervalles

Un intervalle se nomme en deux temps :

1. **Le nombre** : compter lignes + espaces entre les deux notes, **inclus**
   (do→mi = tierce, do→sol = quinte). Indépendant des altérations.
2. **La qualité** : selon le nombre exact de demi-tons.

| Intervalle | Demi-tons | Qualité |
| --- | --- | --- |
| Unisson (prime) | 0 | juste |
| Seconde m / M | 1 / 2 | mineure / majeure |
| Tierce m / M | 3 / 4 | mineure / majeure |
| Quarte juste | 5 | juste |
| Triton (4te aug. = 5te dim.) | 6 | augmentée / diminuée |
| Quinte juste | 7 | juste |
| Sixte m / M | 8 / 9 | mineure / majeure |
| Septième m / M | 10 / 11 | mineure / majeure |
| Octave juste | 12 | juste |

- **Primes, quartes, quintes, octaves** = *justes* (jamais majeures/mineures) ;
  peuvent être **augmentées** (+½) ou **diminuées** (−½).
- **Secondes, tierces, sixtes, septièmes** = *majeures* ou *mineures*.
- **Inversion** : le nom s'obtient par `9 − n` ; juste↔juste, majeur↔mineur,
  augmenté↔diminué.
- **Simple vs composé** : un intervalle **≤ octave** est *simple* ; **> octave**
  il est *composé* (9ᵉ, 10ᵉ, 11ᵉ… = octave + 2ᵈ, + 3ᵉ, + 4ᵗᵉ). Pour la validation
  Moozika, un intervalle composé dans une **voix monophonique** est rare et
  suspect (souvent un `,`/`'` d'octave parasite, §11.2) ; dans un **accord SATB
  vertical** il est normal (les voix sont espacées).

> ⚙️ Usage Moozika : les intervalles servent à **valider** (une octave `,`
> parasite crée un saut aberrant, cf. §11), à construire les accords (§8), et à
> raisonner sur la transposition (§9). Classer un intervalle **tel qu'il est
> écrit** (l'orthographe porte le sens).

---

## 6. Durée et rythme

### 6.1 Valeurs de note (fractions de la ronde)

| Note | Ronde | Blanche | Noire | Croche | Double | Triple |
| --- | --- | --- | --- | --- | --- | --- |
| Fraction | 1 | 1/2 | 1/4 | 1/8 | 1/16 | 1/32 |

Chaque valeur vaut la moitié de la précédente. Les **silences** ont exactement
les mêmes valeurs. Les crochets (flags) peuvent être remplacés par des
**barres (beams)** groupant les notes — sans effet sur la durée ; en musique
vocale, un beam relie souvent les notes chantées sur une même syllabe de texte.

### 6.2 Point et liaison

- **Point** : allonge la note de **la moitié** de sa valeur (noire pointée =
  noire + croche = 3/8). Un 2ᵉ point ajoute la moitié du 1ᵉʳ, etc.
- **Liaison (tie)** : additionne deux notes de **même hauteur** → une seule note
  tenue. **Seule** façon d'écrire un son à cheval sur une barre de mesure.
- ⚠️ **Tie ≠ slur** : la liaison de phrasé (slur) relie des hauteurs
  *différentes* — c'est une articulation, pas une durée.

### 6.3 Divisions empruntées (tuplets) 🚧 partiel

Diviser un temps autrement qu'en 2/4/8… :
- **Triolet** (3:2) = 3 notes dans le temps de 2. **Le seul couramment géré**
  (cf. `solfa-format.md` §4 : 3 syllabes collées ; MusicXML `time-modification`
  3:2, `divisions=12`).
- Duolet (2:3, en mètre composé), quintolet, etc. → **hors périmètre**.

> ⚙️ Correspondance avec le format texte (séparateurs de `solfa-format.md` §3) :
> `.` = demi-temps, `,` = quart de temps, `-` = prolongation (≈ tie/point),
> notes juxtaposées = doubles-croches, 3 syllabes collées = triolet. La théorie
> ci-dessus est la **sémantique** ; le contrat texte est la **syntaxe**.

- **Duolet** (2:3) : en **mètre composé**, deux notes empruntées au mètre simple
  (l'inverse du triolet). 🚧 hors périmètre v1.
- **Swing** (jazz/blues) : deux croches écrites « droites » se jouent en réalité
  ≈ triolet noire-croche. C'est une **convention d'interprétation**, pas une
  écriture rythmique différente → si le style l'exige, se marque par une mention
  *swing* (direction `words`), l'écriture reste en croches. 🚧 hors périmètre v1.

### 6.4 Syncope — ⚙️ ne pas confondre avec une erreur

Une **syncope** met l'accent sur un temps faible ou **hors du temps** (contretemps,
« sur le "et" »). C'est un choix rythmique **légal et fréquent** (fihirana, gospel,
ragtime), pas un défaut.

> ⚙️ **Conséquence pour le parseur.** Une note longue/importante qui commence à la
> moitié d'un temps, ou sur un temps faible, ne viole **rien** : l'invariant de
> composition (§7.3 — chaque temps = 1 temps) **tient toujours**, seule la place de
> l'accent change. Ne **jamais** « recaler » une note syncopée sur le temps fort
> pour la « corriger » : ce serait falsifier le rythme importé.

---

## 7. Signature rythmique, mètre et invariant de composition

### 7.1 Lecture de la signature

Deux nombres : **haut** = nombre de battements par mesure ; **bas** = valeur qui
vaut un battement (4 = noire, 8 = croche…). `C` = 4/4 (*common time*),
`¢` = 2/2 (*cut time*).

### 7.2 Mètre simple vs composé

- **Simple** : le battement se divise en **deux** (2/4, 3/4, 4/4…).
- **Composé** : le battement se divise en **trois** ; il s'écrit comme une valeur
  **pointée**. Ex. **6/8 = 2 battements** de noire pointée (pas 6), 9/8 = 3,
  12/8 = 4. C'est la façon standard d'écrire des temps ternaires.
- Classification : *duple / triple / quadruple* selon le nombre de battements.

> 🎵 En sol-fa, le `!` marque la mi-mesure et `:` sépare les temps
> (`solfa-format.md` §3).
>
> ⚠️ **Déviation dialectale assumée (fihirana malgache).** En théorie, 6/8 = 2
> battements de noire pointée. Mais les recueils malgaches **écrivent** le 6/8 en
> **6 pulsations de croche** (`| 1 : 2 : 3 ! 4 : 5 : 6 |`), et
> `rhythm.py: classify_meter` respecte cette convention (6/8, 5/8, 10/8 → N
> pulsations de croche ; seuls 9/8 et 12/8 sont traités en composé pointé). Le
> `<time>` MusicXML reste « 6/8 » dans les deux cas — seul le **groupement interne
> des temps** diffère. Décision produite : *ne pas* casser ce dialecte (cf. tests
> `test_rhythm`/`test_to_solfa`). Le seul bug corrigé est le **câblage** : la
> chaîne PDF transmet désormais le mètre déclaré à `parse_solfa`
> (`document.py`, garde `header.time_declared`) pour que le `<time>` affiché
> corresponde au rythme parsé (avant, un 6/8 tombait à 6/4).

### 7.3 ⚙️ Invariant de composition (règle d'or, non négociable)

> **La somme des durées (notes + silences) de chaque mesure = exactement ce
> qu'indique la signature. Et chaque temps fait exactement 1 temps — ni plus, ni
> moins.**

- **Déficit** (le temps/la mesure ne se remplit pas) ⇒ une note ou un silence
  **n'a pas été reconnu**. On **remplace la position manquante par un silence**
  (le « vide », corrigeable ensuite dans l'interface). On ne **fausse jamais** la
  durée ou l'octave d'une note voisine pour combler.
  *Exemple (cf. CLAUDE.md) :* `d,,d` (2 quarts au lieu d'un temps) → il manque du
  contenu → `d,.,d` (do quart, silence quart, do quart… le vide signale au
  lecteur qu'une note reste à retrouver).
- **Excédent** ⇒ sur-segmentation ou séparateur parasite → à diagnostiquer, pas à
  tronquer silencieusement.

Cet invariant est le **filet de sécurité principal** contre les partitions
fausses issues de l'OCR. Il est déjà énoncé dans CLAUDE.md et `solfa-format.md`
§3 ; il est ici **rattaché à sa cause théorique** (signature + valeurs de note).

### 7.4 Anacrouse (levée / pickup) — ⚙️ à ne pas confondre avec un déficit

Une pièce peut commencer **avant** le premier temps fort : la **1ʳᵉ mesure est
volontairement incomplète** (mesure de levée). Règle classique : la **dernière
mesure est raccourcie** d'autant, de sorte que *1ʳᵉ + dernière = 1 mesure
complète*. Le modèle marque cette mesure par `Measure.implicit` (`model.py`).

> 🎵 **Notes de levée (pickup notes) à l'intérieur d'une pièce.** N'importe quelle
> **phrase** (pas seulement la première) peut débuter par des notes de levée avant
> son temps fort. Une double barre peut alors apparaître *au milieu* d'une mesure
> pour rattacher la levée à la bonne section — mais la **barre de mesure reste à sa
> place** (fin de mesure pleine). Ne pas lire cette double barre interne comme une
> fin de mesure.

> ⚙️ **Conséquence pour le parseur.** Une 1ʳᵉ mesure incomplète est **légale**,
> pas une erreur. Deux tests la distinguent d'une note manquante :
> 1. sa durée + celle de la **dernière** mesure = une mesure pleine ;
> 2. **toutes les mesures intermédiaires** sont pleines.
>
> ⚠️ **Point ouvert à trancher.** `solfa-format.md` §3 pose : « le nombre de
> temps de la **première mesure** fixe la signature ». Avec une anacrouse cette
> heuristique **se trompe** (elle lirait une levée d'1 temps comme du 1/4).
> Recommandation : dériver la signature du **`<time>` déclaré** si présent
> (cf. mémoire *OMR staff meter & merge*), sinon de la **mesure pleine la plus
> fréquente**, et ne recourir à « la 1ʳᵉ mesure » qu'en dernier ressort. **Ne
> pas** modifier ce comportement sans validation — signalé ici comme écart
> théorie ↔ contrat.

### 7.5 Changement de mètre

Le **modèle** porte un changement **par mesure** : `Measure.time_signature`
(nouveau `(beats, beat_type)`) et, de même, `Measure.key_fifths`/`key_tonic` pour
un changement d'armure (§8.5, modulation). Un changement **déjà présent** dans la
source — lu du MusicXML par la chaîne portée (`from_musicxml.py`) ou marqué `(N/M)`
en sol-fa texte (`solfa-format.md`) — est donc **conservé et réémis** (`<time>`),
pas perdu.

> 🚧 Ce qui reste hors périmètre v1 : **inférer** un changement de mètre **non
> marqué** à partir du seul flux de notes sol-fa. Dans ce cas, la signature est
> supposée **constante** ; un flux qui n'est cohérent avec aucun mètre constant →
> erreur explicite plutôt qu'une partition fausse.

---

## 8. Harmonie (contexte SATB)

Base théorique utile pour la **polyphonie à 4 voix** (fihirana) et pour
**valider** l'OCR — pas pour « reconstruire » une harmonie.

### 8.1 Accords

- **Triade** = 3 notes empilées par tierces : *fondamentale, tierce, quinte*.
  - **Majeure** = tierce M (4 ½) + tierce m (3 ½) ; **mineure** = m + M ;
    **augmentée** = M + M ; **diminuée** = m + m.
- **Inversions** : la note la plus grave détermine l'état (fondamental / 1ᵉʳ /
  2ᵈ renversement). Changer une **hauteur ou son orthographe** change l'accord ;
  le renverser ou doubler à l'octave ne le change pas.
- **Septième** : triade + une 7ᵉ. Cinq types courants (utile pour classer un
  `Harmony.kind`, §8.4) :

  | Accord | Construction | `kind` MusicXML |
  | --- | --- | --- |
  | 7ᵉ **de dominante** (V7) | triade M + 7ᵉ m | `dominant` |
  | 7ᵉ **majeure** | triade M + 7ᵉ M | `major-seventh` |
  | 7ᵉ **mineure** | triade m + 7ᵉ m | `minor-seventh` |
  | 7ᵉ **diminuée** | triade dim + 7ᵉ dim | `diminished-seventh` |
  | **demi-diminuée** | triade dim + 7ᵉ m | `half-diminished` |

  La **7ᵉ de dominante** (triade M + 7ᵉ m) est la plus courante (V7 → I, cadence
  parfaite).

### 8.2 Degrés dans une tonalité majeure

Triade sur chaque degré de la gamme → patron **constant** en majeur :

| Degré | I | ii | iii | IV | V | vi | vii° |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Qualité | maj | min | min | maj | maj | min | dim |
| Nom | tonique | sus-tonique | médiante | sous-dominante | dominante | sus-dominante | sensible |

I, IV, V (majeurs) portent l'essentiel ; **V7 → I** donne le plus fort sentiment
de conclusion. En mineur le patron diffère (§4.4).

### 8.3 Consonance / dissonance et cadences

- Consonances : tierces, quartes, quintes, sixtes, octaves. Dissonances :
  secondes, septièmes, **triton**. Une dissonance **appelle une résolution**.
- **Cadences** (fin de phrase/section) :
  - **Authentique / parfaite** : V→I (ou V7→I) — conclusion forte.
  - **Plagale** : IV→I — c'est l'**« Amen »** de beaucoup de cantiques/**fihirana**.
  - **Demi-cadence** : fin sur V (suspension).
  - **Rompue / trompeuse** : prépare I mais aboutit ailleurs.

> ⚙️ Rôle dans Moozika (pistes de **validation**, pas fonctionnalité v1) :
> - chaque voix SATB reste **monophonique** et indépendante
>   (`solfa-format.md` §7) — le parseur **n'harmonise pas** ;
> - une note isolée incohérente avec l'accord vertical des 4 voix est
>   **suspecte** (aide au diagnostic OCR) ;
> - la **note/l'accord final** (souvent la tonique) aide à **confirmer** la
>   tonique déclarée — utile mais la tonique reste une **métadonnée d'entrée**,
>   jamais tranchée par l'algo seul.

### 8.4 Chiffrage d'accords (symboles) — `Harmony`

Certaines partitions (fihirana avec accords de guitare, lead sheets) portent des
**symboles d'accord** au-dessus de la portée : `C`, `Am`, `G7`, `Dsus4`, `F/A`…
Ils indiquent l'accompagnement **indépendamment** des notes écrites.

- Structure : **fondamentale** + **type** (± notes ajoutées/altérées) + éventuelle
  **basse** après une barre oblique (`C/E` = accord de Do, **mi** à la basse ;
  `slash chord`). Modélisé par `Harmony(root, kind, bass)` (`model.py`), émis en
  `<harmony>` par `musicxml.py`, lu par `from_musicxml.py`.
- ⚠️ Un symbole d'accord nomme toujours ses notes dans la **gamme de sa propre
  fondamentale**, **pas** dans l'armure de la pièce (une altération « ♭9 » part de
  la gamme de l'accord). Ne pas y appliquer l'armure globale.
- ⚙️ Rôle Moozika : **métadonnée à préserver** (pass-through). Le parseur
  **n'harmonise pas** et ne **déduit pas** d'accords depuis les voix ; il conserve
  seulement ceux qui sont écrits.

### 8.5 Texture et modulation

- **Texture** (relation mélodie/harmonie) : *monophonique* (une seule ligne),
  *homophonique* (une mélodie + accompagnement au **même rythme** — cas des
  cantiques/**fihirana** SATB « note contre note » et du barbershop),
  *polyphonique/contrapuntique* (plusieurs mélodies **indépendantes** : canon,
  fugue), *hétérophonique* (rare en Occident). ⚙️ Conséquence : en SATB
  homophonique les 4 voix partagent le rythme mais restent **4 lignes
  monophoniques distinctes** ; ne pas les fusionner en accords ni mélanger des
  rôles différents (orgue ≠ chant, cf. §11.9 et mémoire *OMR staff meter & merge*).
- **Modulation** : passage **temporaire** dans une autre tonalité, souvent sans
  changement d'armure — repérable à un afflux d'**altérations accidentelles** (et
  parfois un vrai changement d'armure). ⚙️ Une modulation est **légale** : ne pas
  traiter ses accidentelles comme des erreurs. Un changement d'armure explicite est
  porté par `Measure.key_fifths`/`key_tonic` (§7.5) et, en sol-fa, annoncé par un
  « Doh = … » (direction `words`). Détecter/nommer une modulation **non marquée**
  reste 🚧 hors périmètre v1 (la tonique déclarée fait foi, §9).

### 8.6 Ambitus SATB — octave par défaut d'une voix 🎵⚙️

Un arrangement choral répartit les voix en **S**oprano (femme aiguë), **A**lto
(femme grave), **T**énor (homme aigu), **B**asse (homme grave) → sigle **SATB**.
Leurs ambitus approximatifs se chevauchent mais se centrent, du grave à l'aigu,
Basse < Ténor < Alto < Soprano.

> ⚙️ **Pourquoi ça compte ici.** Le sol-fa est *mouvable-do* et n'écrit l'octave
> que par marques `'` / `,` (`solfa-format.md` §2). Quand une voix ne précise pas
> son octave, le **rôle SATB fixe l'octave par défaut** raisonnable (une basse
> sonne plus bas qu'un soprano) pour le rendu MusicXML et le playback. La *tessiture*
> (zone confortable, plus étroite que l'ambitus total) sert de garde-fou : une
> syllabe qui projetterait une voix **très** au-delà de sa tessiture signale
> souvent une marque d'octave `'`/`,` mal lue (§11.2), pas un saut réel.

---

## 9. Transposition ⇄ mouvable-do

- **Transposer** = déplacer toutes les notes du **même intervalle** + adopter la
  **nouvelle armure** ; la pièce sonne plus haut/bas mais garde sa structure.
  Majeur→majeur et mineur→mineur seulement (majeur↔mineur ≠ transposition).
- 🎵 **Lien fondamental :** *le sol-fa tonique est une notation invariante par
  transposition.* Les syllabes (degrés) ne changent pas ; **seule la tonique
  change**. D'où :
  - **portée → sol-fa** = « lire en mouvable-do » : rapporter chaque note au
    degré qu'elle occupe dans la tonalité (chaîne `app/staff` → `from_musicxml`) ;
  - **sol-fa → portée** = fixer la tonique déclarée, puis dérouler les degrés en
    hauteurs absolues (`keys.py: resolve_pitch`, §4.2).

> ⚙️ **La tonique est une métadonnée à conserver absolument** (paramètre
> API/CLI), **jamais devinée depuis les syllabes** — c'est la Règle d'or de
> CLAUDE.md. Les **instruments transpositeurs** (clarinette en si♭, cor en fa…)
> écrivent à une hauteur ≠ hauteur réelle : à retenir comme métadonnée éventuelle,
> 🚧 hors périmètre v1.

---

## 10. Applicabilité au sol-fa — récapitulatif

| Concept | 🎼 Portée | 🎵 Sol-fa | Statut v1 Moozika |
| --- | --- | --- | --- |
| 12 demi-tons, enharmonie, `Pitch(step,alter,octave)` | ✅ | ✅ (via degré+delta) | **Livré** |
| Clé de hauteur (sol/fa/ut) | ✅ lecture | ➖ métadonnée seule | **Livré** |
| Armure / `fifths` / cercle des quintes | ✅ | ✅ (déduit de `tonic`) | **Livré (majeur)** |
| Gamme majeure = patron mouvable-do | ✅ | ✅ **cœur** | **Livré** |
| Chromatismes (`-i`/`-a`) | ✅ (altérations) | ✅ | **Livré** |
| Gamme mineure (nat./harm./mél., la-based) | ✅ | ⚠️ convention posée | 🚧 **Non géré** |
| Intervalles (nombre + qualité) | ✅ | ✅ (validation) | Support interne |
| Valeurs, point, liaison | ✅ | ✅ (`.` `,` `-`) | **Livré** |
| Triolet (3:2) | ✅ | ✅ (3 collées) | **Livré** |
| Autres tuplets, mètre composé mal formé | ✅ | ✅ | 🚧 **Erreur explicite** |
| Invariant « chaque temps = 1 temps » | ✅ | ✅ | **Livré (filet OCR)** |
| Anacrouse (levée) | ✅ | ✅ | ⚠️ **À fiabiliser** (§7.4) |
| Signature variable | ✅ | ✅ (`(N/M)`) | 🚧 **Constante** en v1 |
| Harmonie / accords / cadences | ✅ | voix indépendantes | Piste de **validation** |
| Chiffrage d'accords (`C`, `G7`, `F/A`) | ✅ | ✅ (`Harmony`) | **Livré** (pass-through) |
| Transposition | ✅ | ✅ **par nature** | **Livré** (tonique = métadonnée) |
| Ligatures/slur = syllabe (vocal) | ✅ | ✅ | **Livré** (mapping paroles) |
| Syncope | ✅ | ✅ | **Livré** (pas une erreur) |
| Texture (homophonie/polyphonie) | ✅ | ✅ SATB monophonique | Piste de **séparation de voix** |
| Ambitus SATB → octave par défaut | ✅ | ✅ | **Livré** (rôle → octave) |
| Nuances/articulations/ornements/tempo | ✅ | ✅ (`Direction`/`NoteEl`) | **Livré** (§12, préservé) |
| Reprises / voltas | ✅ | ✅ (`repeat`/`ending`) | **Livré** ; renvois D.C./D.S./coda **partiel** |
| Modes, pentatonique, whole-tone, blues | ✅ | ✅ | 🚧 **Hors périmètre** (ne pas inventer, §13) |

---

## 11. Pièges d'implémentation (anti-erreurs)

1. **Ne pas normaliser l'orthographe.** G♯ ≠ A♭ dans le modèle ; garder
   `step`+`alter`. La pitch class ne sert qu'à l'audio (§1).
2. **Double rôle du `,`** (octave grave vs quart de temps) : désambiguïser par la
   position, cf. `solfa-format.md` §2–3. Un `,` mal lu = saut d'octave aberrant
   → détectable par intervalle (§5).
3. **Invariant de temps :** déficit ⇒ **silence** à la position manquante, jamais
   un décalage de durée/octave (§7.3).
4. **Anacrouse ≠ erreur :** 1ʳᵉ mesure incomplète légale ssi elle complète la
   dernière (§7.4). Attention à l'heuristique « 1ʳᵉ mesure fixe la signature ».
5. **Mineur, tuplets non triolet, mètre variable :** lever une **erreur
   explicite** plutôt que produire une partition fausse (§4.4, §6.3, §7.5).
6. **Triolet :** `time-modification` 3:2 et `divisions=12` (§6.3).
7. **Tonique :** métadonnée d'entrée, **jamais** inférée des syllabes (§9). La
   finale peut *confirmer* mais pas *décider*.
8. **Mètre composé (6/8…) :** battement pointé, pas N battements simples (§7.2).
9. **SATB :** 4 voix **monophoniques** indépendantes ; ne pas fusionner des voix
   de rôles différents (orgue ≠ chant), cf. mémoire *OMR staff meter & merge* et
   `solfa-format.md` §7.
10. **Syncope, modulation, note de levée interne** = **légales**, pas des erreurs
    (§6.4, §8.5, §7.4). Ne pas « recaler » ni supprimer.
11. **Notation expressive/structurelle** (nuances, articulations, reprises, tempo,
    accords) = **métadonnée à préserver**, jamais convertie ni jetée (§12).

---

## 12. Notation expressive et structurelle à préserver (fidélité) ⚙️

Objectif produit : **restituer la partition importée à ~100 %**. Or beaucoup de
signes ne touchent **ni la hauteur ni la durée** : ils ne se « convertissent » pas,
ils se **transportent tels quels**. Les jeter appauvrit la partition ; les prendre
pour du bruit ou une erreur la fausse. Le **modèle de domaine les porte déjà**
(`model.py`), la chaîne portée les **lit** (`from_musicxml.py`) et le writer les
**réémet** (`musicxml.py`).

> ⚙️ **Règle de fidélité (invariant).** Tout signe non-hauteur/non-durée reconnu à
> l'entrée est **conservé et réémis** en MusicXML à sa position. Il n'est **ni**
> converti en sol-fa **ni** utilisé pour valider le rythme **ni** supprimé. Un
> signe non géré → l'**ignorer proprement** (le laisser passer / le journaliser),
> **jamais** le transformer en note ou en silence.

| Famille | Exemples | Modèle (`model.py`) | Statut chaîne portée |
| --- | --- | --- | --- |
| **Nuances** | `pp p mp mf f ff`, `fp` | `Direction.kind='dynamics'` | **Livré** (lu/émis) |
| **Soufflets** | crescendo / decrescendo (< >) | `Direction.kind='wedge'` (+`number`) | **Livré** |
| **Accents** | accent (>), `sf/sfz`, `fp`, marcato | `NoteEl.articulations` | **Livré** |
| **Articulations** | staccato (·), legato/**slur**, tenuto, marcato | `articulations` + `slur` | **Livré** |
| **Ornements** | trille, mordant, gruppetto | `NoteEl.ornaments` | **Livré** |
| **Point d'orgue** | fermata (𝄐) | `NoteEl.fermata` | **Livré** |
| **Note d'agrément** | *grace note* (durée nulle) | `NoteEl.grace` | **Partiel** : émis par le writer (`musicxml.py`), **ignoré à la lecture** portée (hors grille) |
| **Tempo (absolu)** | ♩ = 96 (métronome) | `Direction.kind='metronome'` | **Livré** |
| **Tempo (termes)** | Andante, Allegro… | `Direction.kind='words'` | **Livré** |
| **Tempo (graduel)** | rit., accel., rall., rubato, Tempo I | `Direction.kind='words'` | **Livré** |
| **Pédale** | Ped. / * | `Direction.kind='pedal'` | **Livré** |
| **Reprises** | `\|:` `:\|`, « 3× » | `Measure.repeat` (`forward`/`backward`) | **Livré** |
| **Fins alternées** | 1ʳᵉ/2ᵈ fois (*volta*) | `Measure.ending` (`{number,type}`) | **Livré** |
| **Renvois** | D.C. (*da capo*), D.S. (*dal segno*), Segno 𝄋, Coda 𝄌, Fine | `Direction.kind='words'` (v1) | **Partiel** |
| **Accords** | `C`, `G7`, `F/A` | `Harmony(root,kind,bass)` | **Livré** (§8.4) |
| **Paroles** | syllabe sous la note / mélisme | `NoteEl.lyric`, `Measure.beat_lyrics` | **Livré** |

Précisions théoriques utiles à la reconnaissance (ne pas se tromper de sens) :

- **Point d'articulation ≠ point de durée.** Un point *à côté de la tête* allonge
  la note (§6.2) ; un point *au-dessus/en dessous* = **staccato** (articulation,
  n'affecte **pas** la durée notée). ⚙️ Un OMR qui confond les deux fausse le
  rythme. Cf. §11.
- **Slur ≠ tie** (rappel §6.2) : le **slur** relie des hauteurs **différentes**
  (phrasé/mélisme, `NoteEl.slur`) ; la **liaison (tie)** relie deux **mêmes**
  hauteurs et **additionne les durées** (`tie_start`/`tie_stop`). Seule la tie
  change la durée.
- **Reprises = structure**, pas décor : une reprise mal lue change le **nombre de
  strophes/refrains** entendus (§13 sur la forme *strophique* des fihirana). La
  double barre marque presque toujours reprises et renvois — l'utiliser comme
  indice, sans confondre avec une double barre de simple fin de section.
- **Tempo, nuances, accents** ne se lisent **pas** dans les syllabes sol-fa : ils
  vivent **au-dessus/en dessous** de la portée → à capter comme `Direction`, pas
  comme cellules de notation.

## 13. Gammes et modes hors majeur/mineur — référence anti-invention 🚧

Documentés **pour que l'OCR ne les invente pas** : hors du système majeur/mineur en
v1, une suite de notes inattendue relève de l'**erreur/bruit** (ou d'une altération
mal lue), **pas** d'une gamme exotique supposée. La tonique/mode restent des
**métadonnées d'entrée**, jamais devinées.

- **Chromatique** : 12 demi-tons (tous les demi-tons). Sert de référentiel de
  comptage ; pas de centre tonal.
- **Tons entiers** (*whole-tone*) : 6 tons, aucun centre tonal (musique « moderne »).
- **Pentatonique** : 5 notes/octave (répète à la 6ᵉ). Plusieurs patrons distincts
  (les « touches noires » n'en sont qu'un). Fréquente hors Occident.
- **Blues** : proche de la pentatonique + « blue note » (ex. ♯4/♭5 intercalée).
- **Octatonique** : 8 notes ; **microtons** : intervalles < demi-ton (hors notation
  commune).
- **Modes ecclésiastiques** (patron = touches blanches d'une note à son octave,
  *transposable*) : **Ionien** (= majeur, do→do), **Dorien** (ré→ré), **Phrygien**
  (mi→mi), **Lydien** (fa→fa), **Mixolydien** (sol→sol), **Éolien** (= mineur
  naturel, la→la), **Locrien** (si→si). Le **Dorien** (« mineur dorien » du jazz :
  3ᵉ et 7ᵉ abaissées) est le plus courant. En modal, la note de repos est la
  *finalis* (souvent la finale). 🚧 Reconnaissance modale hors périmètre v1 ;
  cohérent avec §4.4 (mineur non livré de bout en bout).

> ⚙️ Rappel de cohérence : ces gammes existent dans la source théorique (chap. 4
> et 6 du PDF) mais **aucune** n'est un mode de fonctionnement du parseur v1, qui
> ne connaît que **majeur** (livré) et **mineur** (posé, 🚧). Voir §10.

---

## Sources

- Catherine Schmidt-Jones, *Understanding Basic Music Theory*, Connexions/OpenStax
  (CNX col10363), 2015 — **CC-BY-SA 4.0**. Fichier : `docs/music_theory.pdf`.
- Contrats et décisions internes : `packages/shared-contracts/solfa-format.md`,
  `docs/architecture.md`, `docs/base_plan.md`, `CLAUDE.md`.
