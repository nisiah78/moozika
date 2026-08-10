import type { Measure, NoteEl, ScoreResult, TripletMark, Voice, VoiceModel } from "@/lib/types";
import { modelToMusicxml } from "@/lib/scoresApi";
import type { AbsPitch } from "@/lib/staffPitch";
import { syllableOfPitch, type ResolvedPitch } from "@/lib/movableDo";
import { isTripletPairContinuation, tripletSpanBeatsAt } from "@/lib/triplets";

export function cloneScore(result: ScoreResult): ScoreResult {
  return JSON.parse(JSON.stringify(result)) as ScoreResult;
}

export function durationForType(
  type: string,
  divisions: number,
  dots = 0,
): number {
  const map: Record<string, number> = {
    whole: divisions * 4,
    half: divisions * 2,
    quarter: divisions,
    eighth: Math.max(1, Math.floor(divisions / 2)),
    "16th": Math.max(1, Math.floor(divisions / 4)),
  };
  let d = map[type] ?? divisions;
  // Point d'augmentation : +½, +¼, …
  let add = d;
  for (let i = 0; i < dots; i++) {
    add = Math.floor(add / 2);
    if (add < 1) break;
    d += add;
  }
  return d;
}

function syllableForPitch(
  pitch: AbsPitch & { syllable?: string },
  tonic: string,
  dohOctave: number,
): string {
  if (pitch.syllable) return pitch.syllable;
  try {
    return syllableOfPitch(
      pitch.step,
      pitch.alter,
      pitch.octave,
      tonic,
      dohOctave,
    ).core;
  } catch {
    return pitch.step.charAt(0).toLowerCase();
  }
}

export function applyNotePitch(
  note: NoteEl,
  pitch: (AbsPitch & { syllable?: string }) | null,
  isRest: boolean,
  tonic = "C",
  dohOctave = 4,
): void {
  note.isRest = isRest;
  if (isRest) {
    note.pitch = null;
  } else {
    note.pitch = {
      step: pitch!.step,
      alter: pitch!.alter,
      octave: pitch!.octave,
      syllable: syllableForPitch(pitch!, tonic, dohOctave),
    };
  }
}

/** Change la valeur rythmique (ronde…16e) en préservant hauteur / silence. */
export function applyNoteDuration(
  note: NoteEl,
  type: string,
  divisions: number,
  dots = 0,
): void {
  note.type = type;
  note.dots = Math.max(0, Math.min(2, dots));
  note.duration = durationForType(type, divisions, note.dots);
}

export function makeNote(
  model: VoiceModel,
  pitch: (AbsPitch & { syllable?: string }) | ResolvedPitch | null,
  isRest: boolean,
  type = "quarter",
  dots = 0,
): NoteEl {
  const tonic = model.tonic || "C";
  const dohOctave = model.dohOctave ?? 4;
  const d = Math.max(0, Math.min(2, dots));
  return {
    isRest,
    duration: durationForType(type, model.divisions || 1, d),
    type,
    dots: d,
    pitch: isRest
      ? null
      : {
          step: pitch!.step,
          alter: pitch!.alter,
          octave: pitch!.octave,
          syllable: syllableForPitch(pitch!, tonic, dohOctave),
        },
    tieStart: false,
    tieStop: false,
  };
}

/** Reconstruit la notation sol-fa d'une voix depuis la grille de mesures/temps. */
export function rebuildVoiceNotation(
  measures: string[][],
  beatsPerMeasure: number | number[],
  meterPrefixes?: Array<
    { beats?: number; beatType?: number; keyTonic?: string } | null | undefined
  >,
  triplets?: TripletMark[],
): string {
  const schedule: number[] =
    typeof beatsPerMeasure === "number"
      ? measures.map(() => beatsPerMeasure)
      : (() => {
          const s = [...beatsPerMeasure];
          const last = s[s.length - 1] ?? 4;
          while (s.length < measures.length) s.push(last);
          return s;
        })();

  return measures
    .map((beats, mi) => {
      const bpm = schedule[mi] ?? schedule[schedule.length - 1] ?? 4;
      const padded = [...beats];
      while (padded.length < bpm) padded.push("");
      const mid = Math.floor(bpm / 2);
      const parts: string[] = [];
      let i = 0;
      while (i < bpm) {
        if (isTripletPairContinuation(triplets, mi, i)) {
          i++;
          continue;
        }
        parts.push(padded[i].trim());
        const span = tripletSpanBeatsAt(triplets, mi, i) ?? 1;
        const nextI = i + span;
        if (nextI < bpm) {
          parts.push(nextI - 1 === mid ? "!" : ":");
        }
        i = nextI;
      }
      // Préfixes de tête : (N/M) mètre puis (Doh=X) tonalité — relus par le
      // parseur pour re-résoudre les hauteurs contre la tonique courante.
      const p = meterPrefixes?.[mi];
      let prefix = "";
      if (p) {
        if (p.beats != null && p.beatType != null) prefix += `(${p.beats}/${p.beatType}) `;
        if (p.keyTonic) prefix += `(Doh=${p.keyTonic}) `;
      }
      return prefix + parts.join(" ");
    })
    .join(" | ");
}

/**
 * Vide les cellules d'une notation en conservant sa structure (nombre de
 * mesures, de temps, séparateurs `:`/`!`, préfixes de métrique). Sert à donner
 * à une voix ajoutée des cellules vides (= silences) prêtes à être remplies.
 */
export function blankNotationLike(notation: string): string {
  return notation
    .split("|")
    .map((m) => {
      const t = m.trim();
      if (!t) return "";
      const pm = t.match(/^\(([^)]*)\)\s*/);
      const prefix = pm ? pm[0] : "";
      const body = pm ? t.slice(pm[0].length) : t;
      const blanked = body
        .split(/([:!])/)
        .map((tok) => (tok === ":" || tok === "!" ? tok : ""))
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      return (prefix + blanked).trim();
    })
    .filter(Boolean)
    .join(" | ");
}

/**
 * Découpe une voix en **divisi** : la voix cible devient « <base> 1 » et une
 * nouvelle voix silencieuse « <base> N » est insérée juste après, entrant à la
 * mesure `fromMeasureAbs` (0-based). La nouvelle voix reprend le squelette
 * rythmique de la cible mais toutes ses notes sont des silences, et sa notation
 * est vidée (cellules à remplir). Retourne le score muté — à régénérer ensuite
 * (`regenerateFromModels`) pour reconstruire le MusicXML pivot.
 */
export function splitVoiceForDivisi(
  result: ScoreResult,
  targetVoiceName: string,
  fromMeasureAbs: number,
): { score: ScoreResult; newVoiceName: string } {
  const next = cloneScore(result);
  const ti = next.voices.findIndex((v) => v.name === targetVoiceName);
  if (ti < 0) return { score: result, newVoiceName: targetVoiceName };
  const target = next.voices[ti];

  const base = targetVoiceName.replace(/\s*\d+$/, "").trim() || targetVoiceName;
  const usedIndices = next.voices
    .filter((v) => v.name.replace(/\s*\d+$/, "").trim() === base)
    .map((v) => {
      const m = v.name.match(/(\d+)\s*$/);
      return m ? Number(m[1]) : 1;
    });
  const newVoiceName = `${base} ${Math.max(1, ...usedIndices) + 1}`;

  // La cible sans index prend « 1 » (S → S1), puis on ajoute S2.
  if (!/\d\s*$/.test(target.name)) {
    target.name = `${base} 1`;
    target.model.partName = `${base} 1`;
  }

  // Nouvelle voix : même squelette rythmique, notes → silences.
  const restMeasures: Measure[] = target.model.measures.map((m) => ({
    number: m.number,
    notes: m.notes.map((n) => ({
      isRest: true,
      duration: n.duration,
      type: n.type,
      dots: n.dots,
      pitch: null,
      tieStart: false,
      tieStop: false,
    })),
    ...(m.timeSignature ? { timeSignature: m.timeSignature } : {}),
    ...(m.keyFifths != null
      ? { keyFifths: m.keyFifths, keyTonic: m.keyTonic }
      : {}),
    ...(m.implicit ? { implicit: m.implicit } : {}),
  }));

  const model: VoiceModel = {
    tonic: target.model.tonic,
    fifths: target.model.fifths,
    timeSignature: target.model.timeSignature,
    divisions: target.model.divisions,
    clef: target.model.clef,
    tempo: null,
    partName: newVoiceName,
    measures: restMeasures,
    dohOctave: target.model.dohOctave,
    enterMeasure: Math.max(0, Math.floor(fromMeasureAbs)),
  };

  next.voices.splice(ti + 1, 0, {
    name: newVoiceName,
    notation: blankNotationLike(target.notation),
    model,
  });

  return { score: next, newVoiceName };
}

export async function regenerateFromModels(
  result: ScoreResult,
  voices: Voice[],
): Promise<ScoreResult> {
  const prevTriplets = voices.map((v) => v.model.triplets);
  // enterMeasure (divisi) n'existe pas en MusicXML : à re-attacher par index.
  const prevEnter = voices.map((v) => v.model.enterMeasure);
  // Ne jamais écraser la notation éditeur par to_solfa du backend :
  // avec divisions=12 (triolets), un to_solfa non aligné réécrivait
  // « d : r : m : f » en « d : - : - : r » et cassait les mesures voisines.
  const prevNotation = voices.map((v) => v.notation);
  const converted = await modelToMusicxml(
    voices.map((v) => v.model),
    result.header.title || "",
  );
  const outVoices = (converted.voices?.length ? converted.voices : voices).map(
    (v, i) => ({
      ...v,
      notation: prevNotation[i] ?? v.notation,
      model: {
        ...v.model,
        triplets: prevTriplets[i] ?? v.model.triplets,
        enterMeasure: prevEnter[i] ?? v.model.enterMeasure,
      },
    }),
  );
  return {
    ...result,
    voices: outVoices,
    musicxml: converted.musicxml,
    uploadedFile: undefined,
  };
}

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080").replace(
  /\/$/,
  "",
);

/** Parse une notation sol-fa via Symfony → omr (ou proxy Next en secours). */
export async function parseSolfaNotation(
  notation: string,
  tonic: string,
  clef: string,
  beats?: number,
  beatType?: number,
  triplets?: TripletMark[],
): Promise<{ model: VoiceModel; musicxml: string }> {
  // `beats`/`beat_type` transmis pour PRÉSERVER la signature à l'édition : sans
  // eux le re-parse retombe sur beat_type=4 (ex. 10/8 → 10/4, rejeté par le back).
  const body = JSON.stringify({
    notation,
    tonic,
    clef,
    doh_octave: 4,
    ...(beats != null ? { beats } : {}),
    ...(beatType != null ? { beat_type: beatType } : {}),
    ...(triplets?.length
      ? {
          triplets: triplets.map((t) => ({
            startMeasure: t.startMeasure,
            startBeat: t.startBeat,
            spanBeats: t.spanBeats,
          })),
        }
      : {}),
  });
  let res = await fetch(`${API_URL}/convert/solfa-parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body,
  });
  if (res.status === 404) {
    res = await fetch("/api/solfa/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body,
    });
  }
  const data = (await res.json()) as {
    model?: VoiceModel;
    musicxml?: string;
    detail?: string;
  };
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  if (!data.model) throw new Error("Réponse parse sans model");
  return { model: data.model, musicxml: data.musicxml || "" };
}
