<?php

declare(strict_types=1);

namespace App\Controller;

use App\Service\ScoreService;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[Route('/scores')]
class ScoreController extends AbstractController
{
    public function __construct(
        private readonly ScoreService $scores,
    ) {
    }

    #[Route('', name: 'scores_list', methods: ['GET'])]
    public function list(): JsonResponse
    {
        $items = [];
        foreach ($this->scores->list() as $row) {
            $items[] = [
                'id' => $row['id']->toRfc4122(),
                'title' => $row['title'],
                'tonic' => $row['tonic'],
                'sourceType' => $row['sourceType'],
                'status' => $row['status'],
                'version' => $row['version'],
                'updatedAt' => $row['updatedAt']->format(\DateTimeInterface::ATOM),
                'createdAt' => $row['createdAt']->format(\DateTimeInterface::ATOM),
            ];
        }

        return $this->json(['items' => $items]);
    }

    #[Route('', name: 'scores_create', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        try {
            $payload = $this->jsonBody($request);
            $score = $this->scores->create($payload);
        } catch (\InvalidArgumentException $e) {
            return $this->json(['detail' => $e->getMessage()], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Throwable $e) {
            return $this->json(['detail' => $e->getMessage()], Response::HTTP_BAD_GATEWAY);
        }

        $latest = $this->scores->latestVersion($score);

        return $this->json([
            'id' => $score->getId()->toRfc4122(),
            'title' => $score->getTitle(),
            'tonic' => $score->getTonic(),
            'sourceType' => $score->getSourceType(),
            'version' => $latest?->getNumber() ?? 1,
            'updatedAt' => $score->getUpdatedAt()->format(\DateTimeInterface::ATOM),
        ], Response::HTTP_CREATED);
    }

    #[Route('/{id}', name: 'scores_get', methods: ['GET'])]
    public function get(string $id): JsonResponse
    {
        $score = $this->scores->get($id);
        if ($score === null) {
            return $this->json(['detail' => 'Partition introuvable'], Response::HTTP_NOT_FOUND);
        }

        try {
            $payload = $this->scores->loadLatestPayload($score);
        } catch (\Throwable $e) {
            return $this->json(['detail' => $e->getMessage()], Response::HTTP_BAD_GATEWAY);
        }

        if ($payload === null) {
            return $this->json(['detail' => 'Aucune version'], Response::HTTP_NOT_FOUND);
        }

        $latest = $this->scores->latestVersion($score);

        return $this->json([
            'id' => $score->getId()->toRfc4122(),
            'title' => $score->getTitle(),
            'tonic' => $score->getTonic(),
            'sourceType' => $score->getSourceType(),
            'version' => $latest?->getNumber() ?? 0,
            'updatedAt' => $score->getUpdatedAt()->format(\DateTimeInterface::ATOM),
            'header' => $payload['header'],
            'voices' => $payload['voices'],
            'musicxml' => $payload['musicxml'],
            'source' => $payload['source'] ?? null,
            'warnings' => $payload['warnings'] ?? [],
        ]);
    }

    #[Route('/{id}/versions', name: 'scores_add_version', methods: ['POST'])]
    public function addVersion(string $id, Request $request): JsonResponse
    {
        $score = $this->scores->get($id);
        if ($score === null) {
            return $this->json(['detail' => 'Partition introuvable'], Response::HTTP_NOT_FOUND);
        }

        try {
            $payload = $this->jsonBody($request);
            $version = $this->scores->addVersion($score, $payload);
        } catch (\InvalidArgumentException $e) {
            return $this->json(['detail' => $e->getMessage()], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Throwable $e) {
            return $this->json(['detail' => $e->getMessage()], Response::HTTP_BAD_GATEWAY);
        }

        return $this->json([
            'id' => $score->getId()->toRfc4122(),
            'version' => $version->getNumber(),
            'origin' => $version->getOrigin(),
            'updatedAt' => $score->getUpdatedAt()->format(\DateTimeInterface::ATOM),
        ], Response::HTTP_CREATED);
    }

    /** @return array<string, mixed> */
    private function jsonBody(Request $request): array
    {
        $data = json_decode($request->getContent(), true);
        if (!is_array($data)) {
            throw new \InvalidArgumentException('JSON invalide');
        }

        return $data;
    }
}
