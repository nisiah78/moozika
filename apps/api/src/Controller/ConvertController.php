<?php

declare(strict_types=1);

namespace App\Controller;

use App\Service\OmrClient;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

class ConvertController extends AbstractController
{
    public function __construct(
        private readonly OmrClient $omr,
    ) {
    }

    #[Route('/convert/model-to-musicxml', name: 'convert_model_to_musicxml', methods: ['POST'])]
    public function modelToMusicxml(Request $request): JsonResponse
    {
        $data = json_decode($request->getContent(), true);
        if (!is_array($data)) {
            return $this->json(['detail' => 'JSON invalide'], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        $models = $data['models'] ?? null;
        if (!is_array($models) || $models === []) {
            return $this->json(['detail' => 'models[] est requis'], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        try {
            $result = $this->omr->musicxmlFromModels($models, (string) ($data['title'] ?? ''));
        } catch (\Throwable $e) {
            return $this->json(['detail' => $e->getMessage()], Response::HTTP_BAD_GATEWAY);
        }

        return $this->json($result);
    }

    #[Route('/convert/solfa-parse', name: 'convert_solfa_parse', methods: ['POST'])]
    public function solfaParse(Request $request): JsonResponse
    {
        $data = json_decode($request->getContent(), true);
        if (!is_array($data)) {
            return $this->json(['detail' => 'JSON invalide'], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        $notation = trim((string) ($data['notation'] ?? ''));
        if ($notation === '') {
            return $this->json(['detail' => 'notation est requis'], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        $triplets = $data['triplets'] ?? null;
        if ($triplets !== null && !is_array($triplets)) {
            return $this->json(['detail' => 'triplets doit être un tableau'], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        try {
            $result = $this->omr->solfaParse(
                $notation,
                (string) ($data['tonic'] ?? 'C'),
                (string) ($data['clef'] ?? 'treble'),
                (int) ($data['doh_octave'] ?? $data['dohOctave'] ?? 4),
                isset($data['beats']) ? (int) $data['beats'] : null,
                (int) ($data['beat_type'] ?? $data['beatType'] ?? 4),
                is_array($triplets) ? $triplets : null,
            );
        } catch (\Throwable $e) {
            return $this->json(['detail' => $e->getMessage()], Response::HTTP_BAD_GATEWAY);
        }

        return $this->json($result);
    }
}
