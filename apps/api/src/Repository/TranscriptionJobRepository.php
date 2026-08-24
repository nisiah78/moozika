<?php

declare(strict_types=1);

namespace App\Repository;

use App\Entity\TranscriptionJob;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Doctrine\Persistence\ManagerRegistry;

/**
 * @extends ServiceEntityRepository<TranscriptionJob>
 */
class TranscriptionJobRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, TranscriptionJob::class);
    }

    /**
     * Jobs en cours (queued|running) — ce que le front doit afficher en carte « en cours ».
     *
     * @return list<TranscriptionJob>
     */
    public function findActive(): array
    {
        /** @var list<TranscriptionJob> $jobs */
        $jobs = $this->createQueryBuilder('j')
            ->andWhere('j.status IN (:statuses)')
            ->setParameter('statuses', TranscriptionJob::ACTIVE_STATUSES)
            ->orderBy('j.createdAt', 'DESC')
            ->getQuery()
            ->getResult();

        return $jobs;
    }

    /**
     * Jobs actifs + terminés récemment : le front a besoin des échecs récents pour afficher
     * la notification, pas seulement de ce qui tourne.
     *
     * @return list<TranscriptionJob>
     */
    public function findActiveAndRecent(\DateTimeImmutable $since, int $limit = 50): array
    {
        /** @var list<TranscriptionJob> $jobs */
        $jobs = $this->createQueryBuilder('j')
            ->andWhere('j.status IN (:active) OR j.updatedAt >= :since')
            ->setParameter('active', TranscriptionJob::ACTIVE_STATUSES)
            ->setParameter('since', $since)
            ->orderBy('j.createdAt', 'DESC')
            ->setMaxResults($limit)
            ->getQuery()
            ->getResult();

        return $jobs;
    }

    /**
     * Statut seul, relu depuis la base sans passer par l'identity map.
     *
     * Le handler s'en sert pour constater une annulation decidee par un AUTRE process (la
     * requete HTTP) pendant qu'il streame : `find()` renverrait l'entite deja chargee, donc
     * l'ancien statut.
     */
    public function findStatusById(\Symfony\Component\Uid\Uuid $id): ?string
    {
        $status = $this->createQueryBuilder('j')
            ->select('j.status')
            ->andWhere('j.id = :id')
            ->setParameter('id', $id, 'uuid')
            ->getQuery()
            ->getOneOrNullResult();

        return \is_array($status) ? (string) $status['status'] : null;
    }

    /**
     * Jobs terminés avant une date : matière à purger.
     *
     * `cancelled` est inclus : l'utilisateur a lui-même decide de l'arreter, il n'y a rien
     * a consulter. Les `failed` partent aussi, mais seulement passe le delai de retention.
     *
     * @return list<TranscriptionJob>
     */
    public function findTerminalBefore(\DateTimeImmutable $before): array
    {
        /** @var list<TranscriptionJob> $jobs */
        $jobs = $this->createQueryBuilder('j')
            ->andWhere('j.status NOT IN (:active)')
            ->andWhere('j.updatedAt < :before')
            ->setParameter('active', TranscriptionJob::ACTIVE_STATUSES)
            ->setParameter('before', $before)
            ->getQuery()
            ->getResult();

        return $jobs;
    }

    /**
     * Jobs zombies : marqués `running` mais plus touchés depuis longtemps, typiquement parce
     * que le worker a été tué. Base du nettoyage de l'étape 11.
     *
     * @return list<TranscriptionJob>
     */
    public function findStale(\DateTimeImmutable $before): array
    {
        /** @var list<TranscriptionJob> $jobs */
        $jobs = $this->createQueryBuilder('j')
            ->andWhere('j.status = :running')
            ->andWhere('j.updatedAt < :before')
            ->setParameter('running', TranscriptionJob::STATUS_RUNNING)
            ->setParameter('before', $before)
            ->getQuery()
            ->getResult();

        return $jobs;
    }
}
