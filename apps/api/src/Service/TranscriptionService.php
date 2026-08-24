<?php

declare(strict_types=1);

namespace App\Service;

use App\Entity\TranscriptionJob;
use App\Message\TranscribeMessage;
use App\Repository\TranscriptionJobRepository;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\HttpFoundation\File\UploadedFile;
use Symfony\Component\Messenger\MessageBusInterface;

/**
 * Cycle de vie des jobs de transcription. Symfony orchestre, Python ne fait que reconnaître :
 * ce service est le seul endroit qui écrit un job en base et le met en file.
 */
class TranscriptionService
{
    /** Types acceptés en entrée — ce que `omr-service` sait traiter (PDF ou image). */
    private const ALLOWED_MIMES = [
        'application/pdf',
        'image/png',
        'image/jpeg',
        'image/webp',
        'image/tiff',
    ];

    /** Fenêtre de « récents » pour la liste : les échecs doivent rester visibles un moment. */
    private const RECENT_WINDOW = '-24 hours';

    public function __construct(
        private readonly EntityManagerInterface $em,
        private readonly TranscriptionJobRepository $jobs,
        private readonly ObjectStorage $storage,
        private readonly MessageBusInterface $bus,
        private readonly TranscriptionPublisher $publisher,
    ) {
    }

    /**
     * Crée le job, stocke la source, puis met en file — dans cet ordre.
     *
     * L'ordre n'est pas cosmétique : le message ne porte que le jobId, donc le worker doit
     * pouvoir lire la ligne ET la source dès qu'il consomme. Dispatcher avant le flush
     * ouvrirait une fenêtre où le worker cherche un job qui n'existe pas encore.
     */
    public function create(UploadedFile $file, ?string $tonic): TranscriptionJob
    {
        $this->assertUploadUsable($file);

        $filename = $file->getClientOriginalName();
        $mime = $file->getClientMimeType();

        if (!\in_array($mime, self::ALLOWED_MIMES, true)) {
            throw new \InvalidArgumentException(sprintf('Type de fichier non supporté (%s). Formats acceptés : PDF, PNG, JPEG, WebP, TIFF.', '' === $mime ? 'inconnu' : $mime));
        }

        $body = (string) file_get_contents($file->getPathname());
        if ('' === $body) {
            throw new \InvalidArgumentException('Le fichier envoyé est vide.');
        }

        $job = new TranscriptionJob();
        $job->setSourceFilename('' !== $filename ? $filename : 'partition')
            ->setSourceMime($mime)
            ->setTonic('' === (string) $tonic ? null : $tonic);

        $key = $this->storage->putSource($job->getId()->toRfc4122(), $job->getSourceFilename(), $body, $mime);
        $job->setSourceKey($key);

        $this->em->persist($job);
        $this->em->flush();

        // Si le dispatch échoue ici, le job reste `queued` sans consommateur : c'est
        // précisément ce que le nettoyage des jobs zombies (findStale) doit rattraper.
        $this->bus->dispatch(new TranscribeMessage($job->getId()->toRfc4122()));

        return $job;
    }

    public function get(string $id): ?TranscriptionJob
    {
        $uuid = $this->parseUuid($id);

        return null === $uuid ? null : $this->jobs->find($uuid);
    }

    /**
     * @return list<TranscriptionJob>
     */
    public function listActiveAndRecent(): array
    {
        return $this->jobs->findActiveAndRecent(new \DateTimeImmutable(self::RECENT_WINDOW));
    }

    /**
     * Annulation coopérative : on ne peut pas tuer un handler Messenger de l'extérieur, donc
     * on marque l'intention et le worker la constate entre deux événements du flux SSE.
     *
     * @throws \DomainException si le job est déjà dans un état terminal
     */
    public function cancel(TranscriptionJob $job): TranscriptionJob
    {
        if (!$job->isActive()) {
            throw new \DomainException(sprintf('Ce job est déjà terminé (%s), il n\'y a plus rien à annuler.', $job->getStatus()));
        }

        $job->setStatus(TranscriptionJob::STATUS_CANCELLED)
            ->setMessage('Annulé à la demande.')
            ->bumpUpdatedAt();
        $this->em->flush();

        // Seule transition d'état qui ne vient pas du worker : c'est donc ici qu'elle doit
        // être publiée, sinon les autres onglets ne la verraient jamais.
        $this->publisher->publish($job);

        return $job;
    }

    /** Purge la source : transitoire par nature, à jeter dès que le job est terminé. */
    public function discardSource(TranscriptionJob $job): void
    {
        if ('' === $job->getSourceKey()) {
            return;
        }

        try {
            $this->storage->delete($job->getSourceKey());
        } catch (\Throwable) {
            // Un objet orphelin dans le bucket ne doit pas faire échouer un job réussi.
        }
    }

    /**
     * Traduit les codes d'erreur d'upload PHP en messages compréhensibles. Sans ça, un PDF
     * trop gros arrive comme un fichier « absent », ce qui envoie chercher au mauvais endroit.
     */
    private function assertUploadUsable(UploadedFile $file): void
    {
        if ($file->isValid()) {
            return;
        }

        throw new \InvalidArgumentException(match ($file->getError()) {
            \UPLOAD_ERR_INI_SIZE, \UPLOAD_ERR_FORM_SIZE => sprintf('Fichier trop volumineux (limite serveur : %s).', (string) \ini_get('upload_max_filesize')), \UPLOAD_ERR_PARTIAL => 'Envoi interrompu : le fichier n\'est arrivé qu\'en partie.', \UPLOAD_ERR_NO_FILE => 'Aucun fichier reçu.', default => sprintf('Échec de l\'envoi du fichier (code %d).', $file->getError()),
        });
    }

    private function parseUuid(string $id): ?\Symfony\Component\Uid\Uuid
    {
        try {
            return \Symfony\Component\Uid\Uuid::fromString($id);
        } catch (\Throwable) {
            return null;
        }
    }
}
