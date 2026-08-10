/**
 * Triolet sol-fa : 3 notes dans 1 ou 2 temps d'une même mesure.
 * Annotation visuelle — ne modifie pas la signature ni la validation rythmique.
 */

import type { ScoreResult, TripletMark, VoiceModel } from "@/lib/types";
import { cloneScore } from "@/lib/scoreEdit";

/** Rôle logique dans la grille (start/end = 2 temps fusionnés côté rendu). */
export type TripletRole = "single" | "start" | "end";

/** Rôle d'affichage du crochet (une seule barre centrée). */
export type TripletBracketRole = "single" | "pair";

export function beatsInMeasure(
  beatSchedule: number[],
  measureAbs: number,
): number {
  return (
    beatSchedule[Math.min(measureAbs, beatSchedule.length - 1)] ??
    beatSchedule[beatSchedule.length - 1] ??
    4
  );
}

/** Dernier temps de la mesure (0-based) — seul le triolet « 1 temps » est possible. */
export function isLastBeatOfMeasure(
  measureAbs: number,
  beatIndex: number,
  beatSchedule: number[],
): boolean {
  return beatIndex >= beatsInMeasure(beatSchedule, measureAbs) - 1;
}

export function canChooseTwoBeatTriplet(
  measureAbs: number,
  beatIndex: number,
  beatSchedule: number[],
): boolean {
  return beatIndex < beatsInMeasure(beatSchedule, measureAbs) - 1;
}

/** Durée couverte par le triolet à cette position (null si aucun). */
export function tripletSpanBeatsAt(
  triplets: TripletMark[] | undefined,
  measureAbs: number,
  beatIndex: number,
): 1 | 2 | null {
  const mark = findTripletContaining(triplets, measureAbs, beatIndex);
  if (!mark) return null;
  return mark.spanBeats ?? 1;
}

/** Fusionne deux cellules voisines en préparation d'un triolet sur 2 temps (`drm`). */
export function mergeTripletBeatRaw(a: string, b: string): string {
  const left = a.replace(/\s+/g, "").trim();
  const right = b.replace(/\s+/g, "").trim();
  if (!left) return right;
  if (!right) return left;
  return `${left}${right}`;
}

/** Après un triolet sur 2 temps, index du temps éditable suivant. */
export function beatIndexAfterTriplet(
  triplets: TripletMark[] | undefined,
  measureAbs: number,
  beatIndex: number,
): number {
  const mark = findTripletContaining(triplets, measureAbs, beatIndex);
  if (mark && (mark.spanBeats ?? 1) === 2 && mark.startBeat === beatIndex) {
    return beatIndex + 2;
  }
  return beatIndex + 1;
}

/** Vide la cellule compagnon d'un triolet sur 2 temps dans la grille. */
export function applyTripletToGrid(
  grid: string[][],
  measureAbs: number,
  beatIndex: number,
  spanBeats: 1 | 2,
): string[][] {
  const next = grid.map((row) => [...row]);
  while (next.length <= measureAbs) {
    next.push([]);
  }
  const row = next[measureAbs];
  if (spanBeats === 2) {
    const merged = mergeTripletBeatRaw(row[beatIndex] ?? "", row[beatIndex + 1] ?? "");
    row[beatIndex] = merged;
    row[beatIndex + 1] = "";
  }
  next[measureAbs] = row;
  return next;
}

/**
 * Ré-insère les slots compagnons des triolets 2 temps après un split `:`/`!`.
 * Notation `drm : f ! s` + triolet sur temps 0–1 → grille `[drm, "", f, s]`.
 */
export function expandGridSlotsForTriplets(
  grid: string[][],
  schedule: number[],
  triplets?: TripletMark[],
): string[][] {
  if (!triplets?.length) return grid;
  return grid.map((row, mi) => {
    const bpm =
      schedule[Math.min(mi, schedule.length - 1)] ??
      schedule[schedule.length - 1] ??
      4;
    const pairStarts = new Set(
      triplets
        .filter((t) => t.startMeasure === mi && (t.spanBeats ?? 1) === 2)
        .map((t) => t.startBeat),
    );
    if (pairStarts.size === 0) {
      const padded = [...row];
      while (padded.length < bpm) padded.push("");
      return padded.slice(0, bpm);
    }
    const src = [...row];
    let si = 0;
    const out: string[] = [];
    for (let bi = 0; bi < bpm; bi++) {
      if ([...pairStarts].some((start) => start + 1 === bi)) {
        out.push("");
        continue;
      }
      out.push(src[si] ?? "");
      si++;
    }
    return out;
  });
}

/** Slots de grille couverts par le triolet (le contenu est dans le premier slot). */
export function tripletCoveredBeats(mark: TripletMark): number[] {
  const span = mark.spanBeats ?? 1;
  return Array.from({ length: span }, (_, i) => mark.startBeat + i);
}

export function findTripletContaining(
  triplets: TripletMark[] | undefined,
  measureAbs: number,
  beatIndex: number,
): TripletMark | undefined {
  if (!triplets?.length) return undefined;
  return triplets.find(
    (t) =>
      t.startMeasure === measureAbs &&
      tripletCoveredBeats(t).includes(beatIndex),
  );
}

export function tripletBracketRoleAt(
  triplets: TripletMark[] | undefined,
  measureAbs: number,
  beatIndex: number,
): TripletBracketRole | null {
  const role = tripletRoleAt(triplets, measureAbs, beatIndex);
  if (role === "start") return "pair";
  if (role === "single") return "single";
  return null;
}

export function isTripletPairContinuation(
  triplets: TripletMark[] | undefined,
  measureAbs: number,
  beatIndex: number,
): boolean {
  return tripletRoleAt(triplets, measureAbs, beatIndex) === "end";
}

export function tripletRoleAt(
  triplets: TripletMark[] | undefined,
  measureAbs: number,
  beatIndex: number,
): TripletRole | null {
  const mark = findTripletContaining(triplets, measureAbs, beatIndex);
  if (!mark) return null;
  const span = mark.spanBeats ?? 1;
  if (span === 1) return "single";
  if (beatIndex === mark.startBeat) return "start";
  if (beatIndex === mark.startBeat + 1) return "end";
  return null;
}

/** Masquer « : » / « ! » entre deux temps d'un triolet sur 2 temps. */
export function hideBeatSeparatorAfter(
  triplets: TripletMark[] | undefined,
  measureAbs: number,
  beatIndex: number,
): boolean {
  if (!triplets?.length) return false;
  return triplets.some(
    (t) =>
      t.startMeasure === measureAbs &&
      (t.spanBeats ?? 1) === 2 &&
      t.startBeat === beatIndex,
  );
}

function beatsOverlap(a: TripletMark, b: TripletMark): boolean {
  if (a.startMeasure !== b.startMeasure) return false;
  const sa = new Set(tripletCoveredBeats(a));
  return tripletCoveredBeats(b).some((b) => sa.has(b));
}

export function removeTripletAt(
  score: ScoreResult,
  voiceName: string,
  measureAbs: number,
  beatIndex: number,
): ScoreResult {
  const next = cloneScore(score);
  const voice = next.voices.find((v) => v.name === voiceName);
  if (!voice) return next;
  const existing = findTripletContaining(voice.model.triplets, measureAbs, beatIndex);
  if (!existing) return next;
  voice.model.triplets = (voice.model.triplets ?? []).filter(
    (t) => t.id !== existing.id,
  );
  return next;
}

export function applyTriplet(
  score: ScoreResult,
  voiceName: string,
  measureAbs: number,
  beatIndex: number,
  spanBeats: 1 | 2,
  beatSchedule: number[],
): ScoreResult {
  const next = cloneScore(score);
  const voice = next.voices.find((v) => v.name === voiceName);
  if (!voice) return next;

  if (spanBeats === 2 && !canChooseTwoBeatTriplet(measureAbs, beatIndex, beatSchedule)) {
    spanBeats = 1;
  }

  const mark: TripletMark = {
    id: `t-${measureAbs}-${beatIndex}-${spanBeats}-${Date.now()}`,
    startMeasure: measureAbs,
    startBeat: beatIndex,
    spanBeats,
  };

  const prev = voice.model.triplets ?? [];
  voice.model.triplets = [
    ...prev.filter((t) => !beatsOverlap(t, mark)),
    mark,
  ];
  return next;
}

/** Clic + : retire si déjà triolet, sinon indique s'il faut choisir le span. */
export function tripletPlusAction(
  triplets: TripletMark[] | undefined,
  measureAbs: number,
  beatIndex: number,
  beatSchedule: number[],
): "remove" | "pick" | "apply-one" {
  if (findTripletContaining(triplets, measureAbs, beatIndex)) return "remove";
  if (isLastBeatOfMeasure(measureAbs, beatIndex, beatSchedule)) return "apply-one";
  return "pick";
}

export function beatScheduleForVoice(
  model: VoiceModel,
  measureCount: number,
): number[] {
  let beats = model.timeSignature.beats;
  let beatType = model.timeSignature.beatType;
  const out: number[] = [];
  const n = Math.max(1, measureCount);
  for (let i = 0; i < n; i++) {
    const ts = model.measures[i]?.timeSignature;
    if (ts) {
      beats = ts.beats;
      beatType = ts.beatType;
    }
    if (beatType === 8 && (beats === 5 || beats === 6 || beats === 10)) {
      out.push(beats);
    } else if (
      (beatType === 8 || beatType === 16) &&
      beats % 3 === 0 &&
      beats > 3
    ) {
      out.push(beats / 3);
    } else {
      out.push(beats);
    }
  }
  return out;
}
