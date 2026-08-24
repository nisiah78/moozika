<?php

declare(strict_types=1);

namespace App\Entity;

use App\Repository\TranscriptionJobRepository;
use Doctrine\DBAL\Types\Types;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Uid\Uuid;

/**
 * Une demande de transcription (PDF/image → MusicXML) suivie de bout en bout.
 *
 * Entité AUTONOME : elle ne pointe vers un Score qu'après succès. C'est un écart assumé vs
 * docs/architecture.md §12 (où JOB porte un score_id non nul), et il est délibéré :
 * ScoreService::create() exige un musicxml non vide et un Score a toujours ≥ 1 ScoreVersion.
 * Créer un Score « en attente » casserait cet invariant et ferait échouer loadLatestPayload.
 */
#[ORM\Entity(repositoryClass: TranscriptionJobRepository::class)]
#[ORM\Table(name: 'transcription_job')]
#[ORM\Index(name: 'idx_transcription_job_status', columns: ['status'])]
#[ORM\Index(name: 'idx_transcription_job_created_at', columns: ['created_at'])]
#[ORM\HasLifecycleCallbacks]
class TranscriptionJob
{
    public const STATUS_QUEUED = 'queued';
    public const STATUS_RUNNING = 'running';
    public const STATUS_DONE = 'done';
    public const STATUS_FAILED = 'failed';
    public const STATUS_CANCELLED = 'cancelled';

    /** États depuis lesquels une annulation a encore un sens. */
    public const ACTIVE_STATUSES = [self::STATUS_QUEUED, self::STATUS_RUNNING];

    #[ORM\Id]
    #[ORM\Column(type: 'uuid', unique: true)]
    private Uuid $id;

    /** @var string queued|running|done|failed|cancelled */
    #[ORM\Column(length: 32)]
    private string $status = self::STATUS_QUEUED;

    /**
     * Phase du contrat SSE (packages/shared-contracts/omr-stream.md) :
     * detect|ocr|layout|audiveris|convert. Null tant que rien n'a démarré.
     */
    #[ORM\Column(length: 32, nullable: true)]
    private ?string $phase = null;

    /**
     * Progression 0-100 telle que rapportée par omr-service.
     *
     * ATTENTION : ne vaut PAS une progression globale fiable. Sur le chemin portée, pct passe
     * de 20 à 75 sans rien entre les deux pendant 15-30 min. Le front doit afficher une barre
     * indéterminée pendant la phase `audiveris` plutôt qu'un pourcentage figé.
     */
    #[ORM\Column(type: Types::SMALLINT, options: ['default' => 0])]
    private int $pct = 0;

    /** Message d'avancement lisible, tel qu'émis par omr-service. */
    #[ORM\Column(length: 255, nullable: true)]
    private ?string $message = null;

    /** Clé du fichier source dans le stockage objet (uploads/{jobId}/source.*). */
    #[ORM\Column(length: 512)]
    private string $sourceKey = '';

    #[ORM\Column(length: 255)]
    private string $sourceFilename = '';

    #[ORM\Column(length: 128)]
    private string $sourceMime = 'application/octet-stream';

    /**
     * Tonique imposée par l'utilisateur, passée telle quelle à omr-service.
     *
     * Hors notation par conception : le sol-fa tonique est relatif, la tonique est une
     * métadonnée qui ne se devine pas depuis les syllabes (cf. CLAUDE.md).
     */
    #[ORM\Column(length: 16, nullable: true)]
    private ?string $tonic = null;

    /** Code stable de la taxonomie d'erreurs (étape 6), pour un message traduisible. */
    #[ORM\Column(length: 64, nullable: true)]
    private ?string $errorCode = null;

    /** Message DESTINE A L'UTILISATEUR, issu de la taxonomie (TranscriptionError). */
    #[ORM\Column(type: Types::TEXT, nullable: true)]
    private ?string $errorMessage = null;

    /**
     * Detail technique brut renvoye par omr-service, conserve pour le diagnostic.
     *
     * Ne JAMAIS l'afficher comme message principal : en pratique c'est parfois un dump des
     * logs INFO d'Audiveris ou une repr Python (`<_io.BytesIO object at 0x...>`).
     */
    #[ORM\Column(type: Types::TEXT, nullable: true)]
    private ?string $errorDetail = null;

    /**
     * Renseigné au succès seulement. `SET NULL` en base : supprimer un Score ne doit pas
     * laisser le job pointer vers un identifiant mort — et ScoreService::delete() passe par
     * un DELETE DQL, que seule une contrainte au niveau base couvre.
     */
    #[ORM\ManyToOne(targetEntity: Score::class)]
    #[ORM\JoinColumn(nullable: true, onDelete: 'SET NULL')]
    private ?Score $score = null;

    #[ORM\Column(type: Types::DATETIME_IMMUTABLE)]
    private \DateTimeImmutable $createdAt;

    #[ORM\Column(type: Types::DATETIME_IMMUTABLE)]
    private \DateTimeImmutable $updatedAt;

    public function __construct()
    {
        $this->id = Uuid::v7();
        $this->createdAt = new \DateTimeImmutable();
        $this->updatedAt = $this->createdAt;
    }

    public function getId(): Uuid
    {
        return $this->id;
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

    public function isActive(): bool
    {
        return \in_array($this->status, self::ACTIVE_STATUSES, true);
    }

    public function isCancelled(): bool
    {
        return self::STATUS_CANCELLED === $this->status;
    }

    public function getPhase(): ?string
    {
        return $this->phase;
    }

    public function setPhase(?string $phase): self
    {
        $this->phase = $phase;

        return $this;
    }

    public function getPct(): int
    {
        return $this->pct;
    }

    public function setPct(int $pct): self
    {
        $this->pct = max(0, min(100, $pct));

        return $this;
    }

    public function getMessage(): ?string
    {
        return $this->message;
    }

    public function setMessage(?string $message): self
    {
        $this->message = null === $message ? null : mb_substr($message, 0, 255);

        return $this;
    }

    public function getSourceKey(): string
    {
        return $this->sourceKey;
    }

    public function setSourceKey(string $sourceKey): self
    {
        $this->sourceKey = $sourceKey;

        return $this;
    }

    public function getSourceFilename(): string
    {
        return $this->sourceFilename;
    }

    public function setSourceFilename(string $sourceFilename): self
    {
        $this->sourceFilename = mb_substr($sourceFilename, 0, 255);

        return $this;
    }

    public function getSourceMime(): string
    {
        return $this->sourceMime;
    }

    public function setSourceMime(string $sourceMime): self
    {
        $this->sourceMime = mb_substr($sourceMime, 0, 128);

        return $this;
    }

    public function getTonic(): ?string
    {
        return $this->tonic;
    }

    public function setTonic(?string $tonic): self
    {
        $this->tonic = $tonic;

        return $this;
    }

    public function getErrorCode(): ?string
    {
        return $this->errorCode;
    }

    public function getErrorMessage(): ?string
    {
        return $this->errorMessage;
    }

    public function getErrorDetail(): ?string
    {
        return $this->errorDetail;
    }

    public function setError(string $code, string $message, ?string $detail = null): self
    {
        $this->errorCode = $code;
        $this->errorMessage = $message;
        $this->errorDetail = $detail;

        return $this;
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

    /**
     * À appeler explicitement quand seule la progression change : le worker écrit hors
     * cycle PreUpdate dans certains cas (transactions courtes + clear()), et `updatedAt`
     * est ce qui permettra de repérer un job zombie (étape 11).
     */
    public function bumpUpdatedAt(): self
    {
        $this->updatedAt = new \DateTimeImmutable();

        return $this;
    }
}
