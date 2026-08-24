<?php

declare(strict_types=1);

namespace App\Service;

use AsyncAws\S3\S3Client;
use Symfony\Component\Uid\Uuid;

/**
 * Stockage objet MinIO (API S3). Credentials uniquement côté serveur.
 */
class ObjectStorage
{
    private S3Client $client;

    public function __construct(
        private readonly string $bucket,
        string $endpoint,
        string $accessKey,
        string $secretKey,
        string $region = 'us-east-1',
    ) {
        $this->client = new S3Client([
            'endpoint' => $endpoint,
            'accessKeyId' => $accessKey,
            'accessKeySecret' => $secretKey,
            'region' => $region,
            'pathStyleEndpoint' => true,
        ]);
    }

    public function putMusicXml(string $scoreId, int $versionNumber, string $musicxml): string
    {
        $key = sprintf('scores/%s/v%d.musicxml', $scoreId, $versionNumber);
        $this->client->putObject([
            'Bucket' => $this->bucket,
            'Key' => $key,
            'Body' => $musicxml,
            'ContentType' => 'application/vnd.recordare.musicxml+xml',
        ]);

        return $key;
    }

    /**
     * Fichier source d'une transcription (PDF/image), en attente de traitement par le worker.
     *
     * Séparé de `putMusicXml` par le préfixe : `uploads/` est du transitoire à purger une fois
     * le job terminé, `scores/` est le durable. Pour relire ou supprimer, `get()`/`delete()`
     * génériques suffisent — le job porte sa `sourceKey`.
     */
    public function putSource(string $jobId, string $filename, string $body, string $contentType): string
    {
        $ext = strtolower(pathinfo($filename, \PATHINFO_EXTENSION));
        // Bornée volontairement : le nom de fichier vient du client, il ne doit pas pouvoir
        // fabriquer une clé arbitraire dans le bucket.
        if (1 !== preg_match('/^[a-z0-9]{1,8}$/', $ext)) {
            $ext = 'bin';
        }

        $key = sprintf('uploads/%s/source.%s', $jobId, $ext);
        $this->client->putObject([
            'Bucket' => $this->bucket,
            'Key' => $key,
            'Body' => $body,
            'ContentType' => $contentType,
        ]);

        return $key;
    }

    public function get(string $key): string
    {
        $result = $this->client->getObject([
            'Bucket' => $this->bucket,
            'Key' => $key,
        ]);

        return $result->getBody()->getContentAsString();
    }

    public function delete(string $key): void
    {
        $this->client->deleteObject([
            'Bucket' => $this->bucket,
            'Key' => $key,
        ]);
    }

    public function ensureBucket(): void
    {
        try {
            $this->client->headBucket(['Bucket' => $this->bucket]);
        } catch (\Throwable) {
            $this->client->createBucket(['Bucket' => $this->bucket]);
        }
    }

    public static function newScoreId(): string
    {
        return Uuid::v7()->toRfc4122();
    }
}
