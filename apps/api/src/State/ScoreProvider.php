<?php

declare(strict_types=1);

namespace App\State;

use ApiPlatform\Metadata\Operation;
use ApiPlatform\State\ProviderInterface;
use App\ApiResource\ScoreListItem;
use App\ApiResource\ScoreListResponse;
use App\ApiResource\ScoreResource;
use App\Service\ScoreService;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Symfony\Component\HttpFoundation\Response;

/**
 * Custom read layer for Score endpoints.
 *
 * This replaces the orchestration formerly done in `ScoreController`.
 */
final class ScoreProvider implements ProviderInterface
{
    public function __construct(
        private readonly ScoreService $scores,
    ) {
    }

    public function provide(Operation $operation, array $uriVariables = [], array $context = []): object|array|null
    {
        $name = $operation->getName();

        return match ($name) {
            'scores_list' => $this->provideList(),
            'scores_get' => $this->provideGet($uriVariables['id'] ?? null),
            default => throw new \RuntimeException(sprintf('Unknown Score operation: %s', (string) $name)),
        };
    }

    private function provideList(): ScoreListResponse
    {
        $response = new ScoreListResponse();
        $items = [];

        foreach ($this->scores->list() as $row) {
            $item = new ScoreListItem();
            $item->id = $row['id']->toRfc4122();
            $item->title = $row['title'];
            $item->tonic = $row['tonic'];
            $item->sourceType = $row['sourceType'];
            $item->status = $row['status'];
            $item->version = (int) $row['version'];
            $item->updatedAt = $row['updatedAt']->format(\DateTimeInterface::ATOM);
            $item->createdAt = $row['createdAt']->format(\DateTimeInterface::ATOM);
            $items[] = $item;
        }

        $response->items = $items;

        return $response;
    }

    private function provideGet(?string $id): ScoreResource
    {
        if ($id === null) {
            throw new NotFoundHttpException('Partition introuvable');
        }

        $score = $this->scores->get($id);
        if ($score === null) {
            throw new NotFoundHttpException('Partition introuvable');
        }

        try {
            $payload = $this->scores->loadLatestPayload($score);
        } catch (\Throwable $e) {
            throw new HttpException(Response::HTTP_BAD_GATEWAY, $e->getMessage());
        }

        if ($payload === null) {
            throw new NotFoundHttpException('Aucune version');
        }

        $latest = $this->scores->latestVersion($score);

        $resource = new ScoreResource();
        $resource->id = $score->getId()->toRfc4122();
        $resource->title = $score->getTitle();
        $resource->tonic = $score->getTonic();
        $resource->sourceType = $score->getSourceType();
        $resource->version = $latest?->getNumber() ?? 0;
        $resource->updatedAt = $score->getUpdatedAt()->format(\DateTimeInterface::ATOM);

        $resource->header = $payload['header'];
        $resource->voices = $payload['voices'];
        $resource->musicxml = $payload['musicxml'];
        $resource->source = $payload['source'] ?? null;
        $resource->warnings = $payload['warnings'] ?? [];

        return $resource;
    }
}

