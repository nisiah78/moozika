# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projet

Moozika convertit des partitions entre **portée classique** (solfège) et **sol-fa tonique malgache**
(mouvable-do : `d r m f s l t` + marques d'octave, notation des *fihirana*), avec import PDF/image,
playback piano et édition. Le sens d'import fonctionne dans les **deux directions** (reconnaître une
portée *et* une feuille sol-fa).

Le plan produit et la conception détaillée vivent dans `docs/base_plan.md` (vision initiale) et
`docs/architecture.md` (décisions actées, diagrammes, roadmap phasée). **Lire `docs/architecture.md`
avant toute décision d'architecture** : il tranche plusieurs écarts vs `base_plan` (voir ci-dessous).

## Principe directeur : MusicXML est le pivot

Tout gravite autour de **MusicXML** comme format canonique et stocké. Chaque module ne connaît que ce
pivot, ce qui permet de remplacer un composant (ex. moteur OMR) sans toucher aux autres. Ne jamais
traiter le texte « Do Ré Mi » comme la source de vérité — c'est une projection du MusicXML.

Deux asymétries structurantes à garder en tête :
- **`portée → MusicXML`** via **Audiveris** (conteneur `apps/audiveris-service`, appel HTTP depuis `app/staff/`).
- **`sol-fa → MusicXML`** n'a **aucun** outil sur étagère → parseur déterministe sur-mesure (implémenté).
- Le sol-fa tonique est **relatif à une tonique** : la même mélodie en Do et en Sol donne les mêmes
  syllabes. La **tonique est une métadonnée à conserver absolument** ; elle est passée hors notation
  (paramètre API/CLI), jamais devinée depuis les syllabes.

## Structure du monorepo

Monorepo, 3 applications **indépendantes** (chacune son propre gestionnaire de dépendances) :

| App | Stack | État |
| --- | --- | --- |
| `apps/omr-service` | FastAPI + Python | **Implémenté** : sol-fa ↔ MusicXML, routage PDF unifié |
| `apps/audiveris-service` | FastAPI + Audiveris 5.11 | **Implémenté** : portée PDF → MusicXML (OMR) |
| `apps/frontend` | Next.js 14 + Tailwind + OpenSheetMusicDisplay | Import, viewer, drawer, save, édition modèle |
| `apps/api` | Symfony 7 + API Platform | **Implémenté** : scores PostgreSQL + MinIO (sans auth user) |

`packages/shared-contracts/` porte les contrats stables entre apps. Priorité actuelle : le parseur
sol-fa (le composant le plus risqué), le reste suit la roadmap phasée de `docs/architecture.md` §14.

**Règle d'or (non négociable) :** le navigateur ne parle **jamais** directement à Python. Symfony
(`apps/api`) est l'unique point d'entrée (auth, quotas, orchestration) et appelle `omr-service` en
HTTP interne. Symfony ne fait **aucun** traitement musical/IA — il orchestre uniquement.
- tu n'est pas autorisé a prendre des decisions a base d'assomption, illusion, allusion, hallunication. uniquement quand c'est confirmé à 100% que tu prend une decision sinon tu retourne avec une proposition claire.
- tu analyse dans le code interne pour trouver l'existant et compabilité, tu analyse interne et externe pour les solutions possible avant de proposer.
- ce projet est pour le moment a but non lucratifs donc les solutions attendus sont des open source aussi pour les platformes additionnel,
- si l'approche 3 fois apres tentative, tu doit analyser si l'approche doit être decouper ou voir une autre solution ou autre approche, tu ne doit pas forcer de resourdre le soucis on forçant la solution qui marche pas.
- si tu n'es pas capable de la realiser tu doit être franc, ça nous coûte du token et du token d'aller chercher une solution qui n'aboutira nulle part
- tu n'implement pas les tests unitaire a chaque fois qu'il y a une modification, uniquement et seulement quand le problème ou implementation est confirmé propre qu'on implemente le test, on veut pas résoudre une test unitaire qui sera rejetté plus tard
- tout les regles de notatition et composition musical pour sol-fa et solfège doit être respecté

Voici certain faute grave a ne pas commettre sur le reconnaissance des notes :
- erreur de composition, la totalité des notes et/ou silence dans chaque temps de chaque mesure doit faire au total de 1 temps (pas plus pas moins), s'il y a un moins c'est qu'il y a une note/silence qui a pas été reconnue ou oublié, 
exempe: d,,d => erreur: 2 note de quart de temps chaqun, il faut trouver la partie manquant, si le note a pas été reconnue, il faut connaitre juste son emplacement et la remplacer par une silence. si le note original est d,.-,d ou d,.fd mais que le "-" ou "f" on pas pu être recuperer, le note doit être d,.,d le "" indiquera au interpreteur/lecteur qu'il y a une silence et qu'on pourra la corriger dans l'interface le note manquant 

## omr-service : le cœur implémenté

Service de reconnaissance/conversion. Deux chaînes livrées, toutes deux **sol-fa → MusicXML** :

- `app/solfa/` — **sol-fa texte → MusicXML**. Pipeline déterministe en étapes nettes :
  `lexer.py` (notation → cellules) → `keys.py` (tonalité/gammes, mouvable-do → hauteur absolue) →
  `rhythm.py` (séparateurs → durées notées) → `parser.py` (orchestration → `ScoreModel`) →
  `musicxml.py` (`ScoreModel`(s) → MusicXML, mono ou SATB). `model.py` est le modèle de domaine
  (`ScoreModel`/`Measure`/`NoteEl`/`Pitch`) sérialisable en JSON, pivot interne consommable par le front.
- `app/pdf/` — **PDF/image → MusicXML SATB** (sol-fa malgache) :
  - typographié : `extract.py` décode via ToUnicode (stdlib) ;
  - scanné : `ocr.py` (PyMuPDF → OpenCV → Tesseract) produit les mêmes runs ;
  - `layout.py` / `document.py` reconstruisent la notation puis le MusicXML SATB.
- `app/staff/` — **portée → MusicXML** via Audiveris (`recognize.py`), puis `from_musicxml` → sol-fa.
  Conteneur dédié `apps/audiveris-service` (Java, `:8081`).

**Contrainte de conception clé :** `app/solfa` n'a **AUCUNE dépendance externe** (stdlib pure). Les
tests tournent donc sans installation. Préserver cette propriété : ne pas importer de lib tierce dans
le parseur cœur (FastAPI/pydantic ne servent qu'à la couche API `main.py`).

**Format d'entrée sol-fa :** documenté dans `packages/shared-contracts/solfa-format.md` — c'est
l'**interface stable** entre l'OCR, la saisie manuelle et le parseur. Cas non gérés (triolets,
mode mineur, signature variable, polyphonie dans une seule voix) → erreur de parsing explicite plutôt
qu'une partition fausse. Modifier ce contrat = décision à peser, pas un détail d'implémentation.

## Commandes

```bash
make test          # tests omr-service en local (cœur stdlib ; OCR skip si absent)
make docker-test   # suite complète dans Docker (= docker compose run --rm omr-test)
make docker-up     # postgres + minio + api + audiveris + omr + frontend → :3000 / :8080
make pdf-demo      # sol-fa malgache jesoa → MusicXML SATB dans /tmp/jesoa.musicxml
make staff-demo    # PDF portée bpi-bp1340 → sol-fa via Audiveris (Docker requis)
```

Un seul test / un seul module (depuis `apps/omr-service`) :

```bash
python3 -m unittest tests.test_parser -v          # un fichier de test
python3 -m unittest tests.test_parser.ClassName.test_method   # un cas précis
```

CLIs (depuis `apps/omr-service`) :

```bash
python -m app.solfa.cli --tonic C "d : d : s : s | l : l : s : -"
python -m app.pdf.cli ../../docs/jesoa-tsy-mba-mandao.pdf [--notation|--json|--out FILE]
```

API (`app/main.py`) : `POST /solfa/parse` (JSON), `POST /pdf/parse` (multipart `file`),
`POST /pdf/parse/stream` (SSE — voir `packages/shared-contracts/omr-stream.md`), `GET /health`.

Frontend (`apps/frontend`) : `npm run dev` / `npm run build`.

## Écarts assumés vs base_plan

`docs/base_plan.md` est la vision de départ ; `docs/architecture.md` la corrige sur des points actés :
- **Conversion sol-fa en Python (music21), pas en PHP.** Le calcul degré/intervalle/tonalité est natif
  côté Python et partage sa logique avec le parseur ; Symfony reste focalisé sur le métier.
- **Notation cible = sol-fa tonique malgache** (mouvable-do, dialecte chromatique en `-i`/`-a`), pas un
  simple mapping `C→Do`.

En cas de contradiction entre les deux docs, `architecture.md` fait foi.
