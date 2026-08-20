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

La **théorie musicale** qui sous-tend la reconnaissance/composition (hauteurs, gammes, mouvable-do,
rythme, mètre, harmonie, transposition) est distillée en règles d'implémentation dans
`packages/shared-contracts/music-theory.md`. **Lire `packages/shared-contracts/music-theory.md` avant toute décision touchant la reconnaissance
des notes, le rythme, la tonalité ou la composition** — il rattache chaque règle du code à sa cause
théorique et marque ce qui vaut pour la portée (🎼), pour le sol-fa (🎵) et ce qui est hors périmètre
v1 (🚧). En cas de contradiction : `music-theory.md` fait foi sur la théorie musicale,
`solfa-format.md` sur le format texte, `architecture.md` sur l'architecture.

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

## Qualité & commit : la porte pré-commit

Avant tout commit, une porte **déterministe** (aucun appel à un modèle) lance les contrôles des
**seuls stacks touchés par l'index**. Cerveau unique : `scripts/quality/gate.py` (stdlib pure,
utilisable hors Claude Code). Rapport machine : `.git/pr-gate-report.json`.

Deux niveaux, volontairement séparés :

| Niveau | Contenu | Tolérance |
| --- | --- | --- |
| **1 — bloquant** | tests du stack, `tsc --noEmit`, `php -l`, syntaxe Python (`ast.parse`) | **zéro** — du code qui ne compile pas ou dont les tests échouent ne passe jamais |
| **2 — scoré** | pylint / phpstan **niveau 8** + php-cs-fixer / eslint | note sur 10, seuil dans `scripts/quality/thresholds.json` |

Formule du Niveau 2 (celle de pylint, appliquée à tous les stacks) :
`score = 10 × (1 − points / N)`, `N` = **lignes ajoutées** par le diff sur les fichiers
réellement lintés. Le dénominateur « lignes ajoutées » et non « LOC des fichiers entiers » est
un choix mesuré : avec les fichiers entiers, `N > 6000` rend n'importe quel seuil inopérant.

Seuil actuel : **8,0/10**, calibré le 2026-08-19 sur mesure réelle (api 8,81 · omr 9,46 ·
audiveris 9,63 · frontend 9,96). Remettre `score_threshold` à `null` repasse le Niveau 2 en mode
mesure ; le Niveau 1 bloque indépendamment de ce réglage.

Règles pylint désactivées par décision (cf. `apps/omr-service/.pylintrc`) :
`import-outside-toplevel` (les imports tardifs gardent `app/solfa` sans dépendance externe) et les
docstrings de fonctions/classes internes. La famille « complexité » (`too-many-*`) reste **active**.

```bash
make gate           # porte complète (Niveau 1 + score) sur ce qui est INDEXÉ
make gate-report    # mesure tout le worktree modifié, ne bloque jamais
make lint           # les 3 chaînes qualité (py via Docker, php via GrumPHP, front)
make hooks          # active le hook versionné (une fois par clone) — DÉJÀ FAIT ici
```

### Ce que le hook lance vraiment

`scripts/hooks/pre-commit` lance le **Niveau 1 des seuls stacks touchés**, en déléguant le routage
à `gate.py --tier1-only` (la table chemin → stack n'existe qu'à un endroit). Coûts mesurés :

| Fichier indexé | Ce qui tourne | Coût |
| --- | --- | --- |
| `*.py` | syntaxe `ast.parse` + suite `unittest` du stack | omr 4,4 s · audiveris 0,04 s |
| `*.ts` / `*.tsx` | `tsc --noEmit` + tests tsx | 5,5 s |
| `*.php` | GrumPHP (phpstan 8, phpcsfixer, jsonlint, yamllint) | 1,4 s |
| les trois ensemble | — | ~8,6 s |

Le **Niveau 2 reste hors du hook** : pylint prend ~23 s via Docker, et un hook lent se contourne au
`--no-verify`, donc devient inutile. Il vit dans `make gate` / `/pr-check`.

Historique de la décision : au départ le hook ne faisait que de la syntaxe, si bien que **seul PHP
était réellement gardé** (GrumPHP s'installe tout seul via son plugin Composer) tandis que Python
n'avait qu'un contrôle de syntaxe et Next.js **rien du tout**. La parité par stack corrige ça.
Ne pas revenir à un hook « syntaxe seule » sans mesurer : le déséquilibre n'était pas voulu.

Skill `/pr-check` : orchestre porte → message de commit → commit de l'index → proposition
d'audit (`/code-review`, `/security-review`). Il ne pousse pas, n'ouvre pas de PR, n'indexe rien
tout seul et ne corrige jamais le code pour faire passer un contrôle.

### GrumPHP : le PHP a sa propre chaîne

`apps/api/grumphp.yml` déclare 4 tâches — `phpstan` (niveau 8), `phpcsfixer`, `jsonlint`
(`detect_key_conflicts`), `yamllint`. Le correcteur interactif est **désactivé**
(`fixer.enabled: false`) : une invite dans un hook n'a pas de sens, et un outil qui réécrit le code
pour faire passer son propre contrôle est l'inverse d'une porte déterministe.

**Le niveau phpstan doit rester identique dans les trois points d'entrée** :
`apps/api/grumphp.yml` (`level: 8`), `apps/api/phpstan.dist.neon` (`level: 8`) et
`scripts/quality/thresholds.json` (`phpstan_level: 8`). Sinon `make lint-php` et GrumPHP annoncent
des volumes d'erreurs différents sur le même code.

**Piège de hooks résolu** : GrumPHP installe son propre `.git/hooks/pre-commit`, que
`core.hooksPath=scripts/hooks` (posé par `make hooks`) rendrait muet. `scripts/hooks/pre-commit`
**délègue donc à GrumPHP** dès qu'un `.php` est indexé (même protocole : diff sur stdin,
`GRUMPHP_GIT_WORKING_DIR` = racine, `cd apps/api`), et `scripts/hooks/commit-msg` fait de même pour
la phase commit-msg. Ne jamais remettre un `php -l` direct à la place : ce serait revenir en arrière
et court-circuiter phpstan/jsonlint/yamllint. Coût mesuré : **1,4 s** quand du PHP change,
0,01 s sinon. GrumPHP tourne aussi depuis `apps/api` en direct :
`vendor/bin/grumphp run --no-interaction`.

Attention : les conteneurs qui montent `apps/api` écrivent en **root** dans le volume
(`grumphp.yml` a été créé root:root). Si un fichier de config devient non modifiable, le supprimer
puis le réécrire suffit — le dossier parent appartient à l'utilisateur.

Deux contraintes d'environnement à connaître :
- **`pip` est cassé en local** (`No module named pip`) → pylint vit dans le stage `quality` du
  Dockerfile omr-service (`make lint-py`). Sa config est dans `apps/omr-service/.pylintrc`,
  **monté au runtime** : la mettre dans `pyproject.toml` invaliderait la couche Docker qui
  installe torch/paddle (~10 min de rebuild par règle ajustée).
- **`apps/omr-service/app/__pycache__` appartient à root** (ancien run Docker monté) → le contrôle
  de syntaxe utilise `ast.parse` (`scripts/quality/syntax_check.py`), jamais `py_compile` qui
  écrirait un `.pyc`.

Lacune assumée : **`apps/api` n'a aucun test** (pas de PHPUnit, pas de `tests/`). Son Niveau 1 se
limite à `php -l` dans `gate.py`, et le rapport le dit explicitement au lieu d'afficher un vert
trompeur. Au commit, GrumPHP ajoute l'analyse statique mais toujours aucun test de comportement.

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
