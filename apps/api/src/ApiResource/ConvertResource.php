<?php

declare(strict_types=1);

namespace App\ApiResource;

use ApiPlatform\Metadata\ApiResource;
use ApiPlatform\Metadata\Post;
use Symfony\Component\Serializer\Annotation\SerializedName;

/**
 * Endpoint dédié à la conversion (omr-service).
 */
#[ApiResource(
    shortName: 'Convert',
    routePrefix: '',
    operations: [
        new Post(
            uriTemplate: '/convert/model-to-musicxml',
            name: 'convert_model_to_musicxml',
            processor: \App\State\ConvertProcessor::class,
            read: false,
            deserialize: true,
        ),
        new Post(
            uriTemplate: '/convert/solfa-parse',
            name: 'convert_solfa_parse',
            processor: \App\State\ConvertProcessor::class,
            read: false,
            deserialize: true,
        ),
    ],
)]
final class ConvertResource
{
    // ---- Request: model-to-musicxml ----
    public ?array $models = null;
    public ?string $title = null;
    public ?string $composer = null;
    public ?string $work = null;

    // ---- Request: solfa-parse ----
    public ?string $notation = null;
    public ?string $tonic = null;
    public ?string $clef = null;

    public ?int $dohOctave = null;

    #[SerializedName('doh_octave')]
    public ?int $dohOctaveSnake = null;

    public mixed $triplets = null;

    public ?int $beats = null;

    public ?int $beatType = null;

    #[SerializedName('beat_type')]
    public ?int $beatTypeSnake = null;

    // ---- Response shared fields ----
    public ?string $musicxml = null;
    public ?array $voices = null;
    public ?array $model = null;
}

