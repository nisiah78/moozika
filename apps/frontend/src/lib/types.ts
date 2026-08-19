// Types alignés sur la réponse de omr-service `/pdf/parse`.
// Événements SSE : packages/shared-contracts/omr-stream.md

export interface Pitch {
  step: string;
  alter: number;
  octave: number;
  syllable: string;
}

export interface NoteEl {
  isRest: boolean;
  duration: number;
  type: string;
  dots: number;
  pitch: Pitch | null;
  tieStart: boolean;
  tieStop: boolean;
}

/** Indication à durée nulle (alignée omr `Direction`). */
export interface MeasureDirection {
  offset: number;
  kind:
    | "dynamics"
    | "wedge"
    | "words"
    | "metronome"
    | "pedal"
    | "segno"
    | "coda"
    | "dacapo"
    | "dalsegno"
    | "fine"
    | string;
  value: string;
  placement?: "above" | "below" | string;
  staff?: number;
  number?: number;
}

export interface Measure {
  number: number;
  notes: NoteEl[];
  directions?: MeasureDirection[];
  /** Changement de métrique à cette mesure. */
  timeSignature?: { beats: number; beatType: number };
  /** Changement d'armure (fifths MusicXML) à cette mesure. */
  keyFifths?: number;
  /** Tonique déclarée si keyFifths est posé. */
  keyTonic?: string;
  repeat?: "forward" | "backward" | string;
  ending?: { number?: string; type?: string };
  implicit?: boolean;
  beatLyrics?: (string | null)[];
}

export interface VoiceModel {
  tonic: string;
  fifths: number;
  /** ``major`` | ``minor`` (mineur la-based). */
  mode?: "major" | "minor";
  timeSignature: { beats: number; beatType: number };
  divisions: number;
  clef: string;
  tempo: number | null;
  partName: string;
  measures: Measure[];
  staffCount?: number;
  midiProgram?: number | null;
  /** Octave scientifique du doh (défaut 4). */
  dohOctave?: number;
  /** Triolets annotés (3 notes sur 1 ou 2 temps, dans la mesure courante). */
  triplets?: TripletMark[];
  /**
   * Voix ajoutée par divisi : index (0-based) de la mesure absolue où elle
   * entre. Le rendu sol-fa n'affiche la voix qu'à partir de ce système
   * (sinon une voix entièrement silencieuse resterait masquée). Métadonnée UI
   * non exprimée en MusicXML → à re-attacher après régénération.
   */
  enterMeasure?: number;
}

/** Triolet dans une mesure : 3 notes sur spanBeats (1 ou 2 temps sol-fa). */
export interface TripletMark {
  id: string;
  startMeasure: number;
  startBeat: number;
  spanBeats: 1 | 2;
}

export interface Voice {
  name: string;
  notation: string;
  model: VoiceModel;
}

export interface ScoreResult {
  header: {
    title: string;
    composer?: string;
    /** Numéro / catalogue d'œuvre (MusicXML ``work-number``). */
    work?: string;
    tonic: string;
    mode?: "major" | "minor";
    fifths?: number;
    timeSignature: { beats: number; beatType: number };
    /** BPM affiché (repère = tempoBeatUnit, éventuellement pointé). */
    tempo: number | null;
    /** Unité du métronome UI (1=ronde … 8=croche). Absent → déduit de la mesure. */
    tempoBeatUnit?: 1 | 2 | 4 | 8 | 16 | null;
    tempoDotted?: boolean | null;
  };
  voices: Voice[];
  musicxml: string;
  /** Fichier .mxl d'origine (OSMD charge l'archive directement). */
  uploadedFile?: File;
  warnings?: string[];
  /** ``solfa_pdf`` | ``audiveris`` */
  source?: string;
}

/** Réponse brute de omr-service `/musicxml/parse`. */
export interface MusicXmlParseResponse {
  header: {
    title?: string;
    composer?: string;
    work?: string;
    tonic: string;
    mode?: string;
    fifths?: number;
    beats: number;
    beatType: number;
    tempo: number | null;
  };
  voices: Voice[];
  warnings?: string[];
}

/** Événements SSE de `POST /pdf/parse/stream`. */
export type OmStreamEvent =
  | { event: "progress"; phase: string; pct: number; message: string }
  | { event: "voice"; index: number; total: number; voice: Voice }
  | { event: "done"; result: ScoreResult }
  | { event: "error"; detail: string };
