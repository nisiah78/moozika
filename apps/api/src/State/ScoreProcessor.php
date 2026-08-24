<?php

declare(strict_types=1);

namespace App\State;

use ApiPlatform\Metadata\Operation;
use ApiPlatform\State\ProcessorInterface;
use App\ApiResource\ScoreResource;
use App\Service\ScoreService;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;
use Symfony\Component\HttpKernel\Exception\UnprocessableEntityHttpException;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Symfony\Component\HttpFoundation\Response;

/**
 * Custom write layer for Score endpoints.
 *
 * This replaces the orchestration formerly done in `ScoreController`.
 */
final class ScoreProcessor implements ProcessorInterface
{
    public function __construct(
        private readonly ScoreService $scores,
    ) {
    }

    public function process(mixed $data, Operation $operation, array $uriVariables = [], array $context = []): mixed
    {
        $name = $operation->getName();

        return match ($name) {
            'scores_create' => $this->processCreate($data),
            'scores_add_version' => $this->processAddVersion($data, $uriVariables['id'] ?? null),
            'scores_delete' => $this->processDelete($uriVariables['id'] ?? null),
            default => throw new \RuntimeException(sprintf('Unknown Score operation: %s', (string) $name)),
        };
    }

    private function processCreate(mixed $data): ScoreResource
    {
        if (!$data instanceof ScoreResource) {
            throw new \InvalidArgumentException('Invalid request payload');
        }

        $payload = [
            'title' => $data->title,
            'tonic' => $data->tonic,
            'sourceType' => $data->sourceType,
            'origin' => $data->origin,
            'musicxml' => (string) ($data->musicxml ?? ''),
            'model' => $data->model,
        ];

        try {
            $score = $this->scores->create($payload);
            $latest = $this->scores->latestVersion($score);
        } catch (\InvalidArgumentException $e) {
            throw new UnprocessableEntityHttpException($e->getMessage());
        } catch (\Throwable $e) {
            throw new HttpException(Response::HTTP_BAD_GATEWAY, $e->getMessage());
        }

        return $this->buildCreateResponse($score, $latest?->getNumber() ?? 1);
    }

    private function processAddVersion(mixed $data, mixed $id): ScoreResource
    {
        if (null === $id) {
            throw new NotFoundHttpException('Partition introuvable');
        }
        if (!$data instanceof ScoreResource) {
            throw new \InvalidArgumentException('Invalid request payload');
        }

        try {
            $score = $this->scores->get((string) $id);
        } catch (\InvalidArgumentException) {
            throw new NotFoundHttpException('Partition introuvable');
        }

        if (null === $score) {
            throw new NotFoundHttpException('Partition introuvable');
        }

        $payload = [
            'title' => $data->title,
            'tonic' => $data->tonic,
            'origin' => $data->origin,
            'musicxml' => (string) ($data->musicxml ?? ''),
            'model' => $data->model,
        ];

        try {
            $version = $this->scores->addVersion($score, $payload);
        } catch (\InvalidArgumentException $e) {
            throw new UnprocessableEntityHttpException($e->getMessage());
        } catch (\Throwable $e) {
            throw new HttpException(Response::HTTP_BAD_GATEWAY, $e->getMessage());
        }

        $resource = new ScoreResource();
        $resource->id = $score->getId()->toRfc4122();
        $resource->version = $version->getNumber();
        $resource->origin = $version->getOrigin();
        $resource->updatedAt = $score->getUpdatedAt()->format(\DateTimeInterface::ATOM);

        return $resource;
    }

    private function processDelete(mixed $id): null
    {
        if (null === $id) {
            throw new NotFoundHttpException('Partition introuvable');
        }

        try {
            $score = $this->scores->get((string) $id);
        } catch (\InvalidArgumentException) {
            throw new NotFoundHttpException('Partition introuvable');
        }

        if (null === $score) {
            throw new NotFoundHttpException('Partition introuvable');
        }

        try {
            $this->scores->delete($score);
        } catch (\Throwable $e) {
            throw new HttpException(Response::HTTP_BAD_GATEWAY, $e->getMessage());
        }

        return null;
    }

    private function buildCreateResponse(\App\Entity\Score $score, int $versionNumber): ScoreResource
    {
        $resource = new ScoreResource();
        $resource->id = $score->getId()->toRfc4122();
        $resource->title = $score->getTitle();
        $resource->tonic = $score->getTonic();
        $resource->sourceType = $score->getSourceType();
        $resource->version = $versionNumber;
        $resource->updatedAt = $score->getUpdatedAt()->format(\DateTimeInterface::ATOM);

        return $resource;
    }
}
