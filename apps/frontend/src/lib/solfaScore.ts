/**
 * Mise en page sol-fa tonique (style recueils malgaches).
 * Aligne les voix d'un système colonne par colonne pour que | : ! restent
 * verticaux, comme sur une feuille typographiée.
 */

import type { ScoreResult, Voice } from "./types";
import {
  beatScheduleForModel,
  solfaPulseCount,
} from "./measureDirectives";

export const MEASURES_PER_SYSTEM = 4;

/** Au-delà de 6 temps/mesure, moins de mesures par ligne pour garder les notes lisibles. */
export function measuresPerSystemFor(beatsPerMeasure: number): number {
  return beatsPerMeasure >= 6 ? 3 : MEASURES_PER_SYSTEM;
}

/**
 * Mise en page à l'impression : la page a une largeur fixe (pas de défilement
 * horizontal comme à l'écran), donc on resserre le nombre de mesures par ligne
 * quand chaque mesure compte beaucoup de cellules, sinon les notes s'entassent.
 * Le critère est le nombre de temps/cellules par mesure (`solfaPulseCount`) :
 *   ≥ 10 → 2 mesures/système · 4-9 → 3 · ≤ 3 → 4.
 */
export function printMeasuresPerSystemFor(beatsPerMeasure: number): number {
  if (beatsPerMeasure >= 10) return 2;
  if (beatsPerMeasure >= 4) return 3;
  return MEASURES_PER_SYSTEM;
}

export interface SolfaBeat {
  raw: string;
  /** Affichage (espaces pour silences). */
  text: string;
}

export interface SolfaMeasure {
  beats: SolfaBeat[];
}

export interface SolfaVoiceLine {
  name: string;
  measures: SolfaMeasure[];
  /** True si la ligne n'a que des silences sur ce système. */
  isRestOnly: boolean;
}

export interface SolfaSystem {
  startNumber: number;
  voices: SolfaVoiceLine[];
  /** Largeurs max par (mesure, temps) pour aligner les colonnes. */
  colWidths: number[][];
}

function splitBeats(measure: string): string[] {
  return measure.split(/[:!]/).map((b) => b.trim());
}

/** Retire les annotations de mesure émises par to_solfa : (6/8), (Doh=F), [D.C.]… */
export function stripMeasureAnnotations(raw: string): string {
  let s = raw.trim();
  let prev = "";
  while (s !== prev) {
    prev = s;
    s = s.replace(/^\([^)]*\)\s*/, "").replace(/^\[[^\]]*\]\s*/, "").trim();
  }
  return s;
}

function isRestOnlyMeasure(beats: string[]): boolean {
  // Silences purs (vides). Les tenues « - » seules sans note
  // comptent comme silence de grille dans l'intro.
  return beats.every((b) => b === "" || (/^[\s\-]*$/.test(b) && !/[a-zA-Z]/.test(b)));
}

function parseVoiceMeasures(notation: string): string[][] {
  return notation
    .split("|")
    .map((m) => splitBeats(stripMeasureAnnotations(m)))
    .filter((beats) => beats.length > 0);
}

function padBeats(beats: string[], n: number): string[] {
  const out = beats.slice(0, n);
  while (out.length < n) out.push("");
  return out;
}

function beatDisplay(raw: string): string {
  return raw === "" ? "" : raw;
}

/**
 * Separators intra-mesure : en 4/4 traditionnel, « ! » marque la mi-mesure.
 * Ex. ``m : - ! - : .m``.
 */
export function formatMeasureBeats(
  beats: SolfaBeat[],
  widths: number[],
  beatsPerMeasure: number,
): string {
  const parts: string[] = [];
  for (let i = 0; i < beats.length; i++) {
    const w = widths[i] ?? 1;
    const text = beats[i].text.padEnd(w, " ");
    parts.push(text);
    if (i < beats.length - 1) {
      const mid = beatsPerMeasure > 0 && i + 1 === Math.floor(beatsPerMeasure / 2);
      parts.push(mid ? " ! " : " : ");
    }
  }
  return parts.join("");
}

/** Schedule de pulsations sol-fa pour chaque mesure du score. */
export function beatScheduleForScore(
  result: ScoreResult,
  measureCount: number,
): number[] {
  const model = result.voices[0]?.model;
  if (model && model.measures.length > 0) {
    return beatScheduleForModel(model, measureCount);
  }
  const { beats, beatType } = result.header.timeSignature;
  const pulses = solfaPulseCount(beats || 4, beatType || 4);
  return Array.from({ length: Math.max(1, measureCount) }, () => pulses);
}

export function buildSolfaSystems(
  result: ScoreResult,
  measuresPerSystem?: number,
): SolfaSystem[] {
  const headerBeats = result.header.timeSignature.beats || 4;
  const headerBeatType = result.header.timeSignature.beatType || 4;
  const headerPulses = solfaPulseCount(headerBeats, headerBeatType);
  const mps = measuresPerSystem ?? measuresPerSystemFor(headerPulses);
  const parsed = result.voices.map((v) => parseVoiceMeasures(v.notation));
  const nMeasures = Math.max(0, ...parsed.map((p) => p.length));
  if (nMeasures === 0) return [];

  const schedule = beatScheduleForScore(result, nMeasures);
  const entered = result.voices.map(() => false);
  const systems: SolfaSystem[] = [];

  for (let start = 0; start < nMeasures; start += mps) {
    const end = Math.min(start + mps, nMeasures);
    const span = end - start;

    const voiceLines: SolfaVoiceLine[] = result.voices.map((v: Voice, vi) => {
      const measures: SolfaMeasure[] = [];
      for (let i = 0; i < span; i++) {
        const abs = start + i;
        const bpm = schedule[abs] ?? headerPulses;
        const rawBeats = padBeats(parsed[vi][abs] ?? [], bpm);
        measures.push({
          beats: rawBeats.map((raw) => ({ raw, text: beatDisplay(raw) })),
        });
      }
      const isRestOnly = measures.every((m) =>
        isRestOnlyMeasure(m.beats.map((b) => b.raw)),
      );
      if (!isRestOnly) entered[vi] = true;
      return { name: v.name, measures, isRestOnly };
    });

    // Intro : soprano seul. Dès qu'une voix a chanté, on garde sa ligne
    // (barres vides si silence) pour coller au layout SATB du recueil.
    // Une voix ajoutée par divisi (enterMeasure) apparaît dès le système qui
    // atteint sa mesure d'entrée, même si elle est encore silencieuse.
    const visible = voiceLines.filter((vl, i) => {
      if (i === 0 || entered[i]) return true;
      const enter = result.voices[i]?.model?.enterMeasure;
      return enter != null && enter < end;
    });

    const colWidths: number[][] = Array.from({ length: span }, (_, mi) => {
      const bpm = schedule[start + mi] ?? headerPulses;
      return Array.from({ length: bpm }, (_, bi) =>
        Math.max(1, ...visible.map((vl) => vl.measures[mi].beats[bi]?.text.length ?? 1)),
      );
    });

    systems.push({
      startNumber: start + 1,
      voices: visible,
      colWidths,
    });
  }

  return systems;
}
