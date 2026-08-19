<?php

declare(strict_types=1);

namespace App\ApiResource;

use ApiPlatform\Metadata\ApiProperty;
use ApiPlatform\Metadata\ApiResource;
use ApiPlatform\Metadata\Delete;
use ApiPlatform\Metadata\Get;
use ApiPlatform\Metadata\GetCollection;
use ApiPlatform\Metadata\Post;
use ApiPlatform\Metadata\Operation;
use Symfony\Component\HttpFoundation\Response;

/**
 * DTO exposé par API Platform for "score" endpoints.
 *
 * Note: the real persistence is in {@see \App\Service\ScoreService}; we use custom providers/processors.
 */
#[ApiResource(
    shortName: 'Score',
    routePrefix: '',
    operations: [
        new GetCollection(
            uriTemplate: '/scores',
            provider: \App\State\ScoreProvider::class,
            name: 'scores_list',
            output: ['class' => ScoreListResponse::class],
            paginationEnabled: false,
            read: false,
            deserialize: false,
        ),
        new Get(
            uriTemplate: '/scores/{id}',
            provider: \App\State\ScoreProvider::class,
            name: 'scores_get',
            read: false,
            deserialize: false,
        ),
        new Post(
            uriTemplate: '/scores',
            processor: \App\State\ScoreProcessor::class,
            name: 'scores_create',
            status: Response::HTTP_CREATED,
            read: false,
            deserialize: true,
        ),
        new Delete(
            uriTemplate: '/scores/{id}',
            processor: \App\State\ScoreProcessor::class,
            name: 'scores_delete',
            status: Response::HTTP_NO_CONTENT,
            read: false,
            deserialize: false,
            serialize: false,
        ),
        new Post(
            uriTemplate: '/scores/{id}/versions',
            processor: \App\State\ScoreProcessor::class,
            name: 'scores_add_version',
            status: Response::HTTP_CREATED,
            read: false,
            deserialize: true,
        ),
    ],
)]
final class ScoreResource
{
    #[ApiProperty(identifier: true)]
    public ?string $id = null;

    public ?string $title = null;
    public ?string $tonic = null;
    public ?string $sourceType = null;
    public ?string $status = null;

    public ?int $version = null;

    public ?string $updatedAt = null;
    public ?string $createdAt = null;

    // Included only by GET /scores/{id} (and omitted for list/create/addVersion)
    public ?array $header = null;
    public ?array $voices = null;
    public ?string $musicxml = null;
    public ?string $source = null;
    public ?array $warnings = null;

    // Included only by POST /scores/{id}/versions (and omitted for list/get/create)
    public ?string $origin = null;

    // Input-only (POST /scores, POST /scores/{id}/versions)
    public mixed $model = null;
}

/**
 * Wrapper returned by GET /scores (frontend expects `{ items: [...] }`).
 */
final class ScoreListResponse
{
    /** @var list<ScoreListItem> */
    public array $items = [];
}

/**
 * Element returned in GET /scores.items.
 */
final class ScoreListItem
{
    public ?string $id = null;
    public ?string $title = null;
    public ?string $tonic = null;
    public ?string $sourceType = null;
    public ?string $status = null;
    public ?int $version = null;
    public ?string $updatedAt = null;
    public ?string $createdAt = null;
}

