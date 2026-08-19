<?php

declare(strict_types=1);

namespace App\State;

use ApiPlatform\Metadata\Operation;
use ApiPlatform\State\ProcessorInterface;
use App\ApiResource\ConvertResource;
use App\Service\OmrClient;
use Symfony\Component\HttpKernel\Exception\UnprocessableEntityHttpException;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Symfony\Component\HttpFoundation\Response;

/**
 * Custom write layer for conversion endpoints.
 */
final class ConvertProcessor implements ProcessorInterface
{
    public function __construct(
        private readonly OmrClient $omr,
    ) {
    }

    public function process(mixed $data, Operation $operation, array $uriVariables = [], array $context = []): mixed
    {
        $name = $operation->getName();

        return match ($name) {
            'convert_model_to_musicxml' => $this->processModelToMusicxml($data),
            'convert_solfa_parse' => $this->processSolfaParse($data),
            default => throw new \RuntimeException(sprintf('Unknown Convert operation: %s', (string) $name)),
        };
    }

    private function processModelToMusicxml(mixed $data): ConvertResource
    {
        if (!($data instanceof ConvertResource)) {
            throw new UnprocessableEntityHttpException('JSON invalide');
        }

        if (!is_array($data->models) || $data->models === []) {
            throw new UnprocessableEntityHttpException('models[] est requis');
        }

        try {
            $result = $this->omr->musicxmlFromModels(
                $data->models,
                (string) ($data->title ?? ''),
                (string) ($data->composer ?? ''),
                (string) ($data->work ?? ''),
            );
        } catch (\Throwable $e) {
            throw new HttpException(Response::HTTP_BAD_GATEWAY, $e->getMessage());
        }

        $out = new ConvertResource();
        $out->musicxml = $result['musicxml'] ?? '';
        $out->voices = is_array($result['voices'] ?? null) ? $result['voices'] : [];

        return $out;
    }

    private function processSolfaParse(mixed $data): ConvertResource
    {
        if (!($data instanceof ConvertResource)) {
            throw new UnprocessableEntityHttpException('JSON invalide');
        }

        $notation = trim((string) ($data->notation ?? ''));
        if ($notation === '') {
            throw new UnprocessableEntityHttpException('notation est requis');
        }

        $triplets = $data->triplets;
        if ($triplets !== null && !is_array($triplets)) {
            throw new UnprocessableEntityHttpException('triplets doit être un tableau');
        }

        $dohOctave = $data->dohOctaveSnake ?? $data->dohOctave ?? 4;
        $beatType = $data->beatTypeSnake ?? $data->beatType ?? 4;

        try {
            $result = $this->omr->solfaParse(
                $notation,
                (string) ($data->tonic ?? 'C'),
                (string) ($data->clef ?? 'treble'),
                (int) $dohOctave,
                $data->beats !== null ? (int) $data->beats : null,
                (int) $beatType,
                $triplets,
            );
        } catch (\Throwable $e) {
            throw new HttpException(Response::HTTP_BAD_GATEWAY, $e->getMessage());
        }

        $out = new ConvertResource();
        $out->model = is_array($result['model'] ?? null) ? $result['model'] : [];
        $out->musicxml = is_string($result['musicxml'] ?? null) ? $result['musicxml'] : '';

        return $out;
    }
}

