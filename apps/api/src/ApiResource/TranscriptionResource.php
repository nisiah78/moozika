<?php

declare(strict_types=1);

namespace App\ApiResource;

use ApiPlatform\Metadata\ApiProperty;
use ApiPlatform\Metadata\ApiResource;
use ApiPlatform\Metadata\Get;
use ApiPlatform\Metadata\GetCollection;
use ApiPlatform\Metadata\Post;
use Symfony\Component\HttpFoundation\Response;

/**
 * Suivi d'une transcription asynchrone.
 *
 * Le POST est en `multipart/form-data` (champs `file`, `tonic` optionnel) et répond 202 : le
 * travail réel se fait dans le worker Messenger, jamais dans le process HTTP — `apps/api`
 * tourne sur `php -S`, mono-worker, une transcription de 30 min y gèlerait toute l'API.
 */
#[ApiResource(
    shortName: 'Transcription',
    routePrefix: '',
    operations: [
        new GetCollection(
            uriTemplate: '/transcriptions',
            provider: \App\State\TranscriptionProvider::class,
            name: 'transcriptions_list',
            output: ['class' => TranscriptionListResponse::class],
            paginationEnabled: false,
            deserialize: false,
        ),
        new Get(
            uriTemplate: '/transcriptions/{id}',
            provider: \App\State\TranscriptionProvider::class,
            name: 'transcriptions_get',
            deserialize: false,
        ),
        new Post(
            uriTemplate: '/transcriptions',
            processor: \App\State\TranscriptionProcessor::class,
            name: 'transcriptions_create',
            status: Response::HTTP_ACCEPTED,
            inputFormats: ['multipart' => ['multipart/form-data']],
            read: false,
            // Le corps est un upload : rien à désérialiser vers ce DTO, le processor lit
            // la requête directement.
            deserialize: false,
        ),
        new Post(
            uriTemplate: '/transcriptions/{id}/cancel',
            processor: \App\State\TranscriptionProcessor::class,
            name: 'transcriptions_cancel',
            // Post repond 201 par defaut : une annulation ne cree rien.
            status: Response::HTTP_OK,
            read: false,
            deserialize: false,
        ),
    ],
)]
final class TranscriptionResource
{
    #[ApiProperty(identifier: true)]
    public ?string $id = null;

    /** queued|running|done|failed|cancelled */
    public ?string $status = null;

    /** detect|ocr|layout|audiveris|convert — null avant démarrage. */
    public ?string $phase = null;

    /**
     * 0-100 tel que rapporté par omr-service.
     *
     * Le front ne doit PAS l'afficher tel quel pendant la phase `audiveris` : la valeur y
     * reste bloquée à 20 pendant 15-30 min, ce qui fait passer un traitement sain pour un
     * plantage. Barre indéterminée + libellé de phase dans ce cas.
     */
    public ?int $pct = null;

    public ?string $message = null;
    public ?string $sourceFilename = null;
    public ?string $tonic = null;

    /** Code stable de la taxonomie d'erreurs, pour un libellé traduisible côté front. */
    public ?string $errorCode = null;

    /** Message DESTINÉ À L'AFFICHAGE. C'est celui-ci que l'UI doit montrer. */
    public ?string $errorMessage = null;

    /**
     * Détail technique brut, pour un « voir les détails » replié — JAMAIS le message principal.
     * En pratique il contient parfois un dump des logs Java d'Audiveris.
     */
    public ?string $errorDetail = null;

    /** Renseigné au succès : c'est ce qui rend la carte cliquable. */
    public ?string $scoreId = null;

    public ?string $createdAt = null;
    public ?string $updatedAt = null;
}

/**
 * Wrapper de GET /transcriptions — même convention `{ items: [...] }` que GET /scores.
 */
final class TranscriptionListResponse
{
    /** @var list<TranscriptionResource> */
    public array $items = [];
}
