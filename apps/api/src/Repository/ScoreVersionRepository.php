<?php

declare(strict_types=1);

namespace App\Repository;

use App\Entity\Score;
use App\Entity\ScoreVersion;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Doctrine\Persistence\ManagerRegistry;

/**
 * @extends ServiceEntityRepository<ScoreVersion>
 */
class ScoreVersionRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, ScoreVersion::class);
    }

    public function findLatestForScore(Score $score): ?ScoreVersion
    {
        return $this->createQueryBuilder('v')
            ->andWhere('v.score = :score')
            ->setParameter('score', $score)
            ->orderBy('v.number', 'DESC')
            ->setMaxResults(1)
            ->getQuery()
            ->getOneOrNullResult();
    }

    public function findMaxNumberForScore(Score $score): int
    {
        $max = $this->createQueryBuilder('v')
            ->select('MAX(v.number)')
            ->andWhere('v.score = :score')
            ->setParameter('score', $score)
            ->getQuery()
            ->getSingleScalarResult();

        return (int) ($max ?? 0);
    }
}
