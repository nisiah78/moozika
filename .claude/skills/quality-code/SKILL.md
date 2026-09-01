---
name: quality-code
description: Audit qualitatif du code par stack (Python/omr-service, Python/audiveris-service,
  PHP-Symfony/api, Next.js-TypeScript/frontend) — SOLID, design patterns (creational/behavioral/
  structural), normes PSR/conventions du stack, scalabilité, performance. Remonte ses observations
  dans docs/<stack>_audit_<datetime>_report.md sans jamais corriger le code. Utiliser quand
  l'utilisateur demande un audit de code, un audit qualité, "/quality-code", ou veut savoir si le
  code respecte SOLID/PSR/les design patterns.
---

# /quality-code — audit qualitatif du code, par stack

Ton rôle ici est de **produire un constat écrit**, pas de corriger. Ce skill est complémentaire
de `pr-check` : `pr-check` fait tourner la porte mécanique déterministe (`scripts/quality/gate.py`
— tests, syntaxe, score pylint/phpstan/eslint) avant un commit ; `quality-code` va plus loin et
regarde ce qu'aucun linter ne peut détecter — respect de SOLID, usage des design patterns,
scalabilité, conformité à l'architecture propre à ce repo. Les deux skills ne se recouvrent pas :
ne recalcule jamais un score que `gate.py` calcule déjà, cite-le.

**Règle absolue : ce skill ne modifie aucun fichier de code, n'écrit aucun test, ne lance aucun
correcteur automatique.** Il écrit uniquement des fichiers de rapport sous `docs/`. Si
l'utilisateur veut que les observations soient corrigées, c'est une tâche séparée, explicite, hors
de ce skill (règle CLAUDE.md).

## Les 4 stacks

| Stack | Racine | Techno |
| --- | --- | --- |
| `omr` | `apps/omr-service` | Python / FastAPI |
| `audiveris` | `apps/audiveris-service` | Python / FastAPI (conteneur Java à part, mais le code audité ici est le Python) |
| `api` | `apps/api` | PHP 8.2 / Symfony 7 / API Platform |
| `frontend` | `apps/frontend` | Next.js 14 / TypeScript / React |

`packages/shared-contracts/` et `docs/` ne sont **pas** des stacks auditables (pas de code, pas de
lint associé dans `gate.py`) — ne pas les inclure même sur demande générique d'« audit complet ».

## Étape 1 — déterminer le périmètre

Lis les arguments passés au skill : une liste de noms parmi `omr`, `audiveris`, `api`, `frontend`.

- **Aucun argument** → les 4 stacks, en parallèle. C'est le comportement par défaut : le but du
  skill est un audit par stack, pas un audit unique.
- **Un ou plusieurs noms valides** → seules ces stacks-là.
- **Un nom invalide** → liste les 4 noms valides et arrête-toi. Ne devine jamais quelle stack
  l'utilisateur voulait dire.

Avant de lancer les agents, calcule un contexte partagé par tous les rapports de cette invocation :

```bash
TS=$(date +%Y%m%d-%H%M)
git rev-parse --short HEAD
git status --porcelain | wc -l
```

Ce skill audite le **worktree actuel**, pas seulement le dernier commit — si des fichiers sont
modifiés/non commités, chaque rapport doit le dire dans son en-tête plutôt que de laisser croire
qu'il n'a regardé que du code committé.

## Étape 2 — spawn un agent par stack, en parallèle

Un seul message, un tool call `Agent` (`subagent_type: general-purpose`) par stack en scope — ne
jamais les lancer séquentiellement, ils sont indépendants. Chaque agent démarre **sans contexte** :
son prompt doit être autonome. Inclure dans chaque prompt :

1. **Racine et structure connue du stack.**
   - `omr` : `app/solfa/` (lexer→keys→rhythm→parser→musicxml), `app/pdf/` (extract/ocr/layout/
     document), `app/staff/` (recognize via Audiveris), `app/pdf/models/`.
   - `audiveris` : le code Python du conteneur (`merge.py`, `consolidate.py` et alentours) —
     dé-condensation SATB, fusion par rôle.
   - `api` : `src/Entity`, `src/Controller`, `src/Repository`, `src/Service`, `src/ApiResource`,
     `src/State`, `src/Message`, `src/MessageHandler`, `src/Command`.
   - `frontend` : `src/app/` (routes : partition, bibliotheque, import, apprendre, a-propos,
     contact, api), `src/components/`, `src/lib/`.

2. **Règles d'architecture propres à ce repo à vérifier en plus de SOLID générique** (extraites de
   `CLAUDE.md` — l'agent doit lire `CLAUDE.md` et `docs/architecture.md` lui-même pour le contexte
   complet, ceci n'est qu'un point de départ) :
   - `omr`/`audiveris` : `app/solfa` doit rester **100% stdlib**, aucune dépendance externe
     importée (vérifier les imports) ; règle de composition musicale — dans chaque mesure, la
     somme des durées notes+silences doit faire exactement 1 temps, une note non reconnue doit
     être remplacée par un silence plutôt que silencieusement omise.
   - `api` : « le navigateur ne parle jamais directement à Python » et « Symfony ne fait aucun
     traitement musical/IA — il orchestre uniquement » → vérifier qu'aucun Controller/Service ne
     contient de logique musicale (hauteurs, durées, tonalité) qui devrait vivre côté `omr-service`.
     Vérifier aussi la **cohérence du niveau phpstan** entre `apps/api/grumphp.yml`,
     `apps/api/phpstan.dist.neon` et `scripts/quality/thresholds.json` — CLAUDE.md exige qu'ils
     soient identiques ; signaler toute divergence comme observation factuelle (fichier + valeur
     lue dans chacun des trois), sans supposer laquelle est la bonne.
   - `api` — **PSR-4, un fichier = une classe/interface/trait** (vérification systématique,
     obligatoire à chaque audit `api`, pas seulement sur signalement) : `composer.json` mappe
     `App\` → `src/` en PSR-4, ce qui veut dire que `App\Xxx\Yyy` doit vivre dans
     `src/Xxx/Yyy.php`. Parcours chaque fichier de `src/` et repère ceux qui déclarent **plus
     d'une** classe/interface/trait (`grep -c '^\(final \|abstract \)*\(class\|interface\|trait\) '
     src/**/*.php` ou lecture directe). Pour chaque cas trouvé :
     - vérifie si les classes surnuméraires sont importées/instanciées ailleurs
       (`grep -rn "use App\\\\...NomDeLaClasse"` dans `src/`) — si oui, c'est un risque réel, pas
       un style nit ;
     - vérifie si `apps/api/Dockerfile` passe `--optimize-autoloader`/`-o` à `composer install` —
       **sans cette option**, l'autoloader Composer résout une classe uniquement via son chemin
       PSR-4 calculé (namespace → fichier), donc toute classe qui n'a pas son propre fichier ne se
       charge que par accident, si un autre fichier du même module a déjà été chargé avant elle
       dans l'ordre d'exécution — un `Class not found` fragile, qui dépend de l'ordre d'appel et
       peut casser dès qu'un nouveau point d'entrée (test, commande CLI, autre provider) instancie
       la classe en premier ;
     - classe l'observation en **Majeur** (pas Mineur) si le risque de rupture est réel (classe
       importée/instanciée ailleurs et pas d'`--optimize-autoloader`), en Mineur si c'est purement
       cosmétique (ex. deux petites classes toujours utilisées ensemble, dans le même fichier que
       leur consommateur unique, sans import externe).
     Exemple déjà identifié dans ce repo (2026-08-26, à re-vérifier à chaque audit plutôt qu'à
     recopier tel quel — le code peut avoir changé) : `src/ApiResource/ScoreResource.php` déclare
     3 classes (`ScoreResource`, `ScoreListResponse`, `ScoreListItem`) ; les deux dernières sont
     importées et instanciées dans `src/State/ScoreProvider.php`, et `apps/api/Dockerfile:17-18`
     n'utilise pas `--optimize-autoloader` — c'est exactement le cas Majeur décrit ci-dessus.
   - `frontend` : MusicXML est le pivot — ne jamais traiter le texte sol-fa comme source de
     vérité ; OSMD ne rend pas le sol-fa tonique nativement (rendu maison attendu).

3. **Commandes à lancer soi-même** (codebase entière, pas un diff) — citer leur sortie réelle,
   **ne jamais recalculer un score** :
   - `omr` : `docker compose run --rm -T -w /app omr-lint pylint --rcfile=/app/.pylintrc app tests`
     puis `cd apps/omr-service && python3 -m unittest discover -s tests -v`.
   - `audiveris` : `docker compose run --rm -T -w /audiveris omr-lint pylint --rcfile=/app/.pylintrc app tests`
     puis `cd apps/audiveris-service && python3 -m unittest discover -s tests -t . -v`.
   - `api` : `cd apps/api && vendor/bin/grumphp run --no-interaction`. **Aucun test PHPUnit
     n'existe dans ce repo** — le rapport doit le dire explicitement plutôt qu'afficher un faux
     vert (lacune déjà assumée dans CLAUDE.md, pas à combler par ce skill).
   - `frontend` : `cd apps/frontend && npm run lint && npm run typecheck && npm test`.

   Note pour `omr`/`audiveris` : `.pylintrc` désactive volontairement `duplicate-code`, `fixme`,
   `too-few-public-methods`, `import-outside-toplevel`, et les docstrings manquantes — ce sont des
   décisions actées du repo, ne pas les re-signaler comme violations. Les règles de complexité
   (`too-many-*`) restent actives et sont pertinentes pour la section SOLID/scalabilité.

4. **Le gabarit de rapport exact** (ci-dessous) et le **chemin de sortie exact** :
   `docs/<stack>_audit_<TS>_report.md` (utiliser le `TS` calculé à l'étape 1, partagé par tous les
   agents de cette invocation).

5. **Règle anti-hallucination**, à coller littéralement dans chaque prompt : *chaque observation
   doit citer un fichier:ligne réellement lu dans le code. N'avance aucun constat non vérifié — en
   cas de doute, formule-le comme point à vérifier dans la section « Hors périmètre », jamais comme
   une affirmation.* C'est la règle CLAUDE.md du repo (pas d'assomption, pas d'hallucination,
   décision confirmée à 100% ou proposition explicite).

6. **Rappel explicite** : n'écrit qu'un seul fichier — le rapport. Ne modifie, ne corrige, ne crée
   aucun autre fichier.

## Gabarit de rapport

```markdown
# Audit qualité — <stack> — <date lisible>

**Stack :** <chemin racine> (<techno>)
**Commit audité :** <sha court> (<worktree modifié : N fichiers> | <worktree propre>)
**Outils exécutés :** <commandes lint/tests réellement lancées>

## 1. Résumé exécutif
Compte d'observations par sévérité (Bloquant / Majeur / Mineur), verdict qualitatif global en
quelques phrases. Pas de note chiffrée globale — `gate.py` reste la seule autorité pour les scores.

## 2. Résultats bruts outillage
Sortie citée (pas recalculée) du lint et des tests lancés à l'étape 2.3.

## 3. Principes SOLID
Sous-sections **Single Responsibility**, **Open/Closed**, **Liskov**, **Interface Segregation**,
**Dependency Inversion**. Chaque observation au format :
`**[Sévérité]** fichier:ligne — constat (citation) — pourquoi c'est un problème — recommandation
(sans l'implémenter)`.

## 4. Design patterns
Sous-sections **Creational**, **Behavioral**, **Structural** — usage correct existant, mésusage,
ou opportunité manquée. Une abstraction non justifiée par un besoin réel du code (sur-ingénierie)
est aussi une observation valide, à documenter comme telle plutôt qu'à ignorer.

## 5. Normes PSR / conventions du stack
PSR-1/PSR-4/PSR-12 pour `api` (au-delà de ce que php-cs-fixer/phpstan couvrent déjà
automatiquement) — **inclut systématiquement le contrôle PSR-4 « un fichier = une
classe/interface/trait »** décrit à l'étape 2.2, jamais optionnel pour ce stack ; conventions
actées dans `.pylintrc` pour `omr`/`audiveris` ; conventions ESLint/TypeScript strict pour
`frontend`.

## 6. Scalabilité & performance
N+1, I/O bloquant, absence de pagination/index, complexité algorithmique évitable, opérations
synchrones qui devraient être asynchrones, etc.

## 7. Conformité à l'architecture du projet
Vérification contre les règles explicites listées à l'étape 2.2 (CLAUDE.md / docs/architecture.md
/ packages/shared-contracts/music-theory.md le cas échéant).

## 8. Recommandations priorisées
Liste ordonnée par impact, sans engager d'implémentation.

## 9. Hors périmètre / points à vérifier
Transparence sur les limites de cet audit : fichiers non lus, doutes non tranchés, zones à
creuser dans un audit ultérieur.
```

## Étape 3 — vérification légère, pas de relecture complète

Une fois tous les agents terminés (notifications), **ne relis pas le contenu complet des
rapports** — ce serait réinjecter dans ton contexte tout ce que les agents ont volontairement écrit
à part. Fais juste :

```bash
ls -la docs/*_audit_${TS}*
grep -c '\*\*\[Bloquant\]\*\*' docs/<stack>_audit_${TS}_report.md
grep -c '\*\*\[Majeur\]\*\*' docs/<stack>_audit_${TS}_report.md
grep -c '\*\*\[Mineur\]\*\*' docs/<stack>_audit_${TS}_report.md
```

(le gabarit produit des observations au format `**[Sévérité]** fichier:ligne — ...` — bien
compter sur `\[Sévérité\]`, pas sur `Sévérité` seul, sous peine de toujours compter 0. Ce grep est
volontairement approximatif : la section 8 « Recommandations priorisées » reprend le tag de
sévérité de certaines observations déjà comptées en section 3-6, donc le total grep peut dépasser
le compte donné dans le « Résumé exécutif » de l'agent. En cas d'écart, préfère toujours le compte
du Résumé exécutif — le grep ne sert qu'à confirmer que le rapport contient bien des observations,
pas à en donner le total exact.)

Puis présente un tableau à l'utilisateur : stack → chemin du rapport → décompte
Bloquant/Majeur/Mineur. S'il veut le détail d'un rapport précis, lis-le à ce moment-là, pas avant.

## Ce que ce skill ne fait pas

- Il ne corrige jamais le code, n'écrit jamais de test, ne lance jamais de correcteur automatique
  (`--fix`, `php-cs-fixer fix`, etc.).
- Il ne recalcule aucun score — `scripts/quality/gate.py` reste la seule autorité pour les scores
  pylint/phpstan/eslint.
- Il ne remplace pas `pr-check` : ce n'est pas une porte de commit, il ne bloque rien et peut être
  lancé à tout moment, indépendamment de l'état de l'index git.
- Il n'avance aucune observation non vérifiée par une lecture réelle du code.
