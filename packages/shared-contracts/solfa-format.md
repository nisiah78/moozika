# Format d'échange sol-fa tonique (Moozika)

Ce document définit **le format texte** consommé par le parseur
`apps/omr-service/app/solfa`. C'est l'interface stable entre :

- l'**OCR** (à venir) qui lira une image/PDF de feuille sol-fa → produit ce texte ;
- la **saisie manuelle** (édition) ;
- le **parseur** qui transforme ce texte en MusicXML + modèle JSON.

> Garder cette frontière permet de brancher l'OCR (PDF/image scanné) sans
> toucher au parseur : l'OCR produit ce même texte (via des runs positionnés
> reconstruits par `app/pdf/layout`).

## 1. Métadonnées (hors notation)

Passées séparément (paramètres d'API / CLI), car la sol-fa est *mouvable-do* :

| Champ | Défaut | Rôle |
| --- | --- | --- |
| `tonic` | `C` | Tonique déclarée par la feuille (« Doh = X »). Ex. `C`, `F`, `Bb`, `F#`. |
| `doh_octave` | `4` | Octave scientifique de la tonique (C4 = do central). |
| `clef` | `treble` | `treble` (sol) ou `bass` (fa). |

## 2. Hauteurs (syllabes)

Diatonique : `d r m f s l t` (doh ray me fah soh lah te).

Chromatismes (dialecte malgache : haussé en `-i`, baissé en `-a`) :

| Syllabe | Sens |
| --- | --- |
| `di` (`de`) | degré 1 haussé (do♯) |
| `ri` / `ra` | degré 2 haussé / baissé |
| `ma` | degré 3 baissé |
| `fi` (`fe`) | degré 4 haussé (fa♯) |
| `si` (`se`) / `sa` | degré 5 haussé / baissé |
| `li` / `la` | degré 6 haussé / baissé |
| `ta` | degré 7 baissé (si♭) |

Les formes Curwen classiques (`de`, `fe`, `se`) sont acceptées comme alias.

**Octave** (suffixe répétable) : `'` monte d'une octave, `,` **ou** `_` descend.
Ex. `d'` = doh à l'octave supérieure, `s,` = soh à l'octave inférieure.

> **Double rôle du `,`** (désambiguïsé par la position) :
> - **collé après une note** (`t,`, `s,`) → marque d'**octave grave** (une seule,
>   au plus 1 par syllabe : `d,,` = d **deux** octaves plus bas est une valeur
>   absurde interdite en composition, jamais produite) ;
> - **en séparateur** (non précédé d'une note : `,d`, `-.,d`) → **quart de temps**
>   (cf. §3).
>
> Sur une entrée OCR bruitée, `,,` (2+ virgules collées) = l'octave grave a été
> fusionnée avec un `,` de quart : on rétablit **octave grave (1 `,`) + silence**
> — `d,,d` → `d,.,d` (d grave, silence de quart, d) si `d,,.d` (d 2 octave plus bas demi-temps, d).

## 3. Rythme (hiérarchie de séparateurs)

```
partition := mesure ( '|' mesure )*
mesure    := temps ( (':' | '!') temps )*  -- ':' et '!' séparent les temps ;
                                            -- '!' marque la mi-mesure (1 temps = 1 noire)
temps     := part  ( '.' part )*           -- '.' = DEMI-temps (subdivise le temps en 2)
part      := cellule ( ',' cellule )*      -- ',' = QUART de temps (subdivise encore en 2)
cellule   := syllabe | '-' | (vide)
```

> **Règle de durée (vaut aussi en solfège)** : `.` = **demi-temps**, `,` = **quart
> de temps**. Le total des notes et silences d'un **temps** fait toujours **exactement
> 1 temps** — ni plus, ni moins. S'il manque quelque chose, c'est qu'une note/un
> silence n'a pas été reconnu : on **remplace la position manquante par un silence**
> (le vide, corrigeable ensuite dans l'interface) plutôt que de fausser la durée ou
> l'octave d'une note voisine.

- `.` est un indicateur de demi-temps, dans un temps il ne peut y avoir qu'un seul point.
- `,` est un indicateur de quart de temps, il ne peut y avoir que deux virgule dans un temps pour une indicateur de quart de temps.
- `:` et `!` séparent les temps (`!` = milieu de mesure, ex. 4/4 : `b : b ! b : b`).
- `-` : **prolongation** (liaison) de la note précédente.
- temps **entièrement vide** : **silence**.
- cellule vide **en tête** (ex. `.m`) : **silence** (anacrouse croche + note).
- cellule vide **après une note** via `.` (ex. `m.`) : **prolongation** (comme `-`).
- cellule vide **après une tenue** via `.` (ex. `-.`) : **silence** (demi-temps tenu + demi-temps de silence).
- cellule vide **issue d'un `,`** (ex. `-.,d`) : **silence explicite** (un quart).
- `-.m` : demi-temps de **tenue** de la note précédente, puis `m`.
- Le nombre de temps de la **première mesure** fixe la signature (ex. 4 temps → 4/4).
- il faut toujours verifier que la valeur des temps dans chaque mesure correspond a celui du `time signature` 

### Exemples

| Notation | Signification |
| --- | --- |
| `d : r : m : f` | 4 noires : do ré mi fa (4/4) |
| `d.r : m` | 2 croches (do ré) + 1 noire (mi) (2/4) |
| `s : -` | soh tenu 2 temps (blanche) |
| `d : : m` | do, silence, mi |
| `.m : m.s` | (silence croche + m) puis (m + s croches) |
| `t, : d'` | te grave puis doh aigu |
| `d : -.` | do, puis **tenue croche + silence croche** |
| `d : -.d` | **do tenu 1 temps ½** (noire pointée) puis do croche |
| `d : -.,d` | do noire pointée + **silence d'un quart** (double-croche) + do |

CAS EXCEPTIONNELLE A FAIRE ATTENTION:
- un `,` est en même temps un indicateur de quart de temps et l'octave en dessous d'une note, donc il faut bien distinguer.
- pour les voix/piano graves, il existe mais rarement le `,,` qui indique 2 octave plus du note qu'il faut considerer aussi.

## 4. Triolets

Un triolet s'écrit **3 syllabes collées** dans une cellule de temps, sans
`.` ni `,` rythmique : ex. `drm`, `s,lt`, `d'r'm`.

| Portée | Notation | Sens |
| --- | --- | --- |
| 1 temps | `d : drm ! m : f` | 3 notes dans 1 temps (croches de triolet) |
| 2 temps | `drm : f ! s` (+ métadonnée `spanBeats=2`) | 3 notes sur 2 temps, **sans** `:` entre eux |

Les marques `triplets: [{startMeasure, startBeat, spanBeats}]` (0-based) sont
passées hors notation (API / modèle voix) pour les spans 2 temps. Le parseur
émet des `<time-modification>` MusicXML (3:2) et passe en `divisions=12`
quand un triolet est présent.

## 5. Limites de la v1

- Subdivisions hors triolet : **binaires** uniquement (croches, doubles-croches).
- Chaque voix est **monophonique** ; la polyphonie SATB est gérée en lisant
  **plusieurs voix** assemblées en parties MusicXML distinctes (cf. §7).
- Signature supposée **constante** sur toute la pièce (sauf marqueurs `(N/M)`).
- Tonalité **majeure** (le mode mineur viendra plus tard).

Ces cas non gérés lèvent une erreur de parsing explicite plutôt que de
produire une partition fausse.

## 6. Modèle JSON de sortie (résumé)

```jsonc
{
  "tonic": "C",
  "fifths": 0,                        // armure MusicXML
  "timeSignature": { "beats": 4, "beatType": 4 },
  "divisions": 4,                     // divisions par noire
  "clef": "treble",
  "measures": [
    { "number": 1, "notes": [
      { "isRest": false, "duration": 4, "type": "quarter", "dots": 0,
        "pitch": { "step": "C", "alter": 0, "octave": 4, "syllable": "d" },
        "tieStart": false, "tieStop": false }
    ]}
  ]
}
```

La sortie MusicXML (score-partwise 4.0) est directement lisible par
OpenSheetMusicDisplay et convertible en MIDI.

## 7. Lecture directe d'un PDF (module `app.pdf`)

Deux chemins, même sortie (notation §2–3 → MusicXML) :

### 6.1 PDF typographié (texte embarqué)

Pour les PDF **typographiés** (texte + polices, recueils générés par
ordinateur), le module décode le texte via les tables ToUnicode —
**aucune OCR** — et reconstruit la notation ci-dessus :

- l'en-tête donne la tonique (« Dô dia D »), la mesure (`4/4`) et le tempo (`= c.75`) ;
- les runs de sol-fa (police du corps) sont regroupés en lignes (voix) par
  proximité verticale ; les systèmes se succèdent verticalement ;
- **barre de mesure** : dans une voix, deux temps qui se suivent **sans**
  séparateur `:`/`!` (ou variante `;`) marquent une nouvelle mesure ;
- les voix d'un système (haut → bas) sont nommées **Soprano, Alto, Tenor, Bass**
  et assemblées en 4 parties MusicXML.

Validé sur `jesoa-tsy-mba-mandao.pdf` : titre, tonique D, 4/4, tempo 75,
4 voix × 26 mesures.

### 6.2 PDF scanné / image (OCR)

Si aucun texte n'est extractible (scan, photo, export image-only), le fallback
OCR s'active (`app/pdf/ocr.py`) :

1. rendu des pages (PyMuPDF, 300 dpi) ou décodage PNG/JPEG ;
2. prétraitement OpenCV (gris, débruitage, binarisation Otsu) ;
3. Tesseract → glyphes + boîtes englobantes → mêmes `Run` que l'extracteur ;
4. `layout.build_document` → notation canonique → parseur sol-fa.

Dépendances : `pymupdf`, `opencv-python-headless`, `pytesseract`, `Pillow`,
et le binaire système `tesseract-ocr` (installé dans l'image Docker).
