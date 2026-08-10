# omr-service

Microservice Python (FastAPI) de reconnaissance / conversion musicale.

État actuel :
- **sol-fa tonique → MusicXML** (texte, PDF typographié, OCR)
- **portée / solfège → MusicXML → sol-fa éditable** via [Audiveris](../audiveris-service/) (conteneur séparé)
- **MusicXML → sol-fa** (`from_musicxml`, `to_solfa`)

## Structure

```
app/
  main.py            # API FastAPI
  solfa/             # sol-fa (texte) -> MusicXML
    ...
  pdf/               # PDF/image sol-fa -> voix -> MusicXML
    detect.py        #   classification PDF (sol-fa vs portée vs scan)
    ...
  staff/             # portée -> Audiveris -> MusicXML -> sol-fa
    recognize.py
tests/               # unittest + fixtures ; OCR intégré si tesseract présent
demo/index.html      # viewer OSMD de démonstration
```

Format d'entrée documenté : [../../packages/shared-contracts/solfa-format.md](../../packages/shared-contracts/solfa-format.md)

## Tests (aucune installation requise)

```bash
python -m unittest discover -s tests -v      # ou, depuis la racine : make test
```

Dans Docker :

```bash
make docker-test
# équivaut à : docker compose run --rm omr-test
```

## CLI

```bash
# sol-fa texte
python -m app.solfa.cli --tonic C "d : d : s : s | l : l : s : -"

# PDF sol-fa (le cantique d'exemple)
python -m app.pdf.cli ../../docs/jesoa-tsy-mba-mandao.pdf                 # MusicXML SATB
python -m app.pdf.cli ../../docs/jesoa-tsy-mba-mandao.pdf --notation      # sol-fa reconstruit
python -m app.pdf.cli ../../docs/jesoa-tsy-mba-mandao.pdf --json          # en-tête + voix + modèles
```

## API

```bash
pip install -e .
uvicorn app.main:app --reload            # http://localhost:8000/docs
```

- `POST /solfa/parse` (JSON) → `{ "model": {...}, "musicxml": "..." }`
- `POST /pdf/parse` (multipart `file`) → PDF unifié : sol-fa malgache **ou** portée (Audiveris)
  → `{ "header", "voices", "musicxml", "source", "warnings?" }`
- `POST /pdf/parse/stream` — même pipeline en **SSE** (`progress` / `voice` / `done` / `error`)
  → contrat : [../../packages/shared-contracts/omr-stream.md](../../packages/shared-contracts/omr-stream.md)
- `POST /recognize` — alias explicite pour l'import portée
- `POST /musicxml/parse` — MusicXML/.mxl → sol-fa tonique

Stack Docker (portée) : depuis la racine du monorepo, `make docker-up` lance
`audiveris` (:8081), `omr-service` (:8000) et le frontend (:3000).
Variable `AUDIVERIS_URL=http://audiveris:8081` est définie dans `compose.yml`.

## Démo visuelle

Lancer l'API puis servir la démo :

```bash
uvicorn app.main:app --reload
python -m http.server 5500 --directory demo   # http://localhost:5500
```
