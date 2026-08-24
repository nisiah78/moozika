<?php

declare(strict_types=1);

namespace App\Message;

/**
 * Demande de transcription d'un fichier source (PDF/image) vers MusicXML.
 *
 * Ne transporte QUE l'identifiant du job : le fichier vit dans le stockage objet
 * (uploads/{jobId}/source.*) et le worker le relit depuis là. Faire passer les octets
 * dans le message gonflerait la table de queue et casserait la relecture après un retry.
 */
final readonly class TranscribeMessage
{
    public function __construct(
        public string $jobId,
    ) {
    }
}
