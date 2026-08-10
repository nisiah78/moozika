<?php

declare(strict_types=1);

namespace App\Service;

use Symfony\Contracts\HttpClient\HttpClientInterface;

/**
 * Client HTTP interne vers omr-service (jamais exposé au navigateur).
 */
class OmrClient
{
    public function __construct(
        private readonly HttpClientInterface $httpClient,
        private readonly string $omrServiceUrl,
    ) {
    }

    /**
     * @param list<array<string, mixed>> $models
     *
     * @return array{musicxml: string, voices: list<array<string, mixed>>}
     */
    public function musicxmlFromModels(array $models, string $title = ''): array
    {
        $response = $this->httpClient->request('POST', rtrim($this->omrServiceUrl, '/').'/musicxml/from-models', [
            'json' => [
                'models' => $models,
                'title' => $title,
            ],
            'timeout' => 60,
        ]);

        $status = $response->getStatusCode();
        $data = $response->toArray(false);
        if ($status >= 400) {
            $detail = is_array($data) ? ($data['detail'] ?? json_encode($data)) : (string) $data;
            throw new \RuntimeException('omr-service from-models: '.$detail, $status);
        }

        if (!isset($data['musicxml']) || !is_string($data['musicxml'])) {
            throw new \RuntimeException('omr-service from-models: réponse sans musicxml');
        }

        return [
            'musicxml' => $data['musicxml'],
            'voices' => is_array($data['voices'] ?? null) ? $data['voices'] : [],
        ];
    }

    /**
     * @param list<array<string, mixed>>|null $triplets
     *
     * @return array{model: array<string, mixed>, musicxml: string}
     */
    public function solfaParse(string $notation, string $tonic = 'C', string $clef = 'treble', int $dohOctave = 4, ?int $beats = null, int $beatType = 4, ?array $triplets = null): array
    {
        // `beats`/`beat_type` PRÉSERVENT la signature à l'édition : sans eux le
        // re-parse retombe sur 4/4 (ex. 10/8 → 10/4, rejeté par from-models).
        $payload = [
            'notation' => $notation,
            'tonic' => $tonic,
            'clef' => $clef,
            'doh_octave' => $dohOctave,
            'beat_type' => $beatType,
        ];
        if ($beats !== null) {
            $payload['beats'] = $beats;
        }
        if ($triplets !== null && $triplets !== []) {
            $payload['triplets'] = $triplets;
        }
        $response = $this->httpClient->request('POST', rtrim($this->omrServiceUrl, '/').'/solfa/parse', [
            'json' => $payload,
            'timeout' => 30,
        ]);

        $status = $response->getStatusCode();
        $data = $response->toArray(false);
        if ($status >= 400) {
            $detail = is_array($data) ? ($data['detail'] ?? json_encode($data)) : (string) $data;
            throw new \RuntimeException('omr-service solfa/parse: '.$detail, $status);
        }

        if (!isset($data['model']) || !is_array($data['model'])) {
            throw new \RuntimeException('omr-service solfa/parse: réponse sans model');
        }

        return [
            'model' => $data['model'],
            'musicxml' => is_string($data['musicxml'] ?? null) ? $data['musicxml'] : '',
        ];
    }
}
