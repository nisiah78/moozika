<?php

declare(strict_types=1);

namespace App\MessageHandler;

use App\Entity\TranscriptionJob;
use App\Message\TranscribeMessage;
use App\Repository\TranscriptionJobRepository;
use App\Service\ObjectStorage;
use App\Service\OmrClient;
use App\Service\ScoreService;
use App\Service\TranscriptionError;
use App\Service\TranscriptionPublisher;
use App\Service\TranscriptionService;
use Doctrine\ORM\EntityManagerInterface;
use Psr\Log\LoggerInterface;
use Symfony\Component\Messenger\Attribute\AsMessageHandler;
use Symfony\Component\Messenger\Exception\UnrecoverableMessageHandlingException;
use Symfony\Component\Uid\Uuid;

/**
 * Exécute une transcription : lit la source, streame omr-service, persiste l'avancement,
 * et crée le Score au succès.
 *
 * Tourne dans le conteneur `api-worker`, jamais dans le process HTTP : `apps/api` est servi
 * par `php -S` (mono-worker), une transcription de 30 min y gèlerait toute l'API.
 */
#[AsMessageHandler]
final class TranscribeMessageHandler
{
    /** Écrire à chaque événement ferait ~1 requête/100 ms en phase OCR pour rien. */
    private const PCT_WRITE_THRESHOLD = 2;

    /** Fréquence de relecture du statut, qui sert aussi à ne pas laisser la connexion oisive. */
    private const CANCEL_CHECK_INTERVAL = 3.0;

    public function __construct(
        private readonly EntityManagerInterface $em,
        private readonly TranscriptionJobRepository $jobs,
        private readonly ObjectStorage $storage,
        private readonly OmrClient $omr,
        private readonly ScoreService $scores,
        private readonly TranscriptionService $transcriptions,
        private readonly TranscriptionPublisher $publisher,
        private readonly LoggerInterface $logger,
    ) {
    }

    public function __invoke(TranscribeMessage $message): void
    {
        $job = $this->loadJob($message->jobId);

        // Idempotence : un rejeu (retry Messenger, message redélivré) ne doit jamais relancer
        // une transcription déjà réglée, ni créer un second Score.
        if (!$job->isActive()) {
            $this->logger->info('Transcription {id} déjà terminée ({status}), rien à faire.', [
                'id' => $message->jobId,
                'status' => $job->getStatus(),
            ]);

            return;
        }

        // N1, cas `queued` : annulé avant même d'être pris en charge.
        if ($job->isCancelled()) {
            $this->transcriptions->discardSource($job);

            return;
        }

        $source = $this->readSource($job);

        $job->setStatus(TranscriptionJob::STATUS_RUNNING)
            ->setPhase('detect')
            ->setMessage('Démarrage de la transcription…')
            ->bumpUpdatedAt();
        $this->em->flush();
        $this->publisher->publish($job);

        $outcome = $this->runStream($job, $source);

        $this->finish($job, $outcome);
    }

    /**
     * Consomme le flux SSE et renvoie ce qui s'est passé.
     *
     * @return array{cancelled: bool, result: array<string, mixed>|null, error: string|null, errorCode: string|null}
     */
    private function runStream(TranscriptionJob $job, string $source): array
    {
        $lastPct = -100;
        $lastPhase = null;
        $lastCancelCheck = microtime(true);
        $cancelled = false;
        $result = null;
        $error = null;
        $errorCode = null;

        $this->omr->parsePdfStream(
            $source,
            $job->getSourceFilename(),
            $job->getSourceMime(),
            $job->getTonic(),
            function (string $event, array $data) use (
                $job,
                &$lastPct,
                &$lastPhase,
                &$lastCancelCheck,
                &$cancelled,
                &$result,
                &$error,
                &$errorCode
            ): bool {
                switch ($event) {
                    case 'done':
                        $raw = $data['result'] ?? null;
                        $result = \is_array($raw) ? $raw : [];

                        return false;

                    case 'error':
                        $error = \is_string($data['detail'] ?? null) ? $data['detail'] : 'Erreur inconnue';
                        // omr-service n'emet pas encore de code structure ; on le lit deja
                        // pour que l'ajouter cote Python soit purement additif.
                        $errorCode = \is_string($data['code'] ?? null) ? $data['code'] : null;

                        return false;

                    case 'progress':
                        $phase = \is_string($data['phase'] ?? null) ? $data['phase'] : null;
                        // `pct` arrive tantôt entier, tantôt flottant (mesuré : 78.75 en phase
                        // `convert`). En strict_types, le passer brut à setPct(int) leverait.
                        $pct = (int) round((float) ($data['pct'] ?? 0));

                        if ($phase !== $lastPhase || abs($pct - $lastPct) >= self::PCT_WRITE_THRESHOLD) {
                            $job->setPhase($phase)
                                ->setPct($pct)
                                ->setMessage(\is_string($data['message'] ?? null) ? $data['message'] : null)
                                ->bumpUpdatedAt();
                            $this->em->flush();
                            // Publie exactement quand on persiste : le throttle sert donc
                            // aussi de limiteur de debit vers le hub.
                            $this->publisher->publish($job);
                            $lastPhase = $phase;
                            $lastPct = $pct;
                        }
                        break;

                    case 'voice':
                    case 'ping':
                        // Rien à persister. Le `ping` existe pour que la boucle continue de
                        // tourner pendant la phase `audiveris`, muette 15-30 min.
                        break;
                }

                if (microtime(true) - $lastCancelCheck >= self::CANCEL_CHECK_INTERVAL) {
                    $lastCancelCheck = microtime(true);
                    if (TranscriptionJob::STATUS_CANCELLED === $this->jobs->findStatusById($job->getId())) {
                        $cancelled = true;

                        return false;
                    }
                }

                return true;
            }
        );

        return ['cancelled' => $cancelled, 'result' => $result, 'error' => $error, 'errorCode' => $errorCode];
    }

    /**
     * @param array{cancelled: bool, result: array<string, mixed>|null, error: string|null, errorCode: string|null} $outcome
     */
    private function finish(TranscriptionJob $job, array $outcome): void
    {
        if ($outcome['cancelled']) {
            // Le statut `cancelled` a déjà été posé par la requête HTTP ; on ne l'écrase pas.
            $this->em->refresh($job);
            $this->transcriptions->discardSource($job);
            $this->publisher->publish($job);

            return;
        }

        if (null !== $outcome['error']) {
            $classified = TranscriptionError::fromDetail($outcome['error'], $outcome['errorCode']);

            // Une panne d'infrastructure n'est PAS un échec de la partition : on laisse le job
            // en `running` et on relance l'exception pour que Messenger retente. Le marquer
            // `failed` ici condamnerait un job qu'un simple redémarrage aurait sauvé (et la
            // garde d'idempotence ferait alors sauter le retry).
            if ($classified->retryable) {
                $this->logger->warning('Transcription {id} : incident transitoire ({code}) — retry. {detail}', [
                    'id' => $job->getId()->toRfc4122(),
                    'code' => $classified->code,
                    'detail' => $classified->rawDetail,
                ]);

                throw new \RuntimeException(sprintf('%s (%s)', $classified->userMessage, $classified->code));
            }

            $this->fail($job, $classified->code, $classified->userMessage, $classified->rawDetail);

            return;
        }

        if (null === $outcome['result']) {
            // Flux clos sans `done` ni `error` : anormal, et il ne faut PAS laisser le job
            // en `running` pour toujours. Non retentable volontairement : si omr-service
            // plante systématiquement sur ce document, retenter coûte 30 min pour rien.
            $this->fail(
                $job,
                'stream_incomplete',
                'La reconnaissance s\'est interrompue avant d\'avoir produit un résultat.',
                'flux SSE clos sans événement done ni error'
            );

            return;
        }

        $this->succeed($job, $outcome['result']);
    }

    /**
     * @param array<string, mixed> $result
     */
    private function succeed(TranscriptionJob $job, array $result): void
    {
        $musicxml = \is_string($result['musicxml'] ?? null) ? $result['musicxml'] : '';
        if ('' === $musicxml) {
            $this->fail(
                $job,
                TranscriptionError::CODE_NO_NOTATION,
                'Aucune notation musicale n\'a pu être reconnue dans ce document.',
                'événement done reçu avec un musicxml vide'
            );

            return;
        }

        // Garde d'idempotence : si un rejeu survient après création du Score mais avant le
        // flush du statut, on ne recrée pas une seconde partition.
        if (null === $job->getScore()) {
            $score = $this->scores->create([
                'title' => $this->deriveTitle($job, $result),
                'tonic' => $this->deriveTonic($job, $result),
                'sourceType' => $this->deriveSourceType($result),
                'origin' => 'omr',
                'musicxml' => $musicxml,
                // Ce que `loadLatestPayload` relira : header/voices/source/warnings. Le
                // musicxml est retiré, il vit dans le stockage objet — le garder ici le
                // stockerait deux fois.
                'model' => $this->buildModel($result),
            ]);
            $job->setScore($score);
        }

        $job->setStatus(TranscriptionJob::STATUS_DONE)
            ->setPhase(null)
            ->setPct(100)
            ->setMessage('Transcription terminée.')
            ->bumpUpdatedAt();
        $this->em->flush();
        $this->publisher->publish($job);

        $this->transcriptions->discardSource($job);
    }

    private function fail(TranscriptionJob $job, string $code, string $userMessage, ?string $detail = null): void
    {
        $job->setStatus(TranscriptionJob::STATUS_FAILED)
            ->setError($code, $userMessage, $detail)
            ->setMessage('Échec de la transcription.')
            ->bumpUpdatedAt();
        $this->em->flush();
        $this->publisher->publish($job);

        $this->transcriptions->discardSource($job);

        $this->logger->warning('Transcription {id} en échec ({code}) : {message} | brut: {detail}', [
            'id' => $job->getId()->toRfc4122(),
            'code' => $code,
            'message' => $userMessage,
            'detail' => $detail ?? '-',
        ]);
    }

    /**
     * @param array<string, mixed> $result
     *
     * @return array<string, mixed>
     */
    private function buildModel(array $result): array
    {
        $model = $result;
        unset($model['musicxml']);

        return $model;
    }

    /** @param array<string, mixed> $result */
    private function deriveTitle(TranscriptionJob $job, array $result): string
    {
        $header = \is_array($result['header'] ?? null) ? $result['header'] : [];
        $title = trim((string) ($header['title'] ?? ''));

        if ('' !== $title) {
            return $title;
        }

        // Repli sur le nom de fichier sans extension : plus parlant que « Sans titre ».
        $base = pathinfo($job->getSourceFilename(), \PATHINFO_FILENAME);

        return '' !== $base ? $base : 'Sans titre';
    }

    /** @param array<string, mixed> $result */
    private function deriveTonic(TranscriptionJob $job, array $result): string
    {
        // La tonique demandée par l'utilisateur prime : en sol-fa tonique elle est une
        // métadonnée hors notation, jamais devinée depuis les syllabes.
        if (null !== $job->getTonic() && '' !== $job->getTonic()) {
            return $job->getTonic();
        }

        $header = \is_array($result['header'] ?? null) ? $result['header'] : [];
        $tonic = trim((string) ($header['tonic'] ?? ''));

        return '' !== $tonic ? $tonic : 'C';
    }

    /**
     * Même correspondance que le front (`page.tsx`) : la source technique du pipeline
     * devient le type métier de la partition.
     *
     * @param array<string, mixed> $result
     */
    private function deriveSourceType(array $result): string
    {
        return match ($result['source'] ?? null) {
            'audiveris' => 'staff',
            'solfa_pdf' => 'solfa',
            default => 'musicxml',
        };
    }

    private function loadJob(string $jobId): TranscriptionJob
    {
        try {
            $uuid = Uuid::fromString($jobId);
        } catch (\Throwable) {
            throw new UnrecoverableMessageHandlingException(sprintf('Identifiant de job invalide : %s', $jobId));
        }

        $job = $this->jobs->find($uuid);
        if (null === $job) {
            // Rien à retenter : le job a été supprimé.
            throw new UnrecoverableMessageHandlingException(sprintf('Job de transcription introuvable : %s', $jobId));
        }

        return $job;
    }

    private function readSource(TranscriptionJob $job): string
    {
        try {
            $source = $this->storage->get($job->getSourceKey());
        } catch (\Throwable $e) {
            $this->fail(
                $job,
                'source_missing',
                'Le fichier envoyé est introuvable : il a peut-être été supprimé entre-temps.',
                $e->getMessage()
            );

            throw new UnrecoverableMessageHandlingException(sprintf('Source illisible pour le job %s : %s', $job->getId()->toRfc4122(), $e->getMessage()), previous: $e);
        }

        return $source;
    }
}
