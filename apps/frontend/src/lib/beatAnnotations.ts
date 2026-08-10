/**
 * Annotations au niveau d'un temps (nuances, soufflets, triolet).
 * Persistées dans Measure.directions avec un offset en divisions.
 */

import type { Measure, MeasureDirection, ScoreResult, VoiceModel } from "@/lib/types";
import { cloneScore } from "@/lib/scoreEdit";
import {
  effectiveTimeSignature,
  measureCapacity,
  solfaPulseCount,
} from "@/lib/measureDirectives";

export type BeatAnnotationMenuId =
  | "dynamics"
  | "crescendo"
  | "diminuendo"
  | "wedge-stop";

export type BeatAnnotationPayload =
  | { id: "dynamics"; level: string }
  | { id: "crescendo" | "diminuendo" | "wedge-stop" };

export type BeatAnnotationChip = {
  key: string;
  kind: "dynamics" | "wedge";
  label: string;
  offset: number;
  value: string;
  number?: number;
};

export const DYNAMIC_LEVELS = [
  "pp",
  "p",
  "mp",
  "mf",
  "f",
  "ff",
  "sf",
  "fp",
] as const;

export const BEAT_ANNOTATION_MENU: {
  id: BeatAnnotationMenuId;
  label: string;
  group: "dynamics" | "hairpin";
  needsPick?: boolean;
}[] = [
  ...DYNAMIC_LEVELS.map((level) => ({
    id: "dynamics" as const,
    label: level,
    group: "dynamics" as const,
    needsPick: true,
  })),
  { id: "crescendo", label: "Crescendo ⟨", group: "hairpin" },
  { id: "diminuendo", label: "Diminuendo ⟩", group: "hairpin" },
  { id: "wedge-stop", label: "Fin de soufflet", group: "hairpin" },
];

const WEDGE_LABEL: Record<string, string> = {
  crescendo: "⟨",
  diminuendo: "⟩",
  stop: "◀▶",
};

export function isGlobalAnnotationPayload(_payload: BeatAnnotationPayload): boolean {
  return true;
}

export function isGlobalAnnotationChip(chip: BeatAnnotationChip): boolean {
  return chip.kind === "dynamics" || chip.kind === "wedge";
}

function directionToChip(
  d: MeasureDirection,
  off: number,
): BeatAnnotationChip | null {
  if (d.kind === "dynamics") {
    return {
      key: `dyn-${off}-${d.value}`,
      kind: "dynamics",
      label: d.value,
      offset: off,
      value: d.value,
    };
  }
  if (d.kind === "wedge") {
    return {
      key: `wedge-${off}-${d.value}-${d.number ?? 0}`,
      kind: "wedge",
      label: WEDGE_LABEL[d.value] ?? d.value,
      offset: off,
      value: d.value,
      number: d.number,
    };
  }
  return null;
}

/** Nuances / soufflets — une seule fois (pupitre SATB), lues sur la voix de référence. */
export function globalChipsForBeat(
  measure: Measure | undefined,
  model: VoiceModel,
  measureIndex: number,
  beatIndex: number,
): BeatAnnotationChip[] {
  if (!measure?.directions?.length) return [];
  const target = beatOffsetDivisions(model, measureIndex, beatIndex);
  const tol = pulseTolerance(model, measureIndex);
  const chips: BeatAnnotationChip[] = [];

  for (const d of measure.directions) {
    const off = d.offset ?? 0;
    if (Math.abs(off - target) > tol) continue;
    if (d.kind !== "dynamics" && d.kind !== "wedge") continue;
    const chip = directionToChip(d, off);
    if (chip) chips.push(chip);
  }
  return chips;
}

function ensureMeasure(model: VoiceModel, measureIndex: number): Measure {
  while (model.measures.length <= measureIndex) {
    model.measures.push({
      number: model.measures.length + 1,
      notes: [],
    });
  }
  return model.measures[measureIndex];
}

/** Offset MusicXML (divisions) du début d'un temps sol-fa. */
export function beatOffsetDivisions(
  model: VoiceModel,
  measureIndex: number,
  beatIndex: number,
): number {
  const ts = effectiveTimeSignature(model, measureIndex);
  const pulses = solfaPulseCount(ts.beats, ts.beatType);
  const cap = measureCapacity(ts.beats, ts.beatType, model.divisions || 1);
  const pulseDur = pulses > 0 ? cap / pulses : cap;
  return Math.round(Math.max(0, beatIndex) * pulseDur);
}

function pulseTolerance(model: VoiceModel, measureIndex: number): number {
  const ts = effectiveTimeSignature(model, measureIndex);
  const pulses = solfaPulseCount(ts.beats, ts.beatType);
  const cap = measureCapacity(ts.beats, ts.beatType, model.divisions || 1);
  const pulseDur = pulses > 0 ? cap / pulses : cap;
  return Math.max(1, Math.floor(pulseDur / 2));
}

function upsertDirectionAtOffset(
  measure: Measure,
  dir: MeasureDirection,
): void {
  const dirs = measure.directions ? [...measure.directions] : [];
  const offset = dir.offset ?? 0;
  const idx = dirs.findIndex(
    (d) =>
      d.kind === dir.kind &&
      (d.offset ?? 0) === offset &&
      (dir.kind !== "wedge" || d.number === dir.number) &&
      (dir.kind !== "dynamics" || d.value === dir.value),
  );
  if (idx >= 0) dirs[idx] = dir;
  else dirs.push(dir);
  measure.directions = dirs;
}

function removeDirectionAtOffset(
  measure: Measure,
  chip: BeatAnnotationChip,
): void {
  if (!measure.directions) return;
  measure.directions = measure.directions.filter((d) => {
    if ((d.offset ?? 0) !== chip.offset) return true;
    if (chip.kind === "dynamics" && d.kind === "dynamics") {
      return d.value !== chip.value;
    }
    if (chip.kind === "wedge" && d.kind === "wedge") {
      return d.value !== chip.value || d.number !== chip.number;
    }
    return true;
  });
  if (measure.directions.length === 0) delete measure.directions;
}

/** @deprecated Utiliser globalChipsForBeat. */
export function chipsForBeat(
  measure: Measure | undefined,
  model: VoiceModel,
  measureIndex: number,
  beatIndex: number,
): BeatAnnotationChip[] {
  return globalChipsForBeat(measure, model, measureIndex, beatIndex);
}

function nextWedgeNumber(measure: Measure): number {
  const nums = (measure.directions ?? [])
    .filter((d) => d.kind === "wedge" && d.number != null)
    .map((d) => d.number as number);
  return nums.length ? Math.max(...nums) + 1 : 1;
}

function applyAnnotationToVoice(
  voice: ScoreResult["voices"][number],
  measureIndex: number,
  beatIndex: number,
  payload: BeatAnnotationPayload,
): void {
  const model = voice.model;
  const measure = ensureMeasure(model, measureIndex);
  const offset = beatOffsetDivisions(model, measureIndex, beatIndex);

  switch (payload.id) {
    case "dynamics": {
      upsertDirectionAtOffset(measure, {
        offset,
        kind: "dynamics",
        value: payload.level,
        placement: "above",
      });
      break;
    }
    case "crescendo":
    case "diminuendo":
    case "wedge-stop": {
      const wedgeValue =
        payload.id === "crescendo"
          ? "crescendo"
          : payload.id === "diminuendo"
            ? "diminuendo"
            : "stop";
      upsertDirectionAtOffset(measure, {
        offset,
        kind: "wedge",
        value: wedgeValue,
        placement: "above",
        number: nextWedgeNumber(measure),
      });
      break;
    }
  }
}

export function applyBeatAnnotation(
  score: ScoreResult,
  voiceName: string,
  measureIndex: number,
  beatIndex: number,
  payload: BeatAnnotationPayload,
): ScoreResult {
  const next = cloneScore(score);
  for (const voice of next.voices) {
    applyAnnotationToVoice(voice, measureIndex, beatIndex, payload);
  }

  return next;
}

export function removeBeatAnnotationChip(
  score: ScoreResult,
  voiceName: string,
  measureIndex: number,
  chip: BeatAnnotationChip,
): ScoreResult {
  const next = cloneScore(score);
  const targets = isGlobalAnnotationChip(chip)
    ? next.voices
    : next.voices.filter((v) => v.name === voiceName);

  for (const voice of targets) {
    if (measureIndex >= voice.model.measures.length) continue;
    removeDirectionAtOffset(voice.model.measures[measureIndex], chip);
  }
  return next;
}
