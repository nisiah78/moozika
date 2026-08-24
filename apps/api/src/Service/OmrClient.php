<?php

declare(strict_types=1);

namespace App\Service;

use Symfony\Contracts\HttpClient\HttpClientInterface;

/**
 * Client HTTP interne vers omr-service (jamais exposé au navigateur).
 */
class OmrClient
{
    /**
     * Borne totale d'une reconnaissance. Calee sur AUDIVERIS_TIMEOUT (1800 s, cf. compose.yml)
     * plus la marge de l'OCR et de la generation MusicXML.
     */
    private const STREAM_MAX_DURATION = 2400;

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
    public function musicxmlFromModels(
        array $models,
        string $title = '',
        string $composer = '',
        string $work = '',
    ): array {
        $response = $this->httpClient->request('POST', rtrim($this->omrServiceUrl, '/').'/musicxml/from-models', [
            'json' => [
                'models' => $models,
                'title' => $title,
                'composer' => $composer,
                'work' => $work,
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

    /**
     * Consomme `POST /pdf/parse/stream` en flux et rejoue chaque événement SSE.
     *
     * Contrat des événements : packages/shared-contracts/omr-stream.md (gelé) —
     * `progress` / `voice` / `done` / `error`, plus des commentaires `: ping` toutes les 5 s
     * remontes au callable sous le nom synthetique `ping` (voir drainFrames()).
     *
     * Volontairement PAS `EventSourceHttpClient` : celui-ci implémente la reconnexion
     * automatique de la spec EventSource (`replaceRequest()` sur toute TransportException,
     * cf. son source ligne ~96). Cette sémantique suppose un GET idempotent ; ici elle
     * **re-POSTerait** l'upload et lancerait une SECONDE transcription de 15-30 min pendant
     * que la première tourne encore côté Python.
     *
     * @param callable(string, array<string, mixed>): bool $onEvent retourner false interrompt
     *                                                              le flux (annulation coopérative)
     *
     * @throws \RuntimeException si omr-service répond une erreur HTTP avant le flux
     */
    public function parsePdfStream(
        string $body,
        string $filename,
        string $mime,
        ?string $tonic,
        callable $onEvent,
    ): void {
        $boundary = 'moozika'.bin2hex(random_bytes(16));

        $response = $this->httpClient->request('POST', rtrim($this->omrServiceUrl, '/').'/pdf/parse/stream', [
            'headers' => [
                'Content-Type' => 'multipart/form-data; boundary='.$boundary,
                'Accept' => 'text/event-stream',
            ],
            'body' => self::buildMultipart($boundary, $body, $filename, $mime, $tonic),
            // MESURÉ : on ne peut PAS s'appuyer sur le timeout d'inactivité. Les `: ping`
            // annoncés toutes les 5 s ne sortent pas de façon fiable — sur un PDF scanné de
            // 213 Ko, le plus grand silence observé entre deux chunks est de **93,6 s** (206,9 s
            // au total, 18 pings). L'OCR natif (Paddle/torch) tient le GIL et empêche la boucle
            // asyncio d'émettre. Pendant la phase `audiveris` c'est pire encore, le service
            // Audiveris bloquant lui aussi sa propre boucle.
            //
            // Un timeout d'inactivité court déclenche donc à tort, Messenger retente, et une
            // SECONDE reconnaissance démarre alors que la première continue de tourner côté
            // Python (qui n'annule rien). On aligne donc l'inactivité sur la durée totale : la
            // seule borne qui a du sens ici est `max_duration`.
            'timeout' => self::STREAM_MAX_DURATION,
            'max_duration' => self::STREAM_MAX_DURATION,
            // Sinon le corps du flux est accumulé dans un php://temp au lieu d'être consommé.
            'buffer' => false,
        ]);

        $buffer = '';
        $errorBody = '';
        $errorStatus = 0;

        foreach ($this->httpClient->stream($response) as $chunk) {
            if ($chunk->isFirst()) {
                $errorStatus = $response->getStatusCode();
                if ($errorStatus < 400) {
                    $errorStatus = 0;
                }

                continue;
            }

            if ($chunk->isLast()) {
                break;
            }

            if (0 !== $errorStatus) {
                $errorBody .= $chunk->getContent();

                continue;
            }

            $buffer .= $chunk->getContent();

            foreach (self::drainFrames($buffer) as [$event, $data]) {
                if (false === $onEvent($event, $data)) {
                    $response->cancel();

                    return;
                }
            }
        }

        if (0 !== $errorStatus) {
            throw new \RuntimeException(
                'omr-service pdf/parse/stream: '.self::extractDetail($errorBody, $errorStatus),
                $errorStatus
            );
        }
    }

    /**
     * Assemble le corps multipart à la main : symfony/mime (FormDataPart) n'est pas
     * installable ici, toutes ses versions 7.3.* étant bloquées par des avis de sécurité.
     * La charge est simple et entièrement sous notre contrôle (un fichier, un champ texte).
     */
    private static function buildMultipart(
        string $boundary,
        string $body,
        string $filename,
        string $mime,
        ?string $tonic,
    ): string {
        $parts = '';

        if (null !== $tonic && '' !== $tonic) {
            $parts .= "--{$boundary}\r\n"
                ."Content-Disposition: form-data; name=\"tonic\"\r\n\r\n"
                .self::sanitizeHeaderValue($tonic)."\r\n";
        }

        $parts .= "--{$boundary}\r\n"
            .'Content-Disposition: form-data; name="file"; filename="'.self::sanitizeHeaderValue($filename)."\"\r\n"
            .'Content-Type: '.self::sanitizeHeaderValue($mime)."\r\n\r\n"
            .$body."\r\n"
            ."--{$boundary}--\r\n";

        return $parts;
    }

    /**
     * Le nom de fichier vient du client : sans nettoyage, un guillemet ou un CRLF permettrait
     * d'injecter des en-têtes MIME arbitraires dans le corps multipart.
     */
    private static function sanitizeHeaderValue(string $value): string
    {
        return str_replace(["\r", "\n", '"'], '', $value);
    }

    /**
     * Extrait les trames SSE complètes du tampon et laisse le reliquat en place.
     *
     * Les commentaires (`: ping`) et les trames sans `data:` exploitable sont ignorés.
     *
     * @return list<array{0: string, 1: array<string, mixed>}>
     */
    private static function drainFrames(string &$buffer): array
    {
        $frames = [];

        while (false !== $pos = strpos($buffer, "\n\n")) {
            $raw = substr($buffer, 0, $pos);
            $buffer = substr($buffer, $pos + 2);

            $event = 'message';
            $data = '';
            foreach (preg_split('/\r\n|\r|\n/', $raw) ?: [] as $line) {
                if (str_starts_with($line, 'event:')) {
                    $event = trim(substr($line, 6));
                } elseif (str_starts_with($line, 'data:')) {
                    $data .= ltrim(substr($line, 5), ' ');
                }
            }

            // Heartbeat (`: ping`) : aucune donnee, mais on le REMONTE quand meme. Pendant la
            // phase `audiveris` omr-service n'emet plus rien pendant 15-30 min sauf ces
            // commentaires ; sans ce tick, l'appelant ne pourrait ni constater une annulation
            // ni garder sa connexion base active sur toute cette duree.
            if ('' === $data) {
                $frames[] = ['ping', []];

                continue;
            }

            $decoded = json_decode($data, true);
            if (\is_array($decoded)) {
                /** @var array<string, mixed> $decoded */
                $frames[] = [$event, $decoded];
            }
        }

        return $frames;
    }

    private static function extractDetail(string $body, int $status): string
    {
        $decoded = json_decode($body, true);
        if (\is_array($decoded) && \is_string($decoded['detail'] ?? null)) {
            return $decoded['detail'];
        }

        return '' !== $body ? mb_substr($body, 0, 500) : 'HTTP '.$status;
    }
}
