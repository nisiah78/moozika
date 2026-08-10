# audiveris-service

Microservice HTTP autour du CLI **Audiveris 5.11** (OMR portée / solfège → MusicXML).

Appelé en interne par `omr-service` (`AUDIVERIS_URL=http://audiveris:8081`). Le navigateur
ne parle jamais directement à ce service (voir `docs/architecture.md`).

## Endpoints

- `GET /health` — binaire Audiveris + config (`ghostscript`, `merge_pages`)
- `POST /recognize` — multipart `file` (PDF/image) → `{ musicxml, filename, size, meta }`
  - `meta` : voie utilisée (`method`), nb de pages rendues, motif de repli — diagnostic.

## Fusion page-par-page (récupération des mesures)

Diagnostic établi (`diagnose_omr.py`) : sur un scan chorale condensé, Audiveris
lit **correctement chaque page isolée** (somme des mesures ≈ total réel) mais en
**perd ~25 %** à l'assemblage de son *book* multi-pages (réconciliation des parts
cassée par les passages en divisi). On **éclate donc le PDF page par page**
(`pypdf`, préserve `/Rotate`), on lance Audiveris sur **chaque page**, puis on
**recolle les mesures par index de part** (`app/merge.py`, testé dans
`tests/test_merge.py`). Repli sur le book PDF entier → aucune régression.

> On garde le format **PDF** par page (pas d'image/TIFF) : Audiveris **échoue** sur
> des TIFF suréchantillonnés mais lit le PDF nativement (rotation comprise, via son
> propre Ghostscript). `_audiveris_one` tolère aussi un code de sortie ≠ 0 tant
> qu'un MusicXML a été produit (Audiveris sort non-nul sur simples avertissements).

> ⚠️ Le split enchaîne **N runs Audiveris** → un import de 10 pages prend
> ~15–30 min (d'où `AUDIVERIS_TIMEOUT=1800` côté omr-service).

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `AUDIVERIS_MERGE_PAGES` | `1` | `0` pour désactiver le split (book entier direct) |

> Ghostscript reste requis : c'est la dépendance de **rendu PDF d'Audiveris 5.11**
> lui-même (le `.deb` extrait via `dpkg-deb -x` ne la résout pas) — d'où le Dockerfile.

## Docker

```bash
docker compose up --build audiveris   # http://localhost:8081/health
```

L'image extrait le `.deb` officiel via `dpkg-deb -x` (le postinst échoue en conteneur headless).
Dépendances GTK minimales pour le mode batch headless.

## Dev local

Installer [Audiveris](https://github.com/Audiveris/audiveris/releases) puis :

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8081
```

Ou laisser `omr-service` appeler le binaire local (`AUDIVERIS_BIN` / `Audiveris` dans le PATH).
