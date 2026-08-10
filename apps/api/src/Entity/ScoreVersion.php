<?php

declare(strict_types=1);

namespace App\Entity;

use App\Repository\ScoreVersionRepository;
use Doctrine\DBAL\Types\Types;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Uid\Uuid;

#[ORM\Entity(repositoryClass: ScoreVersionRepository::class)]
#[ORM\Table(name: 'score_version')]
#[ORM\UniqueConstraint(name: 'uniq_score_version_number', columns: ['score_id', 'number'])]
class ScoreVersion
{
    #[ORM\Id]
    #[ORM\Column(type: 'uuid', unique: true)]
    private Uuid $id;

    #[ORM\ManyToOne(targetEntity: Score::class, inversedBy: 'versions')]
    #[ORM\JoinColumn(nullable: false, onDelete: 'CASCADE')]
    private ?Score $score = null;

    #[ORM\Column]
    private int $number = 1;

    /** @var string omr|edit|import */
    #[ORM\Column(length: 32)]
    private string $origin = 'import';

    #[ORM\Column(length: 512)]
    private string $musicxmlKey = '';

    /** @var array<string, mixed>|null */
    #[ORM\Column(type: Types::JSON, nullable: true)]
    private ?array $modelJson = null;

    #[ORM\Column(type: Types::DATETIME_IMMUTABLE)]
    private \DateTimeImmutable $createdAt;

    public function __construct()
    {
        $this->id = Uuid::v7();
        $this->createdAt = new \DateTimeImmutable();
    }

    public function getId(): Uuid
    {
        return $this->id;
    }

    public function getScore(): ?Score
    {
        return $this->score;
    }

    public function setScore(?Score $score): self
    {
        $this->score = $score;

        return $this;
    }

    public function getNumber(): int
    {
        return $this->number;
    }

    public function setNumber(int $number): self
    {
        $this->number = $number;

        return $this;
    }

    public function getOrigin(): string
    {
        return $this->origin;
    }

    public function setOrigin(string $origin): self
    {
        $this->origin = $origin;

        return $this;
    }

    public function getMusicxmlKey(): string
    {
        return $this->musicxmlKey;
    }

    public function setMusicxmlKey(string $musicxmlKey): self
    {
        $this->musicxmlKey = $musicxmlKey;

        return $this;
    }

    /** @return array<string, mixed>|null */
    public function getModelJson(): ?array
    {
        return $this->modelJson;
    }

    /** @param array<string, mixed>|null $modelJson */
    public function setModelJson(?array $modelJson): self
    {
        $this->modelJson = $modelJson;

        return $this;
    }

    public function getCreatedAt(): \DateTimeImmutable
    {
        return $this->createdAt;
    }
}
