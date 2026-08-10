import type { ScoreResult } from "./types";

/** Valeur de note utilisée comme repère du tempo (dénominateur MusicXML). */
export type TempoBeatUnit = 1 | 2 | 4 | 8 | 16;

export interface TempoSettings {
  bpm: number;
  beatUnit: TempoBeatUnit;
  dotted: boolean;
}

export interface TempoBeatOption {
  id: string;
  beatUnit: TempoBeatUnit;
  dotted: boolean;
  symbol: string;
  label: string;
}

export const TEMPO_BEAT_OPTIONS: TempoBeatOption[] = [
  { id: "whole", beatUnit: 1, dotted: false, symbol: "𝅝", label: "Ronde" },
  { id: "half", beatUnit: 2, dotted: false, symbol: "𝅗𝅥", label: "Blanche" },
  { id: "quarter", beatUnit: 4, dotted: false, symbol: "♩", label: "Noire" },
  { id: "quarter-dot", beatUnit: 4, dotted: true, symbol: "♩.", label: "Noire pointée" },
  { id: "eighth", beatUnit: 8, dotted: false, symbol: "♪", label: "Croche" },
  { id: "eighth-dot", beatUnit: 8, dotted: true, symbol: "♪.", label: "Croche pointée" },
];

const DEFAULT_BPM = 90;

export function tempoOptionId(settings: TempoSettings): string {
  const match = TEMPO_BEAT_OPTIONS.find(
    (o) => o.beatUnit === settings.beatUnit && o.dotted === settings.dotted,
  );
  return match?.id ?? "quarter";
}

export function tempoFromOptionId(id: string, bpm: number): TempoSettings {
  const opt = TEMPO_BEAT_OPTIONS.find((o) => o.id === id) ?? TEMPO_BEAT_OPTIONS[2];
  return { bpm, beatUnit: opt.beatUnit, dotted: opt.dotted };
}

/** BPM effectif en noires/min (référence MusicXML / playback). */
export function resolveQuarterBpm(settings: TempoSettings): number {
  const dot = settings.dotted ? 1.5 : 1;
  const quarterFactor = settings.beatUnit / 4 / dot;
  return settings.bpm / quarterFactor;
}

export function defaultTempoSettings(result: ScoreResult): TempoSettings {
  const { beats, beatType } = result.header.timeSignature;
  const bpm =
    result.header.tempo ??
    result.voices.find((v) => v.model.tempo)?.model.tempo ??
    DEFAULT_BPM;

  if (result.header.tempoBeatUnit) {
    return {
      bpm,
      beatUnit: result.header.tempoBeatUnit,
      dotted: !!result.header.tempoDotted,
    };
  }

  // Mesures composées (9/8, 12/8…) : repère usuel = noire pointée.
  // 6/8 chorale (grille à 6 croches) : croche, comme 10/8.
  if (beatType === 8 && beats % 3 === 0 && beats > 6) {
    return { bpm, beatUnit: 4, dotted: true };
  }
  if (beatType === 8 && (beats === 5 || beats === 6 || beats === 10)) {
    return { bpm, beatUnit: 8, dotted: false };
  }

  const beatUnit: TempoBeatUnit =
    beatType === 2 ? 2 : beatType === 8 ? 8 : beatType === 16 ? 16 : 4;
  return { bpm, beatUnit, dotted: false };
}

export function formatTempoLabel(settings: TempoSettings): string {
  const opt = TEMPO_BEAT_OPTIONS.find(
    (o) => o.beatUnit === settings.beatUnit && o.dotted === settings.dotted,
  );
  return `${opt?.symbol ?? "♩"} = ${settings.bpm}`;
}
