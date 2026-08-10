<?php

declare(strict_types=1);

namespace App\Repository;

use App\Entity\Score;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Doctrine\Persistence\ManagerRegistry;
use Symfony\Component\Uid\Uuid;

/**
 * @extends ServiceEntityRepository<Score>
 */
class ScoreRepository extends ServiceEntityRepository
{
    public function __construct(ManagerRegistry $registry)
    {
        parent::__construct($registry, Score::class);
    }

    /**
     * Métadonnées de liste sans hydrater model_json des versions (évite OOM).
     *
     * @return list<array{
     *   id: Uuid,
     *   title: string,
     *   tonic: string,
     *   sourceType: string,
     *   status: string,
     *   updatedAt: \DateTimeImmutable,
     *   createdAt: \DateTimeImmutable,
     *   version: int
     * }>
     */
    public function findListItemsNewestFirst(): array
    {
        $rows = $this->createQueryBuilder('s')
            ->select(
                's.id AS id',
                's.title AS title',
                's.tonic AS tonic',
                's.sourceType AS sourceType',
                's.status AS status',
                's.updatedAt AS updatedAt',
                's.createdAt AS createdAt',
                '(SELECT MAX(v.number) FROM App\Entity\ScoreVersion v WHERE v.score = s) AS version',
            )
            ->orderBy('s.updatedAt', 'DESC')
            ->getQuery()
            ->getArrayResult();

        $items = [];
        foreach ($rows as $row) {
            $items[] = [
                'id' => $row['id'],
                'title' => (string) $row['title'],
                'tonic' => (string) $row['tonic'],
                'sourceType' => (string) $row['sourceType'],
                'status' => (string) $row['status'],
                'updatedAt' => $row['updatedAt'],
                'createdAt' => $row['createdAt'],
                'version' => (int) ($row['version'] ?? 0),
            ];
        }

        return $items;
    }

    public function findOneById(Uuid|string $id): ?Score
    {
        $uuid = $id instanceof Uuid ? $id : Uuid::fromString((string) $id);

        return $this->find($uuid);
    }
}
