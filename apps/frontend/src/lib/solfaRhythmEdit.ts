/**
 * Rythme sol-fa (édition) :
 * - chaque cellule = exactement 1 temps ;
 * - le surplus cascade au temps suivant (et ainsi de suite) ;
 * - temps incomplet / invalide → surlignage erreur.
 *
 * Unité = 1/4 de temps (beatDiv=4 en mesure simple).
 */

import type { TripletMark } from "@/lib/types";
import { isTripletPairContinuation, tripletSpanBeatsAt } from "@/lib/triplets";

const BEAT_DIV = 4;

const ATOM_ONE = /^(-|_|0|[drmfslt](?:[aei])?(?:'+|,+|_*)?)$/i;

export function beatDivisionsFor(beatType: number, beats: number): number {
  if (beatType === 8 && (beats === 5 || beats === 6 || beats === 10)) return 2;
  // /16 : pulsation = 1 double-croche, pas de subdivision plus fine (métrique
  // variable des fihirana : 5/16, 7/16, 12/16…).
  if (beatType === 16) return 1;
  if (beatType === 8 && beats % 3 === 0 && beats > 3) return 6;
  return BEAT_DIV;
}

export type BeatFill = {
  units: number;
  beatDiv: number;
  status: "ok" | "under" | "over" | "invalid";
};

/** Split `,` rythmiques (pas les `,` d'octave). */
function splitRhythmCommas(half: string): string[] {
  const parts: string[] = [];
  let cur = "";
  for (let i = 0; i < half.length; i++) {
    const c = half[i];
    if (c === ",") {
      const prev = cur.trim();
      if (/[drmfslt](?:[aei])?(?:'+|,*|_*)$/i.test(prev) && !prev.includes(" ")) {
        const rest = half.slice(i + 1);
        if (/^\s*[drmfslt0\-]/i.test(rest) && !/^,+/.test(rest)) {
          parts.push(cur);
          cur = "";
          continue;
        }
        cur += c;
        continue;
      }
      parts.push(cur);
      cur = "";
      continue;
    }
    cur += c;
  }
  parts.push(cur);
  return parts.length ? parts : [""];
}

/**
 * Remplissage d'un temps. Une note seule (`d`) = 1 temps OK.
 * Trop de subdivisions / atomes collés = over ou invalid.
 */
export function analyzeBeatFill(raw: string, beatDiv = BEAT_DIV): BeatFill {
  const text = raw.replace(/\s+/g, " ").trim();
  if (text === "") {
    return { units: beatDiv, beatDiv, status: "ok" };
  }

  // Plusieurs tokens séparés par espace → trop pour une cellule
  if (/\s/.test(text)) {
    const parts = text.split(/\s+/).filter(Boolean);
    return {
      units: parts.length * beatDiv,
      beatDiv,
      status: parts.length > 1 ? "over" : "ok",
    };
  }

  const compact = text.replace(/\s+/g, "");

  // Notes collées sans séparateur : `d` (1 temps), `dd` (2 croches), `dddd`
  // (4 doubles-croches). La JUXTAPOSITION = subdivision égale du temps (convention
  // sol-fa sans espace), pas un dépassement.
  if (!compact.includes(".") && !hasRhythmComma(compact)) {
    const atoms = extractGluedAtoms(compact);
    if (atoms.length === 0) {
      if (!ATOM_ONE.test(compact) && compact !== "-") {
        return { units: 0, beatDiv, status: "invalid" };
      }
      return { units: beatDiv, beatDiv, status: "ok" };
    }
    const n = atoms.length;
    if (n === 1 || beatDiv % n === 0) {
      return { units: beatDiv, beatDiv, status: "ok" };
    }
    return { units: n * beatDiv, beatDiv, status: "over" };
  }

  // Structure . / ,
  try {
    const halves = compact.split(".");
    let total = 0;
    let invalid = false;
    const halfSize = beatDiv / halves.length;
    if (!Number.isInteger(halfSize)) invalid = true;

    for (const half of halves) {
      const quarters = splitRhythmCommas(half);
      const qSize = halfSize / quarters.length;
      if (!Number.isInteger(qSize) && quarters.length > 1) invalid = true;
      for (const q of quarters) {
        const tok = q.trim();
        if (tok === "" || tok === "-" || tok === "_" || tok === "0") {
          total += Math.max(1, Math.round(Number.isFinite(qSize) ? qSize : 1));
          continue;
        }
        // Notes JUXTAPOSÉES dans un quart (`dd`) = sous-cellules égales (2
        // double-croches), pas une cellule invalide.
        const atoms = extractGluedAtoms(tok);
        if (atoms.length === 0) {
          invalid = true;
          total += Math.max(1, Math.round(Number.isFinite(qSize) ? qSize : 1));
          continue;
        }
        const aSize = qSize / atoms.length;
        if (!Number.isInteger(aSize) && atoms.length > 1) invalid = true;
        for (let a = 0; a < atoms.length; a++) {
          total += Math.max(1, Math.round(Number.isFinite(aSize) ? aSize : 1));
        }
      }
    }

    if (invalid) return { units: total, beatDiv, status: "invalid" };
    if (total < beatDiv) return { units: total, beatDiv, status: "under" };
    if (total > beatDiv) return { units: total, beatDiv, status: "over" };
    return { units: total, beatDiv, status: "ok" };
  } catch {
    return { units: 0, beatDiv, status: "invalid" };
  }
}

const TRIPLET_SYLLABLE = /^(-|_|0|[drmfslt](?:[aei])?(?:'+|,+|_*)?)$/i;

/**
 * Validation d'une cellule triolet : 3 notes collées, sans `:` / `.` rythmique.
 * Format attendu : `drm` (ex. dans une mesure `| drm : s ! l : t |`).
 * Jamais de cascade / auto-correction — seuls ok / under / over / invalid.
 */
export function analyzeTripletFill(
  raw: string,
  spanBeats: 1 | 2,
  beatDiv = BEAT_DIV,
): BeatFill {
  const capacity = spanBeats * beatDiv;
  const trimmed = raw.replace(/\s+/g, " ").trim();
  if (trimmed === "") {
    return { units: capacity, beatDiv: capacity, status: "ok" };
  }

  // Espaces, points rythmiques ou virgules séparatrices → format invalide
  if (/\s/.test(trimmed) || trimmed.includes(".")) {
    return { units: 0, beatDiv: capacity, status: "invalid" };
  }

  const compact = trimmed.replace(/\s+/g, "");
  const atoms = extractGluedAtoms(compact);
  if (
    atoms.length === 3 &&
    atoms.every((a) => TRIPLET_SYLLABLE.test(a))
  ) {
    return { units: capacity, beatDiv: capacity, status: "ok" };
  }
  if (atoms.length === 0) {
    return { units: 0, beatDiv: capacity, status: "invalid" };
  }
  if (atoms.length < 3) {
    return { units: atoms.length, beatDiv: capacity, status: "under" };
  }
  return { units: atoms.length, beatDiv: capacity, status: "over" };
}

function hasRhythmComma(compact: string): boolean {
  // virgule rythmique si elle sépare deux cellules (ex. d,r) pas seulement octave (d,)
  return /[drmfslt0\-](?:'+|_*),(?:[drmfslt0\-])/i.test(compact);
}

/** Extrait les atomes d'une chaîne collée (-d, d-r, drm…). */
export function extractGluedAtoms(compact: string): string[] {
  const s = compact.replace(/\s+/g, "");
  if (!s) return [];
  const out: string[] = [];
  const re = /(-|_|0|[drmfslt](?:[aei])?(?:'+|,+|_*)?)/gi;
  let m: RegExpExecArray | null;
  let last = 0;
  while ((m = re.exec(s))) {
    if (m.index > last) {
      // bruit entre atomes
      const gap = s.slice(last, m.index);
      if (gap.trim()) return []; // invalide
    }
    out.push(m[1]);
    last = m.index + m[0].length;
  }
  if (last !== s.length) return [];
  return out;
}

function formatDotBeat(left: string, right: string): string {
  if (!left && !right) return "";
  if (!left) return `.${right}`;
  // Préserver le `.` final : `-.` (tenue + silence) et `m.` (note + prolongation)
  if (!right) return `${left}.`;
  return `${left}.${right}`;
}

/**
 * Sépare uniquement le surplus d'un temps (notes en trop) en cellules
 * successives. Ne complète jamais un temps incomplet avec `-` ou des
 * silences inventés — conforme à solfa-format.md §3 (manque → vide / erreur).
 *
 * Ex. `-.ds,` → `-.d` + `s,` ; `drm` → `d` + `r` + `m` ; `d.r.m` → `d.r` + `m`.
 */
export function splitBeatSurplus(raw: string, beatDiv = BEAT_DIV): string[] {
  const text = raw.replace(/\s+/g, " ").trim();
  if (text === "") return [""];

  const fill = analyzeBeatFill(text, beatDiv);
  // OK ou incomplet : on ne touche pas (pas de « réparation » inventée)
  if (fill.status === "ok" || fill.status === "under") {
    return [text];
  }

  // Tokens séparés par espace → chacun est un temps (ou à resplitter)
  if (/\s/.test(text)) {
    return text.split(/\s+/).filter(Boolean).flatMap((t) => splitBeatSurplus(t, beatDiv));
  }

  const compact = text.replace(/\s+/g, "");

  // Atomes collés sans . / virgule rythmique : drm, -d, ds,
  if (!compact.includes(".") && !hasRhythmComma(compact)) {
    const atoms = extractGluedAtoms(compact);
    if (atoms.length > 1) {
      return atoms.map((a) => (a === "_" ? "-" : a));
    }
    return [text];
  }

  if (compact.includes(".")) {
    const halves = compact.split(".");

    // Plus d'un `.` → un seul `.` par temps (spec) : paires successives
    if (halves.length > 2) {
      const beats: string[] = [];
      for (let i = 0; i < halves.length; i += 2) {
        if (i + 1 < halves.length) {
          beats.push(formatDotBeat(halves[i], halves[i + 1]));
        } else {
          // demi orphelin : laisser tel quel (under), ne pas inventer de paire
          beats.push(halves[i]);
        }
      }
      return beats.flatMap((b) => splitBeatSurplus(b, beatDiv));
    }

    // Exactement un `.` mais temps over/invalid : surplus collé dans un demi
    if (halves.length === 2) {
      const [left, right] = halves;
      const rightAtoms = extractGluedAtoms(right);
      if (rightAtoms.length > 1) {
        const firstBeat = formatDotBeat(left, rightAtoms[0]);
        if (analyzeBeatFill(firstBeat, beatDiv).status !== "over") {
          const rest = rightAtoms.slice(1).map((a) => (a === "_" ? "-" : a));
          return [firstBeat, ...rest.flatMap((r) => splitBeatSurplus(r, beatDiv))];
        }
      }
      const leftAtoms = extractGluedAtoms(left);
      if (leftAtoms.length > 1) {
        const first = leftAtoms[0] === "_" ? "-" : leftAtoms[0];
        const restLeft = leftAtoms
          .slice(1)
          .map((a) => (a === "_" ? "-" : a))
          .join("");
        const remainder = restLeft
          ? formatDotBeat(restLeft, right)
          : right
            ? formatDotBeat("", right)
            : "";
        const tail = remainder ? splitBeatSurplus(remainder, beatDiv) : [];
        return [first, ...tail];
      }
    }
  }

  // Virgules rythmiques sans `.` : plus de 4 quarts → groupes de 4
  if (hasRhythmComma(compact) && !compact.includes(".")) {
    const qs = splitRhythmCommas(compact).map((q) => q.trim());
    if (qs.length > 4) {
      const beats: string[] = [];
      for (let i = 0; i < qs.length; i += 4) {
        const chunk = qs.slice(i, i + 4);
        if (chunk.length === 4) {
          beats.push(`${chunk[0]},${chunk[1]}.${chunk[2]},${chunk[3]}`);
        } else {
          beats.push(chunk.join(","));
        }
      }
      return beats.flatMap((b) => splitBeatSurplus(b, beatDiv));
    }
  }

  // Invalide non séparable → laisser pour surlignage
  return [text];
}

export type BeatSchedule = number | number[];

/** Normalise en tableau de longueurs de mesures (prolonge le dernier mètre). */
export function resolveBeatSchedule(
  beatsPerMeasure: BeatSchedule,
  measureCount: number,
): number[] {
  const n = Math.max(1, measureCount);
  if (typeof beatsPerMeasure === "number") {
    return Array.from({ length: n }, () => beatsPerMeasure);
  }
  if (beatsPerMeasure.length === 0) {
    return Array.from({ length: n }, () => 4);
  }
  const out = beatsPerMeasure.slice(0, n);
  const last = out[out.length - 1] ?? 4;
  while (out.length < n) out.push(last);
  return out;
}

function beatCountAt(schedule: number[], measureIndex: number): number {
  if (schedule.length === 0) return 4;
  if (measureIndex < schedule.length) return schedule[measureIndex];
  return schedule[schedule.length - 1];
}

function flattenGrid(grid: string[][], beatsPerMeasure: BeatSchedule): string[] {
  const schedule = resolveBeatSchedule(beatsPerMeasure, grid.length);
  const flat: string[] = [];
  for (let mi = 0; mi < grid.length; mi++) {
    const bpm = beatCountAt(schedule, mi);
    const r = [...(grid[mi] ?? [])];
    while (r.length < bpm) r.push("");
    flat.push(...r.slice(0, bpm));
  }
  return flat;
}

function chunkBeats(flat: string[], beatsPerMeasure: BeatSchedule): string[][] {
  const seed =
    typeof beatsPerMeasure === "number"
      ? [beatsPerMeasure]
      : beatsPerMeasure.length
        ? [...beatsPerMeasure]
        : [4];
  const copy = [...flat];
  const grid: string[][] = [];
  let i = 0;
  let mi = 0;
  while (i < copy.length) {
    const bpm = beatCountAt(seed, mi);
    while (copy.length < i + bpm) copy.push("");
    grid.push(copy.slice(i, i + bpm));
    i += bpm;
    mi++;
  }
  while (
    grid.length > 1 &&
    grid[grid.length - 1].every((b) => b.trim() === "")
  ) {
    grid.pop();
  }
  return grid.length ? grid : [Array.from({ length: seed[0] }, () => "")];
}

function flatIndex(
  measureIndex: number,
  beatIndex: number,
  schedule: number[],
): number {
  let idx = 0;
  for (let i = 0; i < measureIndex; i++) idx += beatCountAt(schedule, i);
  return idx + beatIndex;
}

function unflatIndex(
  idx: number,
  schedule: number[],
): { measure: number; beat: number } {
  let remaining = idx;
  let mi = 0;
  for (;;) {
    const bpm = beatCountAt(schedule, mi);
    if (remaining < bpm) return { measure: mi, beat: remaining };
    remaining -= bpm;
    mi++;
  }
}

function resolveBeatDiv(
  beatDiv: number | number[],
  measureIndex: number,
): number {
  if (typeof beatDiv === "number") return beatDiv;
  if (beatDiv.length === 0) return BEAT_DIV;
  if (measureIndex < beatDiv.length) return beatDiv[measureIndex];
  return beatDiv[beatDiv.length - 1];
}

/**
 * Cascade horizontale au blur : sépare le surplus de chaque cellule et
 * décale vers la droite. Identité sur une partition déjà valide.
 * Ne réécrit pas les tenues / ne complète pas les temps incomplets.
 *
 * Les cellules marquées triolet sont laissées intactes (pas de split `drm` → d|r|m).
 *
 * `beatsPerMeasure` / `beatDiv` peuvent être des tableaux (mètre variable).
 */
export function normalizeGridCascade(
  grid: string[][],
  beatsPerMeasure: BeatSchedule,
  beatDiv: number | number[] = BEAT_DIV,
  triplets?: TripletMark[],
): string[][] {
  const schedule = resolveBeatSchedule(beatsPerMeasure, grid.length);
  const flat = flattenGrid(grid, schedule);
  const out: string[] = [];
  let cursor = 0;
  for (let mi = 0; mi < schedule.length; mi++) {
    const bpm = schedule[mi];
    const div = resolveBeatDiv(beatDiv, mi);
    for (let bi = 0; bi < bpm; bi++) {
      const beat = flat[cursor] ?? "";
      cursor++;
      // Triolet : jamais d'auto-correction / cascade sur la cellule ni son compagnon.
      if (
        tripletSpanBeatsAt(triplets, mi, bi) != null ||
        isTripletPairContinuation(triplets, mi, bi)
      ) {
        out.push(beat);
        continue;
      }
      out.push(...splitBeatSurplus(beat, div));
    }
  }
  // Surplus au-delà du schedule initial (mesures ajoutées à l'édition)
  while (cursor < flat.length) {
    const mi = schedule.length - 1;
    out.push(...splitBeatSurplus(flat[cursor], resolveBeatDiv(beatDiv, mi)));
    cursor++;
  }
  return chunkBeats(out, schedule);
}

export function beatErrorMap(
  grid: string[][],
  voiceName: string,
  beatDiv: number | number[] = BEAT_DIV,
): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  grid.forEach((measure, mi) => {
    const div = resolveBeatDiv(beatDiv, mi);
    measure.forEach((beat, bi) => {
      const fill = analyzeBeatFill(beat, div);
      out[`${voiceName}::${mi}::${bi}`] =
        fill.status === "under" || fill.status === "over" || fill.status === "invalid";
    });
  });
  return out;
}

/**
 * Coupe la cellule au curseur : la partie gauche reste, la partie droite
 * est poussée dans le temps suivant (la suite glisse d'un cran).
 *
 * Ex. `-.ds,` avec curseur entre `d` et `s` → `-.d` | `s,` | …
 * Si rien à droite du curseur → pas de mutation (navigation seule côté UI).
 */
export function shiftBeatTailToNext(
  grid: string[][],
  measureIndex: number,
  beatIndex: number,
  beatsPerMeasure: BeatSchedule,
  currentValue: string,
  caretIndex: number,
): {
  grid: string[][];
  nextMeasure: number;
  nextBeat: number;
  /** false si aucune queue à déplacer */
  moved: boolean;
} {
  const schedule = resolveBeatSchedule(
    beatsPerMeasure,
    Math.max(grid.length, measureIndex + 1),
  );
  const flat = flattenGrid(grid, schedule);
  const idx = flatIndex(measureIndex, beatIndex, schedule);
  while (flat.length <= idx) flat.push("");

  const value = currentValue;
  const caret = Math.max(0, Math.min(caretIndex, value.length));
  const left = value.slice(0, caret).replace(/\s+$/g, "");
  const right = value.slice(caret).replace(/^\s+/g, "");

  const nextIdx = idx + 1;
  const { measure: nextMeasure, beat: nextBeat } = unflatIndex(nextIdx, schedule);

  if (!right) {
    const next = [...flat];
    next[idx] = left;
    return {
      grid: chunkBeats(next, schedule),
      nextMeasure,
      nextBeat,
      moved: false,
    };
  }

  const next = [...flat];
  next[idx] = left;
  next.splice(idx + 1, 0, right);

  return {
    grid: chunkBeats(next, schedule),
    nextMeasure,
    nextBeat,
    moved: true,
  };
}

/**
 * Extrait la première note d'une cellule pour Suppr (fin de cellule).
 *
 * Règle `.` :
 * - `.` avant la note (ex. `.m`) → vient avec la note ;
 * - `.` derrière (ex. `m.s` → prend `m`, laisse `.s`) → reste.
 *
 * Même idée pour une virgule rythmique (`d,r` → `d` + `,r`).
 */
export function peelFirstNote(raw: string): { taken: string; rest: string } {
  const compact = raw.replace(/\s+/g, "");
  if (!compact) return { taken: "", rest: "" };

  if (compact.includes(".")) {
    const dotIdx = compact.indexOf(".");
    const left = compact.slice(0, dotIdx);
    const right = compact.slice(dotIdx + 1);

    if (left === "") {
      // `.…` — le point leading voyage avec la première note
      if (!right) return { taken: ".", rest: "" };
      const peeled = peelFirstNote(right);
      if (!peeled.taken) return { taken: ".", rest: right };
      return { taken: `.${peeled.taken.replace(/^\./, "")}`, rest: peeled.rest };
    }

    const leftAtoms = extractGluedAtoms(left);
    if (leftAtoms.length >= 1) {
      const first = leftAtoms[0] === "_" ? "-" : leftAtoms[0];
      const leftRest = leftAtoms
        .slice(1)
        .map((a) => (a === "_" ? "-" : a))
        .join("");
      if (leftRest) {
        return { taken: first, rest: formatDotBeat(leftRest, right) };
      }
      // `.` derrière reste : `m.s` → m + .s ; `m.` → m + . ; `-.d` → - + .d
      return { taken: first, rest: `.${right}` };
    }
  }

  // Virgules rythmiques : d,r → d + ,r
  if (hasRhythmComma(compact)) {
    const qs = splitRhythmCommas(compact).map((q) => q.trim());
    if (qs.length > 1) {
      const first = qs[0] === "" ? "" : qs[0];
      const restParts = qs.slice(1);
      const rest = restParts.length ? `,${restParts.join(",")}` : "";
      if (first) return { taken: first, rest };
    }
  }

  const atoms = extractGluedAtoms(compact);
  if (atoms.length === 0) return { taken: compact, rest: "" };
  const first = atoms[0] === "_" ? "-" : atoms[0];
  const rest = atoms
    .slice(1)
    .map((a) => (a === "_" ? "-" : a))
    .join("");
  return { taken: first, rest };
}

/**
 * Suppr en fin de cellule : remonte la 1ʳᵉ note du temps suivant dans la
 * cellule courante ; si ce temps se vide, la suite décale d'un cran.
 */
export function deletePullNextNote(
  grid: string[][],
  measureIndex: number,
  beatIndex: number,
  beatsPerMeasure: BeatSchedule,
  currentValue: string,
  caretIndex: number,
): {
  grid: string[][];
  focusMeasure: number;
  focusBeat: number;
  moved: boolean;
} {
  const schedule = resolveBeatSchedule(
    beatsPerMeasure,
    Math.max(grid.length, measureIndex + 1),
  );
  const flat = flattenGrid(grid, schedule);
  const idx = flatIndex(measureIndex, beatIndex, schedule);
  while (flat.length <= idx) flat.push("");

  const caret = Math.max(0, Math.min(caretIndex, currentValue.length));
  // Uniquement s'il n'y a plus rien après le curseur
  if (caret < currentValue.length) {
    return {
      grid: chunkBeats(flat, schedule),
      focusMeasure: measureIndex,
      focusBeat: beatIndex,
      moved: false,
    };
  }

  const left = currentValue.slice(0, caret).replace(/\s+$/g, "");
  const next = [...flat];
  next[idx] = left;

  // Sauter les silences (cellules vides) jusqu'à une note
  let j = idx + 1;
  while (j < next.length && next[j].trim() === "") j++;
  if (j >= next.length) {
    return {
      grid: chunkBeats(next, schedule),
      focusMeasure: measureIndex,
      focusBeat: beatIndex,
      moved: false,
    };
  }

  if (j > idx + 1) {
    next.splice(idx + 1, j - idx - 1);
    j = idx + 1;
  }

  const { taken, rest } = peelFirstNote(next[j]);
  if (!taken) {
    return {
      grid: chunkBeats(next, schedule),
      focusMeasure: measureIndex,
      focusBeat: beatIndex,
      moved: false,
    };
  }

  next[idx] = `${next[idx]}${taken}`;
  next[j] = rest;
  if (rest.trim() === "") {
    next.splice(j, 1);
  }

  return {
    grid: chunkBeats(next, schedule),
    focusMeasure: measureIndex,
    focusBeat: beatIndex,
    moved: true,
  };
}

/**
 * Cellule vide + Backspace : retire ce temps, tout ce qui suit remonte d'un cran.
 * Le focus reste sur la même position (qui reçoit l'ancien contenu du temps suivant).
 */
export function pullBeatsLeft(
  grid: string[][],
  measureIndex: number,
  beatIndex: number,
  beatsPerMeasure: BeatSchedule,
): {
  grid: string[][];
  focusMeasure: number;
  focusBeat: number;
  moved: boolean;
} {
  const schedule = resolveBeatSchedule(
    beatsPerMeasure,
    Math.max(grid.length, measureIndex + 1),
  );
  const flat = flattenGrid(grid, schedule);
  const idx = flatIndex(measureIndex, beatIndex, schedule);
  while (flat.length <= idx) flat.push("");

  const { measure: focusMeasure, beat: focusBeat } = unflatIndex(idx, schedule);

  // Rien à remonter après cette cellule
  if (flat.slice(idx + 1).every((b) => b.trim() === "")) {
    return {
      grid: chunkBeats(flat, schedule),
      focusMeasure,
      focusBeat,
      moved: false,
    };
  }

  const next = [...flat];
  next.splice(idx, 1);

  return {
    grid: chunkBeats(next, schedule),
    focusMeasure,
    focusBeat,
    moved: true,
  };
}

export function gridHasBeatErrors(
  grid: string[][],
  beatDiv: number | number[] = BEAT_DIV,
  triplets?: TripletMark[],
): boolean {
  for (let mi = 0; mi < grid.length; mi++) {
    const div = resolveBeatDiv(beatDiv, mi);
    for (let bi = 0; bi < grid[mi].length; bi++) {
      if (isTripletPairContinuation(triplets, mi, bi)) continue;
      const span = tripletSpanBeatsAt(triplets, mi, bi);
      const beat = grid[mi][bi];
      const s = span
        ? analyzeTripletFill(beat, span, div).status
        : analyzeBeatFill(beat, div).status;
      if (s === "under" || s === "over" || s === "invalid") return true;
    }
  }
  return false;
}
