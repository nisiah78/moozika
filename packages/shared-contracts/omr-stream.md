# Contrat SSE — `POST /pdf/parse/stream`

Interface stable entre `omr-service`, le proxy Next (intérimaire) et, plus
tard, Symfony Messenger → Mercure. Le navigateur ne parle **jamais**
directement à Python.

## Endpoint

```
POST /pdf/parse/stream
Content-Type: multipart/form-data
  file  : PDF ou image
  tonic : optionnel (ex. « A ») — force la tonique du sol-fa scanné
```

Réponse : `Content-Type: text/event-stream`.

L'endpoint sync `POST /pdf/parse` reste inchangé (CLI, tests, workers).

## Format SSE

Chaque message :

```
event: <name>
data: <json>

```

Commentaires heartbeat (toutes les ~15 s pendant Audiveris) :

```
: ping

```

## Événements

### `progress`

```json
{ "phase": "detect|ocr|layout|audiveris|convert", "pct": 0-100, "message": "…" }
```

| phase | quand |
| --- | --- |
| `detect` | classification PDF (sol-fa vs portée vs scan) |
| `ocr` | OCR page par page (Paddle / Tesseract) |
| `layout` | reconstruction des voix |
| `audiveris` | reconnaissance portée (boîte noire) |
| `convert` | parse sol-fa / MusicXML |

### `voice`

Émis après chaque voix parsée (chemin sol-fa PDF uniquement) :

```json
{
  "index": 0,
  "total": 4,
  "voice": { "name": "Soprano", "notation": "d : r : …", "model": { … } }
}
```

### `done`

Même forme que la réponse de `/pdf/parse` :

```json
{
  "result": {
    "header": { "title", "tonic", "timeSignature", "tempo" },
    "voices": [ { "name", "notation", "model" } ],
    "musicxml": "…",
    "source": "solfa_pdf|audiveris",
    "warnings": []
  }
}
```

### `error`

```json
{ "detail": "message d'erreur" }
```

## Flux Symfony (cible — `apps/api` non implémenté)

1. Client → `POST /scores` (Symfony) → `202 { jobId, scoreId }`.
2. Worker Messenger → `POST omr-service/pdf/parse/stream` (URL fichier interne).
3. Chaque événement SSE est republie vers Mercure (`/jobs/{id}`).
4. Sur `done` : stocke MusicXML, Job=`done` ; client `GET /scores/{id}`.

Le schéma d'événements ci-dessus **ne change pas**.
