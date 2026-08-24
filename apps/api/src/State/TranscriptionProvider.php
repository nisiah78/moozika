<?php

declare(strict_types=1);

namespace App\State;

use ApiPlatform\Metadata\Operation;
use ApiPlatform\State\ProviderInterface;
use App\ApiResource\TranscriptionListResponse;
use App\ApiResource\TranscriptionResource;
use App\Entity\TranscriptionJob;
use App\Service\TranscriptionService;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;

/**
 * Couche de lecture des endpoints de transcription.
 *
 * @implements ProviderInterface<TranscriptionResource|TranscriptionListResponse>
 */
final class TranscriptionProvider implements ProviderInterface
{
    public function __construct(
        private readonly TranscriptionService $transcriptions,
    ) {
    }

    /**
     * @return TranscriptionResource|TranscriptionListResponse
     */
    public function provide(Operation $operation, array $uriVariables = [], array $context = []): object
    {
        $name = $operation->getName();

        return match ($name) {
            'transcriptions_list' => $this->provideList(),
            'transcriptions_get' => $this->provideGet($uriVariables['id'] ?? null),
            default => throw new \RuntimeException(sprintf('Unknown Transcription operation: %s', (string) $name)),
        };
    }

    /**
     * Transforme un job en représentation API. Statique et publique : le processor renvoie
     * exactement la même forme, une divergence entre les deux ferait vaciller le front.
     */
    public static function toResource(TranscriptionJob $job): TranscriptionResource
    {
        $resource = new TranscriptionResource();
        $resource->id = $job->getId()->toRfc4122();
        $resource->status = $job->getStatus();
        $resource->phase = $job->getPhase();
        $resource->pct = $job->getPct();
        $resource->message = $job->getMessage();
        $resource->sourceFilename = $job->getSourceFilename();
        $resource->tonic = $job->getTonic();
        $resource->errorCode = $job->getErrorCode();
        $resource->errorMessage = $job->getErrorMessage();
        $resource->errorDetail = $job->getErrorDetail();
        $resource->scoreId = $job->getScore()?->getId()->toRfc4122();
        $resource->createdAt = $job->getCreatedAt()->format(\DateTimeInterface::ATOM);
        $resource->updatedAt = $job->getUpdatedAt()->format(\DateTimeInterface::ATOM);

        return $resource;
    }

    private function provideList(): TranscriptionListResponse
    {
        $response = new TranscriptionListResponse();
        $response->items = array_map(
            static fn (TranscriptionJob $job): TranscriptionResource => self::toResource($job),
            $this->transcriptions->listActiveAndRecent()
        );

        return $response;
    }

    private function provideGet(mixed $id): TranscriptionResource
    {
        $job = null === $id ? null : $this->transcriptions->get((string) $id);

        if (null === $job) {
            throw new NotFoundHttpException('Transcription introuvable');
        }

        return self::toResource($job);
    }
}
