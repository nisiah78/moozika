<?php

declare(strict_types=1);

namespace App\Entity;

use App\Repository\ScoreRepository;
use Doctrine\Common\Collections\ArrayCollection;
use Doctrine\Common\Collections\Collection;
use Doctrine\DBAL\Types\Types;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Uid\Uuid;

#[ORM\Entity(repositoryClass: ScoreRepository::class)]
#[ORM\Table(name: 'score')]
#[ORM\HasLifecycleCallbacks]
class Score
{
    #[ORM\Id]
    #[ORM\Column(type: 'uuid', unique: true)]
    private Uuid $id;

    #[ORM\Column(length: 255)]
    private string $title = '';

    #[ORM\Column(length: 16)]
    private string $tonic = 'C';

    /** @var string staff|solfa|musicxml */
    #[ORM\Column(length: 32)]
    private string $sourceType = 'solfa';

    #[ORM\Column(length: 32)]
    private string $status = 'ready';

    #[ORM\Column(type: Types::DATETIME_IMMUTABLE)]
    private \DateTimeImmutable $createdAt;

    #[ORM\Column(type: Types::DATETIME_IMMUTABLE)]
    private \DateTimeImmutable $updatedAt;

    /** @var Collection<int, ScoreVersion> */
    #[ORM\OneToMany(targetEntity: ScoreVersion::class, mappedBy: 'score', cascade: ['persist', 'remove'], orphanRemoval: true)]
    #[ORM\OrderBy(['number' => 'ASC'])]
    private Collection $versions;

    public function __construct()
    {
        $this->id = Uuid::v7();
        $this->createdAt = new \DateTimeImmutable();
        $this->updatedAt = $this->createdAt;
        $this->versions = new ArrayCollection();
    }

    public function getId(): Uuid
    {
        return $this->id;
    }

    public function getTitle(): string
    {
        return $this->title;
    }

    public function setTitle(string $title): self
    {
        $this->title = $title;

        return $this;
    }

    public function getTonic(): string
    {
        return $this->tonic;
    }

    public function setTonic(string $tonic): self
    {
        $this->tonic = $tonic;

        return $this;
    }

    public function getSourceType(): string
    {
        return $this->sourceType;
    }

    public function setSourceType(string $sourceType): self
    {
        $this->sourceType = $sourceType;

        return $this;
    }

    public function getStatus(): string
    {
        return $this->status;
    }

    public function setStatus(string $status): self
    {
        $this->status = $status;

        return $this;
    }

    public function getCreatedAt(): \DateTimeImmutable
    {
        return $this->createdAt;
    }

    public function getUpdatedAt(): \DateTimeImmutable
    {
        return $this->updatedAt;
    }

    #[ORM\PreUpdate]
    public function touch(): void
    {
        $this->updatedAt = new \DateTimeImmutable();
    }

    public function bumpUpdatedAt(): self
    {
        $this->updatedAt = new \DateTimeImmutable();

        return $this;
    }

    /** @return Collection<int, ScoreVersion> */
    public function getVersions(): Collection
    {
        return $this->versions;
    }

    public function addVersion(ScoreVersion $version): self
    {
        if (!$this->versions->contains($version)) {
            $this->versions->add($version);
            $version->setScore($this);
        }

        return $this;
    }

    public function getLatestVersion(): ?ScoreVersion
    {
        $latest = null;
        foreach ($this->versions as $version) {
            if (null === $latest || $version->getNumber() > $latest->getNumber()) {
                $latest = $version;
            }
        }

        return $latest;
    }

    public function nextVersionNumber(): int
    {
        $max = 0;
        foreach ($this->versions as $version) {
            $max = max($max, $version->getNumber());
        }

        return $max + 1;
    }
}
