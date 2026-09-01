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

Commentaires heartbeat (`_HEARTBEAT_SEC = 5 s` dans le code ; en pratique irrégulier,
voir la note sous `ping`) :

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
{ "detail": "message d'erreur", "code": "OcrError" }
```

| champ | rôle |
| --- | --- |
| `detail` | message lisible, tel que produit par l'exception |
| `code` | **nom de la classe d'exception** levée (ajout additif) |

`code` existe parce que la classe d'exception porte déjà la classification (rythme incohérent,
mètre hors périmètre v1, rien reconnu, format invalide…) alors que cette information se perdait
sur le fil : le consommateur devait la redeviner depuis le texte et cassait à la moindre
reformulation d'un message. Valeurs observées : `PdfSolfaError`, `StaffRecognizeError`,
`MusicXmlError`, `OcrError`, `ExtractError`, `ParseError`, `LexError`, `RhythmError`,
`MeterError` — plus n'importe quelle classe Python via l'`except Exception` de `main.py`.

**Champ additif, rétrocompatible** : un consommateur qui ne lit que `detail` est inchangé (c'est
le cas du front, `apps/frontend/src/lib/omrStream.ts`).

⚠️ `code` décrit **l'exception réellement levée, pas la cause racine**. `PdfSolfaError` reprend
parfois un échec Audiveris dans son propre message (`app/pdf/document.py:350`). Un consommateur
qui doit distinguer une panne d'infrastructure (retentable) d'une partition illisible
(définitive) doit donc **aussi** inspecter `detail` — et le faire **avant** de se fier au `code`.

### `ping` (côté consommateur)

Les commentaires SSE `: ping` ne sont pas un événement du protocole, mais un consommateur a
intérêt à les remonter à sa propre logique : pendant la phase `audiveris`, ils sont **le seul
trafic** pendant 15-30 min. Sans eux, impossible d'y constater une annulation ou de garder une
connexion base active. Mesuré : les pings ne sont pas réguliers pour autant — sur un PDF scanné,
le plus grand silence entre deux chunks atteint **93,6 s**, l'OCR natif retenant le GIL. Ne pas
caler un timeout d'inactivité court dessus.

## Annulation

**Fermer la connexion annule le travail.** `omr-service` teste `request.is_disconnected()`
dans la boucle du générateur et lève un jeton d'annulation coopératif
(`app/cancel.py`) que le pipeline consulte à ses points de contrôle : frontières de phase,
**entre les pages OCR**, entre les voix, et avant de lancer Audiveris.

La cascade va jusqu'au bout : `omr-service` coupe sa connexion vers `audiveris-service`
(`shutdown(SHUT_RDWR)`, et non un simple `close()` qui ne réveille pas un `recv()` bloqué),
lequel tue **le groupe de processus** de la JVM — Ghostscript enfant compris.

Trois propriétés à connaître avant de s'appuyer dessus :

| | |
| --- | --- |
| **Granularité** | l'arrêt survient à un point de contrôle, jamais au milieu d'un appel natif. Le gaspillage est borné à **une page**. Mesuré : ~110 s résiduels au lieu de 512 s sur un scan de 4 pages, soit **~78 % évité**. |
| **Document mono-page** | la boucle de pages ne fait qu'un tour : **aucun** point de contrôle pendant l'OCR. L'annulation ne prend effet qu'à la fin. |
| **Latence de détection** | celle de la boucle asyncio, **jusqu'à ~90 s** quand l'OCR natif retient le GIL. |

Aucun événement n'est émis sur annulation : le client est parti, personne n'écoute.

## Flux Symfony — **implémenté**

1. Client → `POST /transcriptions` (multipart) → **`202 { id, status: "queued" }`**.
   Symfony stocke la source dans le stockage objet (`uploads/{jobId}/source.*`), crée un
   `TranscriptionJob` et dispatche `TranscribeMessage{jobId}` — **la clé, jamais les octets**.
2. Worker Messenger (conteneur `api-worker`, process séparé) → relit la source depuis MinIO et
   la POSTe **en multipart** vers `pdf/parse/stream`.
3. Chaque événement est persisté sur le job (écriture throttlée : changement de phase ou
   Δ`pct` ≥ 2) **et** publié sur Mercure, topic `/transcriptions/{id}`.
4. Sur `done` : MusicXML stocké, `Score` créé, `job.status=done` + `scoreId` ; le client ouvre
   `GET /scores/{id}`.

⚠️ Correction par rapport à la cible initialement décrite : **ce n'est pas Python qui télécharge
le fichier.** `omr-service` n'accepte que du multipart et n'a aucun accès au stockage objet —
c'est Symfony qui lit MinIO et pousse les octets. Python reste **sans état** : ni queue, ni base,
ni identifiants de stockage.

Un abonnement SSE ne rejoue pas l'historique : le client fait donc
`GET /transcriptions/{id}` **puis** s'abonne. La ligne en base reste la source de vérité,
Mercure n'est qu'un canal de poussée — c'est aussi ce qui fait survivre un rechargement de page.

Le schéma d'événements ci-dessus **ne change pas** (le champ `code` de `error` est un ajout
additif, cf. plus haut).
