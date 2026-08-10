/**
 * Directives de mesure (navigation, tempo, métrique, tonalité).
 * Source de vérité = VoiceModel.measures[i] sur toutes les voix.
 */

import type {
  Measure,
  MeasureDirection,
  NoteEl,
  ScoreResult,
  VoiceModel,
} from "@/lib/types";
import { cloneScore } from "@/lib/scoreEdit";
import {
  fifthsOf,
  normalizeTonic,
  resolvePitch,
  syllableOfPitch,
  withOctaveMarks,
} from "@/lib/movableDo";

export type DirectiveMenuId =
  | "segno"
  | "coda"
  | "dacapo"
  | "dalsegno"
  | "fine"
  | "metronome"
  | "time"
  | "key";

export type DirectivePayload =
  | { id: "segno" | "coda" | "dacapo" | "dalsegno" | "fine" }
  | { id: "metronome"; bpm: number }
  | { id: "time"; beats: number; beatType: number }
  | { id: "key"; tonic: string };

export type DirectiveChip =
  | { key: string; kind: "direction"; label: string; directionKind: string }
  | { key: string; kind: "time"; label: string }
  | { key: string; kind: "key"; label: string };

export const DIRECTIVE_MENU: {
  id: DirectiveMenuId;
  label: string;
  group: "nav" | "tempo" | "meter" | "key";
  needsForm?: boolean;
}[] = [
  { id: "segno", label: "Segno (𝄋)", group: "nav" },
  { id: "coda", label: "Coda (𝄌)", group: "nav" },
  { id: "dacapo", label: "D.C. (Da Capo)", group: "nav" },
  { id: "dalsegno", label: "D.S. (Dal Segno)", group: "nav" },
  { id: "fine", label: "Fine", group: "nav" },
  { id: "metronome", label: "Tempo (métronome)", group: "tempo", needsForm: true },
  { id: "time", label: "Changement de mesure", group: "meter", needsForm: true },
  { id: "key", label: "Changement de tonalité (Doh)", group: "key", needsForm: true },
];

const NAV_LABEL: Record<string, string> = {
  segno: "Segno",
  coda: "Coda",
  dacapo: "D.C.",
  dalsegno: "D.S.",
  fine: "Fine",
};

function ensureMeasure(model: VoiceModel, measureIndex: number): Measure {
  while (model.measures.length <= measureIndex) {
    model.measures.push({
      number: model.measures.length + 1,
      notes: [],
    });
  }
  return model.measures[measureIndex];
}

function upsertDirection(measure: Measure, dir: MeasureDirection): void {
  const dirs = measure.directions ? [...measure.directions] : [];
  const idx = dirs.findIndex(
    (d) => d.kind === dir.kind && (d.offset ?? 0) === (dir.offset ?? 0),
  );
  if (idx >= 0) dirs[idx] = dir;
  else dirs.push(dir);
  measure.directions = dirs;
}

function removeDirectionKind(measure: Measure, kind: string): void {
  if (!measure.directions) return;
  measure.directions = measure.directions.filter((d) => d.kind !== kind);
  if (measure.directions.length === 0) delete measure.directions;
}

/** Token syllabe sol-fa (avec marques d'octave) → null si tiret / silence / autre. */
function parseSyllableToken(
  raw: string,
): { core: string; shift: number } | null {
  const t = raw.trim();
  if (!t || t === "-" || t === "_" || t === "0") return null;
  const m = t.match(/^([drmfslt](?:[aei])?)('+|,+|_*)?$/i);
  if (!m) return null;
  const core = m[1].toLowerCase();
  const marks = m[2] || "";
  let shift = 0;
  if (marks.includes("'")) shift = marks.length;
  else if (marks) shift = -marks.length;
  return { core, shift };
}

/**
 * Transpose les hauteurs absolues sous une nouvelle tonique en conservant
 * les syllabes écrites (degrés mouvable-do). Le piano / MusicXML suivent.
 * S'arrête au prochain `(Doh=)` déjà posé plus loin.
 */
export function transposePitchesFromSyllables(
  model: VoiceModel,
  fromMeasure: number,
  tonic: string,
  dohOctave: number,
): void {
  const newTonic = normalizeTonic(tonic);
  for (let mi = fromMeasure; mi < model.measures.length; mi++) {
    const m = model.measures[mi];
    if (mi > fromMeasure && m.keyTonic) break;
    const localTonic = normalizeTonic(m.keyTonic || newTonic);
    for (const note of m.notes) {
      if (note.isRest || !note.pitch) continue;
      const parsed = parseSyllableToken(note.pitch.syllable);
      if (!parsed) continue;
      try {
        const p = resolvePitch(parsed.core, parsed.shift, localTonic, dohOctave);
        note.pitch.step = p.step;
        note.pitch.alter = p.alter;
        note.pitch.octave = p.octave;
      } catch {
        /* laisse la hauteur */
      }
    }
  }
}

/**
 * Réécrit une syllabe sous une nouvelle tonique en conservant la hauteur absolue
 * (mouvable-do : mêmes notes écrites → nouvelles syllabes).
 */
export function transposeSyllableToken(
  token: string,
  oldTonic: string,
  newTonic: string,
  dohOctave = 4,
): string {
  const parsed = parseSyllableToken(token);
  if (!parsed) return token;
  if (normalizeTonic(oldTonic) === normalizeTonic(newTonic)) return token;
  try {
    const pitch = resolvePitch(parsed.core, parsed.shift, oldTonic, dohOctave);
    const { core, octaveShift } = syllableOfPitch(
      pitch.step,
      pitch.alter,
      pitch.octave,
      newTonic,
      dohOctave,
    );
    return withOctaveMarks(core, octaveShift);
  } catch {
    return token;
  }
}

/** Réécrit tous les tokens syllabe d'un fragment de mesure (préfixe annotations conservé). */
function transposeMeasureText(
  measureText: string,
  oldTonic: string,
  newTonic: string,
  dohOctave: number,
): string {
  // Préfixes (6/8), (Doh=…), [D.C.]… — ne pas toucher
  let prefix = "";
  let body = measureText;
  for (;;) {
    const m = body.match(/^(\([^)]*\)|\[[^\]]*\])\s*/);
    if (!m) break;
    prefix += m[0];
    body = body.slice(m[0].length);
  }

  // Syllabes isolées ou collées (drm, -d, d') — pas les séparateurs : ! . ,
  const rewritten = body.replace(
    /[drmfslt](?:[aei])?(?:'+|,+|_*)?/gi,
    (tok) => transposeSyllableToken(tok, oldTonic, newTonic, dohOctave),
  );
  return prefix + rewritten;
}

/**
 * Transpose (ré-épelle) la notation sol-fa texte à partir de `fromMeasure`
 * jusqu'au prochain changement de tonique déjà présent.
 */
export function resyllabifyNotationFrom(
  notation: string,
  fromMeasure: number,
  oldTonic: string,
  newTonic: string,
  dohOctave: number,
  model: VoiceModel,
): string {
  const parts = notation.split("|");
  // split garde les segments ; trim pour cibler les mesures non vides
  const measureIndexes: number[] = [];
  parts.forEach((p, i) => {
    if (p.trim()) measureIndexes.push(i);
  });

  let logical = 0;
  for (let pi = 0; pi < parts.length; pi++) {
    if (!parts[pi].trim()) continue;
    if (logical < fromMeasure) {
      logical++;
      continue;
    }
    if (
      logical > fromMeasure &&
      model.measures[logical]?.keyTonic
    ) {
      break;
    }
    parts[pi] = transposeMeasureText(
      parts[pi],
      oldTonic,
      newTonic,
      dohOctave,
    );
    logical++;
  }
  return parts.join("|");
}

/** Capacité d'une mesure en divisions (noires × divisions). */
export function measureCapacity(
  beats: number,
  beatType: number,
  divisions: number,
): number {
  // divisions = par noire ; capacité = beats * (4/beatType) * divisions
  return Math.round(beats * (4 / beatType) * divisions);
}

export function measureDurationSum(notes: NoteEl[]): number {
  return notes.reduce((s, n) => s + (n.duration || 0), 0);
}

/** Table gloutonne (miroir omr `split_duration`) pour une durée → type/points. */
function noteShapeForDuration(
  duration: number,
  divisions: number,
): { type: string; dots: number } | null {
  const d = divisions || 1;
  const table: Array<[number, string, number]> = [
    [d * 4, "whole", 0],
    [d * 3, "half", 1],
    [d * 2, "half", 0],
    [Math.round(d * 1.5), "quarter", 1],
    [d, "quarter", 0],
    [Math.round(d * 0.75), "eighth", 1],
    [Math.max(1, Math.floor(d / 2)), "eighth", 0],
    [Math.max(1, Math.floor(d / 4)), "16th", 0],
  ];
  for (const [value, type, dots] of table) {
    if (value === duration) return { type, dots };
  }
  return null;
}

function makeRest(duration: number, divisions: number): NoteEl[] {
  const out: NoteEl[] = [];
  let left = duration;
  const d = divisions || 1;
  const values = [
    d * 4,
    d * 3,
    d * 2,
    Math.round(d * 1.5),
    d,
    Math.round(d * 0.75),
    Math.max(1, Math.floor(d / 2)),
    Math.max(1, Math.floor(d / 4)),
  ];
  while (left > 0) {
    const value = values.find((v) => v <= left) ?? 1;
    const shape = noteShapeForDuration(value, d) ?? { type: "16th", dots: 0 };
    out.push({
      isRest: true,
      duration: value,
      type: shape.type,
      dots: shape.dots,
      pitch: null,
      tieStart: false,
      tieStop: false,
    });
    left -= value;
  }
  return out;
}

/**
 * Ajuste les notes d'une mesure à la capacité du mètre (coupe le surplus,
 * complète avec des silences). Indispensable après un changement 10/8→6/8 :
 * sinon le MusicXML déborde (20 div dans une mesure de 12).
 */
export function fitNotesToCapacity(
  notes: NoteEl[],
  capacity: number,
  divisions = 1,
): NoteEl[] {
  if (capacity <= 0) return [];
  const out: NoteEl[] = [];
  let sum = 0;
  for (const n of notes) {
    const dur = n.duration || 0;
    if (dur <= 0) continue;
    if (sum >= capacity) break;
    if (sum + dur <= capacity) {
      out.push({ ...n, pitch: n.pitch ? { ...n.pitch } : null });
      sum += dur;
      continue;
    }
    const remain = capacity - sum;
    if (remain > 0) {
      const shape = noteShapeForDuration(remain, divisions);
      out.push({
        ...n,
        duration: remain,
        type: shape?.type ?? n.type,
        dots: shape?.dots ?? 0,
        pitch: n.pitch ? { ...n.pitch } : null,
        tieStart: false,
        tieStop: false,
      });
      sum = capacity;
    }
    break;
  }
  if (sum < capacity) {
    out.push(...makeRest(capacity - sum, divisions));
  }
  return out;
}

/**
 * Métrique effective à l'index (en remontant les changements).
 */
export function effectiveTimeSignature(
  model: VoiceModel,
  measureIndex: number,
): { beats: number; beatType: number } {
  let beats = model.timeSignature.beats;
  let beatType = model.timeSignature.beatType;
  for (let i = 0; i <= measureIndex && i < model.measures.length; i++) {
    const ts = model.measures[i].timeSignature;
    if (ts) {
      beats = ts.beats;
      beatType = ts.beatType;
    }
  }
  return { beats, beatType };
}

/**
 * Nombre de pulsations sol-fa (`:`) pour une signature MusicXML.
 * Miroir de `classify_meter` : 6/8 → 6 croches (pas 2 noires pointées),
 * 10/8 → 10, 9/8 → 3 composés.
 */
export function solfaPulseCount(beats: number, beatType: number): number {
  if (beatType === 8 && (beats === 5 || beats === 6 || beats === 10)) {
    return beats;
  }
  if ((beatType === 8 || beatType === 16) && beats % 3 === 0 && beats > 3) {
    return beats / 3;
  }
  return beats;
}

/**
 * Longueur de chaque mesure en cellules sol-fa, d'après le mètre effectif.
 * Les indices au-delà de `model.measures` prolongent le dernier mètre.
 */
export function beatScheduleForModel(
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
    out.push(solfaPulseCount(beats, beatType));
  }
  return out;
}

/** Divisions par pulsation pour chaque mesure (miroir `beatDivisionsFor`). */
export function beatDivScheduleForModel(
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
    // Inline mirror of beatDivisionsFor — évite un import circulaire.
    if (beatType === 8 && (beats === 5 || beats === 6 || beats === 10)) out.push(2);
    else if (
      (beatType === 8 || beatType === 16) &&
      beats % 3 === 0 &&
      beats > 3
    )
      out.push(6);
    else out.push(4);
  }
  return out;
}

export function effectiveTonic(model: VoiceModel, measureIndex: number): string {
  let tonic = model.tonic;
  for (let i = 0; i <= measureIndex && i < model.measures.length; i++) {
    if (model.measures[i].keyTonic) {
      tonic = model.measures[i].keyTonic!;
    }
  }
  return tonic;
}

/** Chips à afficher pour une mesure (voix 0 = référence globale). */
export function chipsForMeasure(measure: Measure | undefined): DirectiveChip[] {
  if (!measure) return [];
  const chips: DirectiveChip[] = [];
  if (measure.timeSignature) {
    const { beats, beatType } = measure.timeSignature;
    chips.push({
      key: "time",
      kind: "time",
      label: `${beats}/${beatType}`,
    });
  }
  if (measure.keyTonic) {
    chips.push({
      key: "key",
      kind: "key",
      label: `Doh=${measure.keyTonic}`,
    });
  }
  for (const d of measure.directions || []) {
    if (d.kind === "metronome") {
      chips.push({
        key: `dir-${d.kind}`,
        kind: "direction",
        label: `♩=${d.value}`,
        directionKind: d.kind,
      });
    } else if (d.kind in NAV_LABEL) {
      chips.push({
        key: `dir-${d.kind}`,
        kind: "direction",
        label: NAV_LABEL[d.kind] || d.value || d.kind,
        directionKind: d.kind,
      });
    } else if (d.kind === "words" && d.value) {
      chips.push({
        key: `dir-words-${d.value}`,
        kind: "direction",
        label: d.value,
        directionKind: d.kind,
      });
    }
  }
  return chips;
}

export type ApplyResult = {
  score: ScoreResult;
  /** Mesures dont la somme des durées ≠ capacité après changement de time. */
  meterWarnings: string[];
};

export function applyDirective(
  score: ScoreResult,
  measureIndex: number,
  payload: DirectivePayload,
): ApplyResult {
  const next = cloneScore(score);
  const meterWarnings: string[] = [];

  for (const voice of next.voices) {
    const model = voice.model;
    const measure = ensureMeasure(model, measureIndex);
    const dohOctave = model.dohOctave ?? 4;

    switch (payload.id) {
      case "segno":
      case "coda":
      case "dacapo":
      case "dalsegno":
      case "fine": {
        const value =
          payload.id === "dacapo"
            ? "D.C."
            : payload.id === "dalsegno"
              ? "D.S."
              : payload.id === "fine"
                ? "Fine"
                : "";
        upsertDirection(measure, {
          offset: 0,
          kind: payload.id,
          value,
          placement: "above",
        });
        break;
      }
      case "metronome": {
        const bpm = Math.min(300, Math.max(1, Math.round(payload.bpm)));
        upsertDirection(measure, {
          offset: 0,
          kind: "metronome",
          value: String(bpm),
          placement: "above",
        });
        if (measureIndex === 0) {
          model.tempo = bpm;
          next.header.tempo = bpm;
        }
        break;
      }
      case "time": {
        const beats = payload.beats;
        const beatType = payload.beatType;
        if (beats < 1 || beatType < 1) {
          throw new Error("Signature invalide");
        }
        // Éviter de stocker un changement redondant si déjà le mètre courant
        const before = effectiveTimeSignature(model, Math.max(0, measureIndex - 1));
        if (
          measureIndex > 0 &&
          before.beats === beats &&
          before.beatType === beatType
        ) {
          delete measure.timeSignature;
        } else {
          measure.timeSignature = { beats, beatType };
        }
        if (measureIndex === 0) {
          model.timeSignature = { beats, beatType };
          next.header.timeSignature = { beats, beatType };
          // Mesure 1 : le mètre d'en-tête suffit, pas besoin de répéter
          delete measure.timeSignature;
        }
        // Ajuster les durées à la capacité effective (sinon 10/8→6/8 laisse
        // 20 divisions dans une mesure de 12 → MusicXML invalide / faux 2/4).
        const divisions = model.divisions || 1;
        let curBeats = model.timeSignature.beats;
        let curType = model.timeSignature.beatType;
        for (let mi = 0; mi < model.measures.length; mi++) {
          const m = model.measures[mi];
          if (m.timeSignature) {
            curBeats = m.timeSignature.beats;
            curType = m.timeSignature.beatType;
          }
          if (mi < measureIndex) continue;
          const cap = measureCapacity(curBeats, curType, divisions);
          m.notes = fitNotesToCapacity(m.notes || [], cap, divisions);
          const sum = measureDurationSum(m.notes);
          if (sum !== cap) {
            meterWarnings.push(
              `${voice.name} m.${mi + 1}: durée ${sum} ≠ capacité ${cap} (${curBeats}/${curType})`,
            );
          }
        }
        break;
      }
      case "key": {
        const tonic = normalizeTonic(payload.tonic);
        const fifths = fifthsOf(tonic);
        measure.keyTonic = tonic;
        measure.keyFifths = fifths;
        // Indication texte pour sol-fa / MusicXML words
        upsertDirection(measure, {
          offset: 0,
          kind: "words",
          value: `Doh = ${tonic}`,
          placement: "above",
        });
        if (measureIndex === 0) {
          model.tonic = tonic;
          model.fifths = fifths;
          next.header.tonic = tonic;
        }
        // Syllabes (degrés) inchangées → nouvelles hauteurs absolues pour piano / MusicXML
        transposePitchesFromSyllables(model, measureIndex, tonic, dohOctave);
        break;
      }
    }
  }

  return { score: next, meterWarnings };
}

export function removeDirectiveChip(
  score: ScoreResult,
  measureIndex: number,
  chip: DirectiveChip,
): ScoreResult {
  const next = cloneScore(score);
  for (const voice of next.voices) {
    if (measureIndex >= voice.model.measures.length) continue;
    const measure = voice.model.measures[measureIndex];
    if (chip.kind === "time") {
      delete measure.timeSignature;
    } else if (chip.kind === "key") {
      delete measure.keyFifths;
      delete measure.keyTonic;
      removeDirectionKind(measure, "words");
      // Ne pas recalculer en arrière — les syllabes restent celles de la nouvelle tonique
    } else if (chip.kind === "direction") {
      removeDirectionKind(measure, chip.directionKind);
    }
  }
  return next;
}
