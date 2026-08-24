<?php

declare(strict_types=1);

namespace App\Service;

use App\Entity\TranscriptionJob;
use App\State\TranscriptionProvider;
use Psr\Log\LoggerInterface;
use Symfony\Component\Mercure\HubInterface;
use Symfony\Component\Mercure\Update;
use Symfony\Component\Serializer\SerializerInterface;

/**
 * Pousse l'état d'un job vers le hub Mercure.
 *
 * Règle : **qui change l'état le publie**. Le handler pour toutes les transitions du worker,
 * `TranscriptionService::cancel()` pour la seule qui se produit hors du worker.
 *
 * La sérialisation passe par le MÊME DTO que l'API (`TranscriptionProvider::toResource`) :
 * le navigateur reçoit donc exactement la forme qu'il obtient en `GET /transcriptions/{id}`,
 * et il n'y a pas deux représentations à maintenir en phase.
 */
class TranscriptionPublisher
{
    public function __construct(
        private readonly HubInterface $hub,
        private readonly SerializerInterface $serializer,
        private readonly LoggerInterface $logger,
    ) {
    }

    public static function topicFor(TranscriptionJob $job): string
    {
        return '/transcriptions/'.$job->getId()->toRfc4122();
    }

    public function publish(TranscriptionJob $job): void
    {
        try {
            $payload = $this->serializer->serialize(
                TranscriptionProvider::toResource($job),
                'json',
                // Même convention que l'API Platform : les champs nuls sont omis, pas
                // sérialisés à null. Le front les type donc optionnels.
                ['skip_null_values' => true]
            );

            $this->hub->publish(new Update(self::topicFor($job), $payload));
        } catch (\Throwable $e) {
            // Une panne du hub ne doit JAMAIS faire échouer une transcription de 30 min :
            // Mercure n'est qu'un canal de poussée, la base reste la source de vérité et le
            // front sait relire l'état par GET.
            $this->logger->warning('Publication Mercure impossible pour {id} : {err}', [
                'id' => $job->getId()->toRfc4122(),
                'err' => $e->getMessage(),
            ]);
        }
    }
}
