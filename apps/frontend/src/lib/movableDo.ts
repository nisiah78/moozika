/**
 * Sol-fa tonique mouvable-do (miroir de apps/omr-service/app/solfa/keys.py).
 * Syllabes relatives à la tonique → hauteur absolue et inverse.
 */

import type { AbsPitch } from "@/lib/staffPitch";

const LETTERS = ["C", "D", "E", "F", "G", "A", "B"] as const;

const TONIC_MAP: Record<string, { letter: string; fifths: number }> = {
  C: { letter: "C", fifths: 0 },
  G: { letter: "G", fifths: 1 },
  D: { letter: "D", fifths: 2 },
  A: { letter: "A", fifths: 3 },
  E: { letter: "E", fifths: 4 },
  B: { letter: "B", fifths: 5 },
  "F#": { letter: "F", fifths: 6 },
  "C#": { letter: "C", fifths: 7 },
  F: { letter: "F", fifths: -1 },
  Bb: { letter: "B", fifths: -2 },
  Eb: { letter: "E", fifths: -3 },
  Ab: { letter: "A", fifths: -4 },
  Db: { letter: "D", fifths: -5 },
  Gb: { letter: "G", fifths: -6 },
  Cb: { letter: "C", fifths: -7 },
};

const SHARP_ORDER = ["F", "C", "G", "D", "A", "E", "B"];
const FLAT_ORDER = ["B", "E", "A", "D", "G", "C", "F"];

const DIATONIC: Record<string, number> = {
  d: 1,
  r: 2,
  m: 3,
  f: 4,
  s: 5,
  l: 6,
  t: 7,
};

const CHROMATIC: Record<string, [number, number]> = {
  di: [1, 1],
  de: [1, 1],
  ri: [2, 1],
  fi: [4, 1],
  fe: [4, 1],
  si: [5, 1],
  se: [5, 1],
  li: [6, 1],
  ra: [2, -1],
  ma: [3, -1],
  sa: [5, -1],
  la: [6, -1],
  lo: [6, -1],
  ta: [7, -1],
};

const DIATONIC_REVERSE: Record<number, string> = {
  1: "d",
  2: "r",
  3: "m",
  4: "f",
  5: "s",
  6: "l",
  7: "t",
};

const CHROMATIC_REVERSE: Record<string, string> = {
  "1:+1": "di",
  "2:+1": "ri",
  "4:+1": "fi",
  "5:+1": "si",
  "6:+1": "li",
  "2:-1": "ra",
  "3:-1": "ma",
  "5:-1": "sa",
  "6:-1": "la",
  "7:-1": "ta",
};

/** Enharmonie : (syllabe, bump d'octave). */
const ENHARMONIC_REVERSE: Record<string, [string, number]> = {
  "3:+1": ["f", 0],
  "7:+1": ["d", 1],
  "1:-1": ["t", -1],
  "4:-1": ["m", 0],
};

export function normalizeTonic(tonic: string): string {
  let t = tonic.trim().replace(/♯/g, "#").replace(/♭/g, "b");
  if (!t) throw new Error("tonique vide");
  t = t[0].toUpperCase() + t.slice(1).toLowerCase();
  if (!(t in TONIC_MAP)) throw new Error(`tonique inconnue: ${tonic}`);
  return t;
}

export function fifthsOf(tonic: string): number {
  return TONIC_MAP[normalizeTonic(tonic)].fifths;
}

/** Toniques supportées (ordre quintes croissantes puis bémols). */
export const TONIC_OPTIONS = Object.keys(TONIC_MAP);

function alteredLetters(fifths: number): Record<string, number> {
  const out: Record<string, number> = {};
  if (fifths > 0) {
    for (const letter of SHARP_ORDER.slice(0, fifths)) out[letter] = 1;
  } else if (fifths < 0) {
    for (const letter of FLAT_ORDER.slice(0, -fifths)) out[letter] = -1;
  }
  return out;
}

export type ResolvedPitch = AbsPitch & { syllable: string };

/** Syllabe sol-fa → hauteur absolue (mouvable-do). */
export function resolvePitch(
  core: string,
  octaveShift: number,
  tonic: string,
  dohOctave = 4,
): ResolvedPitch {
  const key = normalizeTonic(tonic);
  const { letter: tonicLetter, fifths } = TONIC_MAP[key];
  const keyAlter = alteredLetters(fifths);
  const c = core.toLowerCase();

  let degree: number;
  let delta: number;
  if (c in DIATONIC) {
    degree = DIATONIC[c];
    delta = 0;
  } else if (c in CHROMATIC) {
    [degree, delta] = CHROMATIC[c];
  } else {
    throw new Error(`syllabe sol-fa inconnue: ${core}`);
  }

  const tonicIndex = LETTERS.indexOf(tonicLetter as (typeof LETTERS)[number]);
  const letter = LETTERS[(tonicIndex + degree - 1) % 7];
  const alter = (keyAlter[letter] ?? 0) + delta;
  const tonicPosition = dohOctave * 7 + tonicIndex;
  const position = tonicPosition + (degree - 1) + 7 * octaveShift;
  const octave = Math.floor(position / 7);

  return { step: letter, alter, octave, syllable: c };
}

/** Hauteur absolue → syllabe sol-fa (core + octave_shift). */
export function syllableOfPitch(
  step: string,
  alter: number,
  octave: number,
  tonic: string,
  dohOctave = 4,
): { core: string; octaveShift: number } {
  const key = normalizeTonic(tonic);
  const { letter: tonicLetter, fifths } = TONIC_MAP[key];
  const keyAlter = alteredLetters(fifths);
  const s = step.toUpperCase();
  const tonicIndex = LETTERS.indexOf(tonicLetter as (typeof LETTERS)[number]);
  const letterIndex = LETTERS.indexOf(s as (typeof LETTERS)[number]);
  if (letterIndex < 0) throw new Error(`lettre invalide: ${step}`);

  // Modulo positif (en JS `-4 % 7 === -4`, contrairement à Python)
  const degree = ((((letterIndex - tonicIndex) % 7) + 7) % 7) + 1;
  const delta = alter - (keyAlter[s] ?? 0);
  const keyDelta = `${degree}:${delta >= 0 ? "+" : ""}${delta}`;

  let core: string;
  let octaveBump = 0;
  if (delta === 0) {
    core = DIATONIC_REVERSE[degree];
  } else if (keyDelta in CHROMATIC_REVERSE) {
    core = CHROMATIC_REVERSE[keyDelta];
  } else if (keyDelta in ENHARMONIC_REVERSE) {
    [core, octaveBump] = ENHARMONIC_REVERSE[keyDelta];
  } else {
    throw new Error(`altération non représentable (degré ${degree}, delta ${delta})`);
  }

  const tonicPosition = dohOctave * 7 + tonicIndex;
  const position = octave * 7 + letterIndex;
  const octaveShift =
    Math.floor((position - tonicPosition - (degree - 1)) / 7) + octaveBump;

  return { core, octaveShift };
}

/** Choisit l'octave_shift qui place la syllabe le plus près de `near`. */
export function pitchForSyllableNear(
  core: string,
  near: AbsPitch,
  tonic: string,
  dohOctave = 4,
): ResolvedPitch {
  const nearIdx = near.octave * 7 + LETTERS.indexOf(near.step.toUpperCase() as (typeof LETTERS)[number]);
  let best = resolvePitch(core, 0, tonic, dohOctave);
  let bestDist = Infinity;
  for (let sh = -3; sh <= 3; sh++) {
    const p = resolvePitch(core, sh, tonic, dohOctave);
    const idx = p.octave * 7 + LETTERS.indexOf(p.step as (typeof LETTERS)[number]);
    const dist = Math.abs(idx - nearIdx);
    if (dist < bestDist) {
      bestDist = dist;
      best = p;
    }
  }
  return best;
}

export function withOctaveMarks(core: string, octaveShift: number): string {
  if (octaveShift > 0) return core + "'".repeat(octaveShift);
  if (octaveShift < 0) return core + ",".repeat(-octaveShift);
  return core;
}
