<?php

declare(strict_types=1);

namespace App\State;

use ApiPlatform\Metadata\Operation;
use ApiPlatform\State\ProcessorInterface;
use App\ApiResource\TranscriptionResource;
use App\Service\TranscriptionService;
use Symfony\Component\HttpFoundation\File\UploadedFile;
use Symfony\Component\HttpFoundation\RequestStack;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\HttpKernel\Exception\ConflictHttpException;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;
use Symfony\Component\HttpKernel\Exception\UnprocessableEntityHttpException;

/**
 * Couche d'écriture des endpoints de transcription.
 *
 * @implements ProcessorInterface<mixed, TranscriptionResource>
 */
final class TranscriptionProcessor implements ProcessorInterface
{
    public function __construct(
        private readonly TranscriptionService $transcriptions,
        private readonly RequestStack $requests,
    ) {
    }

    public function process(mixed $data, Operation $operation, array $uriVariables = [], array $context = []): mixed
    {
        $name = $operation->getName();

        return match ($name) {
            'transcriptions_create' => $this->processCreate(),
            'transcriptions_cancel' => $this->processCancel($uriVariables['id'] ?? null),
            default => throw new \RuntimeException(sprintf('Unknown Transcription operation: %s', (string) $name)),
        };
    }

    private function processCreate(): TranscriptionResource
    {
        // L'upload se lit sur la requête : `deserialize: false` sur l'opération, donc rien
        // n'est hydraté dans le DTO. RequestStack plutôt que $context['request'] pour ne pas
        // dépendre d'un détail interne d'API Platform.
        $request = $this->requests->getCurrentRequest();
        if (null === $request) {
            throw new HttpException(Response::HTTP_INTERNAL_SERVER_ERROR, 'Requête indisponible');
        }

        $file = $request->files->get('file');
        if (!$file instanceof UploadedFile) {
            throw new UnprocessableEntityHttpException('Aucun fichier reçu. Envoyez un multipart/form-data avec un champ « file ».');
        }

        $tonic = $request->request->get('tonic');

        try {
            $job = $this->transcriptions->create($file, \is_string($tonic) ? $tonic : null);
        } catch (\InvalidArgumentException $e) {
            throw new UnprocessableEntityHttpException($e->getMessage());
        } catch (\Throwable $e) {
            // Stockage objet injoignable ou transport en file indisponible : c'est une panne
            // d'infrastructure, pas une faute du client.
            throw new HttpException(Response::HTTP_BAD_GATEWAY, $e->getMessage());
        }

        return TranscriptionProvider::toResource($job);
    }

    private function processCancel(mixed $id): TranscriptionResource
    {
        $job = null === $id ? null : $this->transcriptions->get((string) $id);

        if (null === $job) {
            throw new NotFoundHttpException('Transcription introuvable');
        }

        try {
            $this->transcriptions->cancel($job);
        } catch (\DomainException $e) {
            throw new ConflictHttpException($e->getMessage());
        } catch (\Throwable $e) {
            throw new HttpException(Response::HTTP_BAD_GATEWAY, $e->getMessage());
        }

        return TranscriptionProvider::toResource($job);
    }
}
