<?php

declare(strict_types=1);

namespace App\Service;

use App\Entity\Score;
use App\Entity\ScoreVersion;
use App\Repository\ScoreRepository;
use App\Repository\ScoreVersionRepository;
use Doctrine\ORM\EntityManagerInterface;
use Doctrine\ORM\PersistentCollection;
use Symfony\Component\Uid\Uuid;

class ScoreService
{
    public function __construct(
        private readonly EntityManagerInterface $em,
        private readonly ScoreRepository $scores,
        private readonly ScoreVersionRepository $versions,
        private readonly ObjectStorage $storage,
    ) {
    }

    /**
     * @param array{title?: string, tonic?: string, sourceType?: string, origin?: string, musicxml: string, model?: array<string, mixed>|null} $payload
     */
    public function create(array $payload): Score
    {
        $musicxml = $payload['musicxml'] ?? '';
        if ($musicxml === '') {
            throw new \InvalidArgumentException('musicxml est requis');
        }

        $score = (new Score())
            ->setTitle(trim((string) ($payload['title'] ?? '')) ?: 'Sans titre')
            ->setTonic(trim((string) ($payload['tonic'] ?? '')) ?: 'C')
            ->setSourceType((string) ($payload['sourceType'] ?? 'solfa'))
            ->setStatus('ready');

        $origin = (string) ($payload['origin'] ?? 'omr');
        $version = $this->buildVersion($score, 1, $origin, $musicxml, $payload['model'] ?? null);
        $score->addVersion($version);

        $this->em->persist($score);
        $this->em->flush();

        return $score;
    }

    /**
     * @param array{title?: string, tonic?: string, origin?: string, musicxml: string, model?: array<string, mixed>|null} $payload
     */
    public function addVersion(Score $score, array $payload): ScoreVersion
    {
        $musicxml = $payload['musicxml'] ?? '';
        if ($musicxml === '') {
            throw new \InvalidArgumentException('musicxml est requis');
        }

        if (isset($payload['title'])) {
            $title = trim((string) $payload['title']);
            if ($title !== '') {
                $score->setTitle($title);
            }
        }
        if (isset($payload['tonic'])) {
            $tonic = trim((string) $payload['tonic']);
            if ($tonic !== '') {
                $score->setTonic($tonic);
            }
        }

        $origin = (string) ($payload['origin'] ?? 'edit');
        $nextNumber = $this->versions->findMaxNumberForScore($score) + 1;
        $version = $this->buildVersion(
            $score,
            $nextNumber,
            $origin,
            $musicxml,
            $payload['model'] ?? null,
        );
        $score->addVersion($version);
        $score->bumpUpdatedAt();

        $this->em->persist($version);
        $this->em->flush();

        return $version;
    }

    /**
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
    public function list(): array
    {
        return $this->scores->findListItemsNewestFirst();
    }

    public function get(string $id): ?Score
    {
        return $this->scores->findOneById($id);
    }

    /**
     * Supprime la partition (versions SQL via ON DELETE CASCADE) puis les
     * objets MusicXML MinIO. On n'hydrate pas model_json.
     */
    public function delete(Score $score): void
    {
        $keys = $this->versions->findMusicxmlKeysForScore($score);

        $this->em->createQueryBuilder()
            ->delete(Score::class, 's')
            ->where('s.id = :id')
            ->setParameter('id', $score->getId())
            ->getQuery()
            ->execute();

        if ($this->em->contains($score)) {
            $this->em->detach($score);
        }

        foreach ($keys as $key) {
            if ($key === '') {
                continue;
            }
            try {
                $this->storage->delete($key);
            } catch (\Throwable) {
                // best-effort : la ligne Postgres est déjà partie
            }
        }
    }

    public function latestVersion(Score $score): ?ScoreVersion
    {
        $versions = $score->getVersions();
        // Évite de lazy-load toutes les versions (model_json peut saturer la mémoire).
        if ($versions instanceof PersistentCollection && !$versions->isInitialized()) {
            return $this->versions->findLatestForScore($score);
        }

        return $score->getLatestVersion();
    }

    /**
     * @return array{header: array<string, mixed>, voices: list<array<string, mixed>>, musicxml: string}|null
     */
    public function loadLatestPayload(Score $score): ?array
    {
        $version = $this->latestVersion($score);
        if ($version === null) {
            return null;
        }

        $musicxml = $this->storage->get($version->getMusicxmlKey());
        $model = $version->getModelJson() ?? [];

        return [
            'header' => $model['header'] ?? [
                'title' => $score->getTitle(),
                'tonic' => $score->getTonic(),
                'timeSignature' => ['beats' => 4, 'beatType' => 4],
                'tempo' => null,
            ],
            'voices' => $model['voices'] ?? [],
            'musicxml' => $musicxml,
            'source' => $model['source'] ?? $score->getSourceType(),
            'warnings' => $model['warnings'] ?? [],
        ];
    }

    /**
     * @param array<string, mixed>|null $model
     */
    private function buildVersion(
        Score $score,
        int $number,
        string $origin,
        string $musicxml,
        ?array $model,
    ): ScoreVersion {
        $key = $this->storage->putMusicXml($score->getId()->toRfc4122(), $number, $musicxml);

        return (new ScoreVersion())
            ->setNumber($number)
            ->setOrigin($origin)
            ->setMusicxmlKey($key)
            ->setModelJson($model);
    }
}
