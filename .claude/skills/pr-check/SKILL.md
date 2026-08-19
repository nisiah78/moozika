---
name: pr-check
description: Porte de qualité avant commit — lance les tests et les outils qualité des seuls stacks touchés par l'index, puis commite avec un message généré si tout passe. Utiliser quand l'utilisateur veut committer, préparer une PR, vérifier ses modifications, ou dit "pr-check", "porte", "gate", "je commite".
---

# /pr-check — porte de qualité avant commit

Ton rôle ici est **d'orchestrer**, pas de juger la qualité toi-même. Le verdict vient
d'un script déterministe (`scripts/quality/gate.py`) qui n'appelle aucun modèle. Tu ne
réinterprètes pas son résultat, tu ne le contournes pas, tu ne « répares » rien sans
demande explicite.

## Étape 1 — vérifier le périmètre

```bash
git diff --cached --name-only --diff-filter=ACMR
```

- **Index vide** → n'indexe RIEN de toi-même. Affiche les fichiers modifiés regroupés par
  stack (`git status --porcelain`) et demande lesquels indexer. `git add -A` est interdit :
  le worktree contient des artefacts de debug et des fichiers non suivis sans rapport.
- **Index non vide** → continue.

Vérifie aussi la branche : `git rev-parse --abbrev-ref HEAD`. Si c'est `main`, signale-le
**une fois** (« le commit ira sur `main` — l'historique du repo travaille comme ça, je
continue ? ») et respecte la réponse. Ne crée pas de branche sans accord.

## Étape 2 — lancer la porte

```bash
python3 scripts/quality/gate.py
```

Puis lis le rapport machine :

```bash
cat .git/pr-gate-report.json
```

Le script fait tout le travail de sélection : il lit l'index, en déduit les stacks touchés,
et ne lance que leurs contrôles.

| Stack détecté | Niveau 1 (bloquant) | Niveau 2 (scoré) |
| --- | --- | --- |
| `omr` | contrôle de syntaxe + suite `unittest` complète | pylint (via Docker) |
| `audiveris` | contrôle de syntaxe + suite `unittest` | pylint (via Docker) |
| `api` | `php -l` seulement — **aucun test PHP n'existe dans le repo** | phpstan + php-cs-fixer |
| `frontend` | `tsc --noEmit` + tests tsx | eslint |
| `docs` | aucun | aucun |

## Étape 3 — interpréter le verdict

Lis `verdict` dans le rapport.

### `fail` avec des `blockers`
Périmètre invalide (index vide, artefact interdit indexé). Dis lequel, propose de le
désindexer (`git restore --staged <fichier>`), n'insiste pas.

### `fail-tier1` sur un stack
Un test échoue ou le code ne compile pas. **Ne commite pas.** Rapporte :
- le stack et l'étape en échec (`tier1[].name`),
- la commande exacte à rejouer (`tier1[].cmd` + `cwd`),
- l'extrait d'erreur (`tier1[].output_tail`).

Puis arrête-toi. Tu ne corriges le code que si l'utilisateur le demande — et dans ce cas
c'est une tâche à part, pas une étape de la porte (règle CLAUDE.md : on ne force pas une
solution pour faire passer un contrôle).

### `fail-tier2` sur un stack
Le score est sous le seuil. Affiche le score, le seuil, le nombre de points, et les règles
les plus fréquentes (`tier2[].detail.rules` pour eslint,
`detail.messageTypeCount` pour pylint, `detail.files_to_fix` pour php-cs-fixer). Ne commite
pas. Propose la commande de correction automatique quand elle existe
(`npm run lint -- --fix`, `vendor/bin/php-cs-fixer fix`) sans la lancer d'office.

### `pass`
Passe à l'étape 4.

Note : si `report_only` vaut `true` dans le rapport, le seuil du Niveau 2 n'est pas encore
calibré (`score_threshold: null` dans `scripts/quality/thresholds.json`) — le score est
alors **informatif**. Dis-le explicitement plutôt que d'annoncer un vert complet.

## Étape 4 — commiter

Lis le diff indexé pour rédiger le message :

```bash
git diff --cached --stat
git diff --cached
```

Format :

```
<type>(<scope>): <sujet ≤ 72 caractères>

<corps : le POURQUOI, pas la liste des fichiers>
```

- `type` ∈ `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`, `build`
- `scope` ∈ `omr`, `api`, `frontend`, `audiveris`, `contracts`, `infra`
- Plusieurs stacks touchés → scope du stack dominant, les autres dans le corps.
- Le corps explique l'intention et les décisions, pas l'inventaire du diff.

Commite **l'index uniquement** (jamais `-a`, jamais `git add`) :

```bash
git commit -m "$(cat <<'EOF'
<message>
EOF
)"
```

Termine le message par la ligne de co-auteur exigée par la configuration du dépôt.

Puis affiche `git log -1 --stat` et rends la main. **Ne pousse pas, n'ouvre pas de PR** —
c'est hors périmètre de ce skill, par décision explicite.

## Étape 5 — proposer l'audit (optionnel)

Après le commit, propose — une seule fois, réponse par défaut « non » :

> Commit fait. Tu veux un audit de code par Claude ? `/code-review` (standards + spec)
> ou `/security-review` (sécurité). Sinon, à toi pour la suite.

**Réutilise ces skills existants, n'écris pas d'audit maison.** N'en lance aucun sans
demande explicite : ce sont des passes coûteuses, volontairement séparées de la porte
mécanique.

## Ce que ce skill ne fait pas

- Il ne modifie pas le code pour faire passer un contrôle.
- Il n'indexe rien tout seul, ne pousse pas, n'ouvre pas de PR.
- Il ne contourne pas la porte (`--no-verify` est réservé à l'utilisateur).
- Il ne recalcule pas les scores lui-même : `gate.py` est la seule autorité.
