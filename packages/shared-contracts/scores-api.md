# Contrats API scores (Symfony)

Base URL (dev) : `http://localhost:8080`  
Pas d'auth utilisateur en v1. MusicXML canonique en MinIO ; snapshot UI en JSONB.

## `GET /scores`

```json
{ "items": [{ "id", "title", "tonic", "sourceType", "status", "version", "updatedAt", "createdAt" }] }
```

## `POST /scores`

Body : `{ title, tonic, sourceType?, origin?, musicxml, model? }`  
`model` = `{ header, voices, source?, warnings? }` (forme `ScoreResult` sans musicxml).

## `GET /scores/{id}`

Dernière version : métadonnées + `header` + `voices` + `musicxml`.

## `POST /scores/{id}/versions`

Nouvelle version après édition : `{ title?, tonic?, origin?, musicxml, model? }`.

## `POST /convert/model-to-musicxml`

Body : `{ models: ScoreModel[], title?, composer?, work? }`  
Réponse : `{ musicxml, voices: [{ name, notation, model }] }`  
Symfony relaie vers `omr-service` `POST /musicxml/from-models`.

Le champ `model.header` peut aussi porter : `composer`, `work`, `mode`, `fifths`.

## `POST /convert/solfa-parse`

Body : `{ notation, tonic?, clef?, doh_octave? }`  
Réponse : `{ model, musicxml }` — parse sol-fa texte via omr-service.
