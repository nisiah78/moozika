<?php

declare(strict_types=1);

namespace App\Service;

/**
 * Traduit un échec brut de `omr-service` en (code stable, message affichable, retentable ?).
 *
 * Deux raisons d'exister, la seconde plus importante que la première :
 *  1. le `detail` brut est inaffichable — exemples réellement reçus en test :
 *     « image illisible : cannot identify image file <_io.BytesIO object at 0x7f36939ab600> »
 *     et un dump complet des logs INFO d'Audiveris ;
 *  2. toutes les erreurs ne se valent pas. « Audiveris indisponible » est une panne
 *     d'infrastructure qu'il faut **retenter** ; « mesure 7/8 non supportée » est définitif et
 *     doit être expliqué à l'utilisateur. Sans cette distinction, on retente 30 min d'OMR pour
 *     rien, ou on abandonne un job qu'un simple redémarrage aurait sauvé.
 */
final readonly class TranscriptionError
{
    public const CODE_UNSUPPORTED_FILE = 'unsupported_file';
    public const CODE_NO_NOTATION = 'no_notation_detected';
    public const CODE_UNSUPPORTED_NOTATION = 'unsupported_notation';
    public const CODE_RHYTHM_INCONSISTENT = 'rhythm_inconsistent';
    public const CODE_RECOGNITION_UNAVAILABLE = 'recognition_unavailable';
    public const CODE_STAFF_RECOGNITION_FAILED = 'staff_recognition_failed';
    public const CODE_TIMEOUT = 'timeout';
    public const CODE_INTERNAL = 'internal';

    private function __construct(
        public string $code,
        public string $userMessage,
        public bool $retryable,
        public string $rawDetail,
    ) {
    }

    /**
     * @param string|null $code code structuré fourni par omr-service, s'il en fournit un
     */
    public static function fromDetail(string $detail, ?string $code = null): self
    {
        // 1. L'INFRASTRUCTURE D'ABORD, avant même le code structuré. `PdfSolfaError` emballe
        //    parfois un échec Audiveris dans son *texte* (app/pdf/document.py:350) : faire
        //    primer la classe classerait « Audiveris indisponible » en « rien reconnu », donc
        //    en échec définitif, et condamnerait un job qu'un redémarrage aurait sauvé.
        $transient = self::detectTransient($detail);
        if (null !== $transient) {
            return $transient;
        }

        // 2. Le code structuré émis par omr-service (nom de la classe d'exception) : robuste
        //    aux reformulations de message, contrairement aux heuristiques.
        if (null !== $code && '' !== $code) {
            $known = self::fromStructuredCode($code, $detail);
            if (null !== $known) {
                return $known;
            }
        }

        // 3. Repli sur le texte — indispensable : l'`except Exception` de omr-service laisse
        //    remonter des classes Python quelconques (ex. `UnidentifiedImageError`).
        return self::fromHeuristics($detail);
    }

    /**
     * Les seuls échecs qui méritent un retry : le service de reconnaissance est indisponible
     * ou a dépassé son temps. Les confondre avec une erreur de contenu coûte soit 30 min d'OMR
     * pour rien, soit un job perdu alors qu'un redémarrage l'aurait sauvé.
     *
     * Détecté sur le TEXTE et non sur la classe, parce que l'information survit à l'emballage
     * (`PdfSolfaError` reprend le message d'Audiveris dans le sien).
     */
    private static function detectTransient(string $detail): ?self
    {
        $haystack = mb_strtolower($detail);

        foreach ([
            'audiveris indisponible',
            'audiveris_url non configuré',
            'binaire audiveris local introuvable',
            'ocr indisponible',
            'aucun appel',
        ] as $needle) {
            if (str_contains($haystack, $needle)) {
                return self::make(
                    self::CODE_RECOGNITION_UNAVAILABLE,
                    self::messageFor(self::CODE_RECOGNITION_UNAVAILABLE),
                    true,
                    $detail
                );
            }
        }

        if (str_contains($haystack, 'timeout') || str_contains($haystack, 'timed out')) {
            return self::make(self::CODE_TIMEOUT, self::messageFor(self::CODE_TIMEOUT), true, $detail);
        }

        return null;
    }

    /**
     * Chemin privilégié : la classe d'exception Python porte déjà la classification, il suffit
     * qu'elle survive au transport.
     */
    private static function fromStructuredCode(string $code, string $detail): ?self
    {
        return match ($code) {
            'MeterError', 'LexError', 'ParseError' => self::make(
                self::CODE_UNSUPPORTED_NOTATION,
                'Cette partition utilise une notation que la v1 ne gère pas encore.',
                false,
                $detail
            ),
            'RhythmError' => self::make(
                self::CODE_RHYTHM_INCONSISTENT,
                'Le rythme reconnu est incohérent : le total des durées ne remplit pas la mesure.',
                false,
                $detail
            ),
            'ExtractError', 'OcrError' => self::make(
                self::CODE_NO_NOTATION,
                self::messageFor(self::CODE_NO_NOTATION),
                false,
                $detail
            ),
            'MusicXmlError' => self::make(
                self::CODE_UNSUPPORTED_FILE,
                'Ce fichier n\'est pas dans un format exploitable pour la transcription.',
                false,
                $detail
            ),
            // Classes TROP LARGES pour classer sur le seul nom : `PdfSolfaError` emballe
            // aussi bien un fichier corrompu (« image illisible ») qu'un document sans
            // notation ou un repli Audiveris raté, et `StaffRecognizeError` va de « pas de
            // MusicXML produit » à « portée illisible ». Sur celles-là le texte est plus
            // informatif que la classe.
            'PdfSolfaError', 'StaffRecognizeError' => self::fromHeuristics($detail),
            default => null,
        };
    }

    /**
     * Repli sur le texte. Indispensable même avec des codes structurés : l'`except Exception`
     * nu de `omr-service` (main.py:214) laisse remonter n'importe quelle exception Python,
     * qui n'aura jamais de code utile.
     */
    private static function fromHeuristics(string $detail): self
    {
        $haystack = mb_strtolower($detail);

        // L'ORDRE EST SIGNIFIANT : du plus spécifique au plus générique. Un test sur les
        // messages réels a montré que placer 'non supporté' ou 'triolet' trop haut capturait
        // « mesure non supportée en v1: 7/8 » et « durée non alignée sur la grille (triolet ?) »
        // dans la mauvaise catégorie. Ne pas réordonner sans repasser le jeu de messages.
        foreach ([
            // 1. Rythme : avant 'triolet', que ces messages contiennent souvent.
            'durée non alignée' => self::CODE_RHYTHM_INCONSISTENT,
            'durée non représentable' => self::CODE_RHYTHM_INCONSISTENT,
            'durée invalide' => self::CODE_RHYTHM_INCONSISTENT,

            // 2. Notation hors périmètre v1 : avant le générique 'non supporté'.
            'mesure non supportée' => self::CODE_UNSUPPORTED_NOTATION,
            'subdivision non supportée' => self::CODE_UNSUPPORTED_NOTATION,
            'non géré en v1' => self::CODE_UNSUPPORTED_NOTATION,
            'triolet' => self::CODE_UNSUPPORTED_NOTATION,

            // 3. Audiveris a bien tourne mais n'a pas su lire la portee. recognize.py:107
            // prefixe ces echecs par « Audiveris : » suivi de la sortie JVM nettoyee ; c'est
            // le cas le plus courant du chemin portee, il ne doit pas retomber sur « raison
            // inattendue ». Vient APRES le bloc infrastructure, pour que « Audiveris
            // indisponible » reste classe comme transitoire.
            'audiveris : ' => self::CODE_STAFF_RECOGNITION_FAILED,
            'échec audiveris' => self::CODE_STAFF_RECOGNITION_FAILED,
            'reconnaissance échouée' => self::CODE_STAFF_RECOGNITION_FAILED,

            // 4. Rien de reconnu dans un document par ailleurs valide.
            'aucun texte reconnu' => self::CODE_NO_NOTATION,
            'aucun texte extrait' => self::CODE_NO_NOTATION,
            'aucune voix exploitable' => self::CODE_NO_NOTATION,
            'sans voix exploitable' => self::CODE_NO_NOTATION,
            'aucun musicxml' => self::CODE_NO_NOTATION,

            // 5. Format d'entrée inadapté.
            'pas du musicxml' => self::CODE_UNSUPPORTED_FILE,
            'fichier image détecté' => self::CODE_UNSUPPORTED_FILE,
            'score-timewise' => self::CODE_UNSUPPORTED_FILE,
            'pdf sans page' => self::CODE_UNSUPPORTED_FILE,

            // 6. Filets génériques, en dernier par construction.
            'illisible' => self::CODE_UNSUPPORTED_FILE,
            'non supporté' => self::CODE_UNSUPPORTED_FILE,
        ] as $needle => $mapped) {
            if (str_contains($haystack, $needle)) {
                return self::make($mapped, self::messageFor($mapped), false, $detail);
            }
        }

        return self::make(
            self::CODE_INTERNAL,
            'La transcription a échoué pour une raison inattendue.',
            false,
            $detail
        );
    }

    private static function messageFor(string $code): string
    {
        return match ($code) {
            self::CODE_UNSUPPORTED_FILE => 'Ce fichier n\'est pas dans un format exploitable pour la transcription.',
            self::CODE_NO_NOTATION => 'Aucune notation musicale n\'a pu être reconnue dans ce document.',
            self::CODE_UNSUPPORTED_NOTATION => 'Cette partition utilise une notation que la v1 ne gère pas encore.',
            self::CODE_RHYTHM_INCONSISTENT => 'Le rythme reconnu est incohérent : le total des durées ne remplit pas la mesure.',
            self::CODE_RECOGNITION_UNAVAILABLE => 'Le service de reconnaissance est momentanément indisponible.',
            self::CODE_STAFF_RECOGNITION_FAILED => 'La reconnaissance de la portée a échoué : la partition est peut-être trop dense ou de qualité insuffisante.',
            self::CODE_TIMEOUT => 'La reconnaissance a dépassé le temps imparti. Essayez avec un document plus court.',
            default => 'La transcription a échoué pour une raison inattendue.',
        };
    }

    private static function make(string $code, string $message, bool $retryable, string $detail): self
    {
        // Le detail brut est CONSERVÉ (diagnostic) mais borné : un échec Audiveris renvoie
        // plusieurs kilo-octets de logs Java.
        return new self($code, $message, $retryable, mb_substr(trim($detail), 0, 2000));
    }
}
