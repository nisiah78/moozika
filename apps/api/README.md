# api (Symfony 7) — persistance des partitions

Point d'entrée métier pour le stockage des partitions (MusicXML + métadonnées).
Le navigateur appelle cette API ; elle parle à PostgreSQL, MinIO et `omr-service`.

## Endpoints

| Méthode | Route | Rôle |
| --- | --- | --- |
| `GET` | `/health` | Santé |
| `GET` | `/scores` | Liste |
| `POST` | `/scores` | Créer (save manuel) |
| `GET` | `/scores/{id}` | Dernière version + MusicXML |
| `POST` | `/scores/{id}/versions` | Nouvelle version (édition) |
| `POST` | `/convert/model-to-musicxml` | Régénère MusicXML via omr |

Pas d'auth utilisateur en v1. MinIO et Postgres restent authentifiés côté serveur.

## Dev

```bash
# depuis la racine du monorepo
make docker-up
# API : http://localhost:8080/health
```

Variables : voir `.env` (`DATABASE_URL`, `MINIO_*`, `OMR_SERVICE_URL`).
