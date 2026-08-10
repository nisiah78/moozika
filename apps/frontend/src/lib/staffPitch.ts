/** Mapping portée ⇄ hauteurs + labels solfège français. */

export type StaffClef = "treble" | "bass";

export interface AbsPitch {
  step: string;
  alter: number;
  octave: number;
}

/**
 * Options du dropdown — sol-fa tonique mouvable-do (degrés), pas le solfège fixe.
 * En tonalité A, `m` = C♯ (mi), pas « Do » fixe (= C → ma).
 */
export const SOLFEGE_OPTIONS = [
  { id: "rest", label: "Silence", kind: "rest" as const },
  { id: "d", label: "d — doh", kind: "note" as const, syllable: "d" },
  { id: "r", label: "r — ré", kind: "note" as const, syllable: "r" },
  { id: "m", label: "m — mi", kind: "note" as const, syllable: "m" },
  { id: "f", label: "f — fa", kind: "note" as const, syllable: "f" },
  { id: "s", label: "s — soh", kind: "note" as const, syllable: "s" },
  { id: "l", label: "l — lah", kind: "note" as const, syllable: "l" },
  { id: "t", label: "t — ti", kind: "note" as const, syllable: "t" },
] as const;

export type SolfegeOptionId = (typeof SOLFEGE_OPTIONS)[number]["id"];

const STEPS = ["C", "D", "E", "F", "G", "A", "B"] as const;

/** Index diatonique absolu (C0 = 0). */
export function pitchIndex(step: string, octave: number): number {
  const i = STEPS.indexOf(step.toUpperCase() as (typeof STEPS)[number]);
  if (i < 0) return octave * 7;
  return octave * 7 + i;
}

export function pitchFromIndex(index: number): AbsPitch {
  const octave = Math.floor(index / 7);
  let stepIdx = index % 7;
  if (stepIdx < 0) {
    stepIdx += 7;
  }
  return { step: STEPS[stepIdx], alter: 0, octave };
}

/** Position 0 = ligne du bas de la portée (5 lignes = 0,2,4,6,8). */
export function clefBottomIndex(clef: StaffClef): number {
  // Treble: ligne bas = E4 ; Bass: ligne bas = G2
  return clef === "bass" ? pitchIndex("G", 2) : pitchIndex("E", 4);
}

export function pitchToStaffPos(pitch: AbsPitch, clef: StaffClef): number {
  return pitchIndex(pitch.step, pitch.octave) - clefBottomIndex(clef);
}

export function staffPosToPitch(pos: number, clef: StaffClef): AbsPitch {
  return pitchFromIndex(clefBottomIndex(clef) + pos);
}

export function stepToSolfege(step: string): string {
  const map: Record<string, string> = {
    C: "Do",
    D: "Ré",
    E: "Mi",
    F: "Fa",
    G: "Sol",
    A: "La",
    B: "Si",
  };
  return map[step.toUpperCase()] ?? step;
}

/** Nombre de lignes supplémentaires nécessaires pour une position. */
export function ledgerLinesForPos(pos: number): { above: number; below: number } {
  // Portée : positions 0..8 (5 lignes). Hors plage = ledgers.
  let above = 0;
  let below = 0;
  if (pos > 8) {
    // positions 10,12,14… = lignes
    for (let p = 10; p <= pos; p += 2) above++;
  }
  if (pos < 0) {
    for (let p = -2; p >= pos; p -= 2) below++;
  }
  return { above, below };
}

export function maxLedgerNeeded(
  pitches: (AbsPitch | null)[],
  clef: StaffClef,
): { above: number; below: number } {
  let above = 0;
  let below = 0;
  for (const p of pitches) {
    if (!p) continue;
    const pos = pitchToStaffPos(p, clef);
    const n = ledgerLinesForPos(pos);
    above = Math.max(above, n.above);
    below = Math.max(below, n.below);
  }
  return { above, below };
}
