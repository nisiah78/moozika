/**
 * Playback piano à partir du ScoreResult (modèle déjà dérivé du MusicXML).
 * Tone.js + samples Salamander — cf. docs/architecture.md §9.
 *
 * Hauteurs : on lit directement `note.pitch` (hauteur absolue). C'est la source
 * de vérité — le parseur l'a déjà résolue cellule par cellule avec la tonique
 * EFFECTIVE (changements de `(Doh=X)` mid-partition inclus) ET les marques
 * d'octave (`,` / `'`). Recalculer depuis la seule syllabe perdrait l'octave
 * (la syllabe stockée est le « core » sans marques) → notes en `,` une octave
 * trop haut.
 *
 * Synchronisation multi-voix : les mesures sont alignées dans le temps (chaque
 * mesure démarre au même instant pour toutes les voix). Sans cela, une mesure
 * de durée incohérente entre voix (artefact OMR) décale toute une voix jusqu'à
 * la fin — d'où une note qui « traîne » après la fin apparente de la partition.
 */

import { defaultTempoSettings, resolveQuarterBpm, type TempoSettings } from "./tempo";
import type { NoteEl, Pitch, ScoreResult, VoiceModel } from "./types";

export type PlayState = "idle" | "loading" | "playing" | "stopped";

export interface ScheduledNote {
  time: number; // secondes depuis le début
  duration: number;
  note: string; // ex. "F#4"
}

/** Position de lecture : mesure absolue + temps (pulsation) dans la mesure. */
export interface PlaybackPosition {
  measure: number;
  beat: number;
}

const DEFAULT_TEMPO = 90;

/** Pitch modèle → notation scientifique Tone.js ("F#4", "Bb3"). */
export function pitchToNoteName(p: Pitch): string {
  const accidental =
    p.alter === 1 ? "#" : p.alter === -1 ? "b" : p.alter === 2 ? "##" : p.alter === -2 ? "bb" : "";
  return `${p.step}${accidental}${p.octave}`;
}

/** Tonique en vigueur à la mesure (suit les `keyTonic` depuis le début). */
export function effectiveTonicAt(model: VoiceModel, measureIndex: number): string {
  let tonic = model.tonic || "C";
  for (let i = 0; i <= measureIndex && i < model.measures.length; i++) {
    if (model.measures[i].keyTonic) tonic = model.measures[i].keyTonic!;
  }
  return tonic;
}

/**
 * Nom de note entendu = hauteur absolue stockée. `note.pitch` fait foi : le
 * parseur l'a résolue avec la tonique effective (changements de Doh compris) et
 * les marques d'octave. Ne PAS recalculer depuis la syllabe (« core » sans
 * marques → perte d'octave sur les notes en `,` / `'`).
 */
export function soundingNoteName(note: NoteEl): string | null {
  if (note.isRest || !note.pitch) return null;
  return pitchToNoteName(note.pitch);
}

/**
 * Une voix → liste d'événements, liaisons fusionnées.
 * `measureStarts` (optionnel) : instant de début de chaque mesure absolue. Il
 * réaligne le début de mesure sur la grille commune à toutes les voix, sans
 * jamais reculer (les liaisons de barre survivent) — indispensable quand une
 * voix a une mesure de durée aberrante qui la décalerait sinon.
 */
export function voiceToEvents(
  model: VoiceModel,
  tempoBpm: number,
  measureStarts?: number[],
): ScheduledNote[] {
  const { divisions } = model;
  const quarterSec = 60 / tempoBpm;
  const events: ScheduledNote[] = [];
  let t = 0;

  // Note ouverte (liaison) : on accumule la durée jusqu'au tieStop.
  let open: { note: string; start: number; duration: number } | null = null;

  const flush = () => {
    if (open) {
      events.push({ time: open.start, duration: open.duration, note: open.note });
      open = null;
    }
  };

  for (let mi = 0; mi < model.measures.length; mi++) {
    // Aligner le début de mesure sur la grille commune (avance seulement :
    // comble le retard d'une voix plus courte, ne rembobine jamais).
    if (measureStarts) {
      const ms = measureStarts[mi];
      if (ms != null && ms > t) t = ms;
    }
    const measure = model.measures[mi];
    for (const n of measure.notes) {
      const durSec = (n.duration / divisions) * quarterSec;

      if (n.isRest || !n.pitch) {
        flush();
        t += durSec;
        continue;
      }

      const name = soundingNoteName(n);
      if (!name) {
        flush();
        t += durSec;
        continue;
      }

      if (n.tieStop && open && open.note === name) {
        open.duration += durSec;
        if (!n.tieStart) flush();
      } else if (n.tieStart) {
        flush();
        open = { note: name, start: t, duration: durSec };
      } else {
        flush();
        events.push({ time: t, duration: durSec, note: name });
      }

      t += durSec;
    }
  }
  flush();
  return events;
}

function enabledVoicesOf(
  result: ScoreResult,
  enabledVoices?: ReadonlySet<string>,
) {
  return enabledVoices
    ? result.voices.filter((v) => enabledVoices.has(v.name))
    : result.voices;
}

/**
 * Grille commune de mesures : début (secondes) et durée de chaque mesure
 * absolue. La durée d'une mesure = MAX de sa durée sur toutes les voix — ainsi
 * toutes les voix démarrent chaque mesure au même instant, même si l'OMR a
 * produit une mesure de durée aberrante dans une voix.
 */
function measureGrid(
  voices: ScoreResult["voices"],
  quarterSec: number,
): { starts: number[]; durs: number[] } {
  const measureCount = Math.max(0, ...voices.map((v) => v.model.measures.length));
  const starts: number[] = [];
  const durs: number[] = [];
  let acc = 0;
  for (let mi = 0; mi < measureCount; mi++) {
    starts.push(acc);
    let maxDur = 0;
    for (const v of voices) {
      const m = v.model.measures[mi];
      if (!m) continue;
      const div = v.model.divisions || 1;
      let d = 0;
      for (const n of m.notes) d += (n.duration / div) * quarterSec;
      if (d > maxDur) maxDur = d;
    }
    durs.push(maxDur);
    acc += maxDur;
  }
  return { starts, durs };
}

/**
 * Convertit le score en événements schedulés.
 * Si ``enabledVoices`` est fourni, seules les voix dont le nom est dans
 * l'ensemble sont incluses ; sinon toutes les voix sont jouées.
 * Les mesures sont alignées entre voix (cf. measureGrid).
 */
export function scoreToEvents(
  result: ScoreResult,
  enabledVoices?: ReadonlySet<string>,
  tempoSettings?: TempoSettings,
): ScheduledNote[] {
  const settings = tempoSettings ?? defaultTempoSettings(result);
  const tempo = resolveQuarterBpm(settings) || DEFAULT_TEMPO;
  const quarterSec = 60 / tempo;
  const voices = enabledVoicesOf(result, enabledVoices);
  const { starts } = measureGrid(voices, quarterSec);
  return voices.flatMap((v) => voiceToEvents(v.model, tempo, starts));
}

/**
 * Nombre de pulsations sol-fa d'une signature (miroir de `solfaPulseCount` de
 * measureDirectives — dupliqué ici pour garder playback sans dépendance à alias
 * `@/`, donc testable en standalone). 6/8 → 6, 9/8 → 3, etc.
 */
function solfaPulses(beats: number, beatType: number): number {
  if (beatType === 8 && (beats === 5 || beats === 6 || beats === 10)) return beats;
  if ((beatType === 8 || beatType === 16) && beats % 3 === 0 && beats > 3) {
    return beats / 3;
  }
  return beats;
}

/** Pulsations par mesure d'après le mètre effectif (miroir beatScheduleForModel). */
function pulsesPerMeasure(model: VoiceModel, measureCount: number): number[] {
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
    out.push(solfaPulses(beats, beatType));
  }
  return out;
}

/**
 * Timeline des TEMPS (pulsations) : chaque mesure de la grille commune est
 * découpée en pulsations égales. Le nombre de temps par mesure suit la 1ʳᵉ voix
 * (`voices[0]`), source des cellules sol-fa affichées → l'index de temps colle
 * exactement à la cellule vue. Utilisé pour surligner le temps en cours.
 */
export function beatTimeline(
  result: ScoreResult,
  enabledVoices?: ReadonlySet<string>,
  tempoSettings?: TempoSettings,
): Array<PlaybackPosition & { time: number }> {
  const settings = tempoSettings ?? defaultTempoSettings(result);
  const tempo = resolveQuarterBpm(settings) || DEFAULT_TEMPO;
  const quarterSec = 60 / tempo;
  const voices = enabledVoicesOf(result, enabledVoices);
  const { starts, durs } = measureGrid(voices, quarterSec);
  const measureCount = starts.length;
  if (measureCount === 0) return [];

  // Mètre = 1ʳᵉ voix (celle qui pilote l'affichage sol-fa) ; à défaut la plus
  // longue des voix jouées.
  let ref: VoiceModel | null = result.voices[0]?.model ?? null;
  if (!ref) {
    for (const v of voices) {
      if (!ref || v.model.measures.length > ref.measures.length) ref = v.model;
    }
  }
  if (!ref) return [];
  const pulses = pulsesPerMeasure(ref, measureCount);

  const out: Array<PlaybackPosition & { time: number }> = [];
  for (let mi = 0; mi < measureCount; mi++) {
    const count = Math.max(
      1,
      pulses[Math.min(mi, pulses.length - 1)] ?? pulses[pulses.length - 1] ?? 4,
    );
    const beatDur = durs[mi] / count;
    for (let bi = 0; bi < count; bi++) {
      out.push({ measure: mi, beat: bi, time: starts[mi] + bi * beatDur });
    }
  }
  return out;
}

const SALAMANDER_URLS: Record<string, string> = {
  A0: "A0.mp3",
  C1: "C1.mp3",
  "D#1": "Ds1.mp3",
  "F#1": "Fs1.mp3",
  A1: "A1.mp3",
  C2: "C2.mp3",
  "D#2": "Ds2.mp3",
  "F#2": "Fs2.mp3",
  A2: "A2.mp3",
  C3: "C3.mp3",
  "D#3": "Ds3.mp3",
  "F#3": "Fs3.mp3",
  A3: "A3.mp3",
  C4: "C4.mp3",
  "D#4": "Ds4.mp3",
  "F#4": "Fs4.mp3",
  A4: "A4.mp3",
  C5: "C5.mp3",
  "D#5": "Ds5.mp3",
  "F#5": "Fs5.mp3",
  A5: "A5.mp3",
  C6: "C6.mp3",
  "D#6": "Ds6.mp3",
  "F#6": "Fs6.mp3",
  A6: "A6.mp3",
  C7: "C7.mp3",
  "D#7": "Ds7.mp3",
  "F#7": "Fs7.mp3",
  A7: "A7.mp3",
  C8: "C8.mp3",
};

type ToneModule = typeof import("tone");

/** Lecteur partagé (lazy) : un Sampler Salamander pour toute la session. */
export class PianoPlayer {
  private tone: ToneModule | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private sampler: any = null;
  private loaded = false;
  private part: { dispose: () => void } | null = null;
  /** Callback de surlignage : temps en cours (ou null quand la lecture cesse). */
  private onBeat: ((pos: PlaybackPosition | null) => void) | null = null;
  /** Avancement 0..1 poussé par la même boucle rAF que le surlignage. */
  private onProgress: ((ratio: number) => void) | null = null;
  /** Boucle d'animation du surlignage (requestAnimationFrame). */
  private raf: number | null = null;

  async ensureReady(): Promise<void> {
    if (this.loaded) return;
    this.tone = await import("tone");
    await this.tone.start();
    this.sampler = new this.tone.Sampler({
      urls: SALAMANDER_URLS,
      release: 1,
      baseUrl: "https://tonejs.github.io/audio/salamander/",
    }).toDestination();
    await this.tone.loaded();
    this.loaded = true;
  }

  async play(
    result: ScoreResult,
    onDone?: () => void,
    enabledVoices?: ReadonlySet<string>,
    tempoSettings?: TempoSettings,
    onBeat?: (pos: PlaybackPosition | null) => void,
    /**
     * Avancement 0..1, appelé depuis la MÊME boucle rAF que `onBeat`.
     * L'appelant DOIT l'écrire dans le DOM par une ref, jamais via setState :
     * un rendu React par pulsation sature le thread principal et désynchronise
     * l'ordonnanceur de Tone (cf. l'en-tête de playbackHighlight.ts).
     */
    onProgress?: (ratio: number) => void,
  ): Promise<void> {
    await this.ensureReady();
    const Tone = this.tone!;
    this.stop();
    this.onBeat = onBeat ?? null;
    this.onProgress = onProgress ?? null;

    const events = scoreToEvents(result, enabledVoices, tempoSettings);
    if (events.length === 0) {
      onDone?.();
      return;
    }

    const end =
      Math.max(...events.map((e) => e.time + e.duration)) + 0.3;

    // Transport relatif : 0 = maintenant.
    Tone.Transport.cancel();
    Tone.Transport.stop();
    Tone.Transport.position = 0;

    const part = new Tone.Part((time, value) => {
      const e = value as ScheduledNote;
      this.sampler.triggerAttackRelease(e.note, e.duration, time);
    }, events.map((e) => [e.time, e]));
    part.start(0);
    this.part = part;

    Tone.Transport.start();

    Tone.Transport.scheduleOnce(() => {
      this.stop();
      onDone?.();
    }, end);

    // Surlignage du temps en cours : UNE boucle rAF qui lit la position RÉELLE
    // du transport (Tone.Transport.seconds) et avance un pointeur dans la liste
    // des temps. On n'ajoute AUCUN événement à l'ordonnanceur (sinon des
    // centaines de callbacks Transport+Draw le saturent → notes en retard/coupées
    // et surlignage désynchronisé de l'audio). Ici le vert suit exactement le son.
    // L'avancement passe par CETTE boucle et pas par une seconde : deux rAF
    // concurrentes se disputeraient le thread que l'audio doit garder libre.
    if ((onBeat || onProgress) && typeof requestAnimationFrame !== "undefined") {
      const beats = onBeat ? beatTimeline(result, enabledVoices, tempoSettings) : [];
      const Transport = Tone.Transport;
      let bi = -1;
      let lastRatio = -1;
      const tick = () => {
        const pos = Transport.seconds;

        if (beats.length > 0) {
          let ni = bi;
          while (ni + 1 < beats.length && beats[ni + 1].time <= pos) ni++;
          if (ni >= 0 && ni !== bi) {
            bi = ni;
            this.onBeat?.({ measure: beats[bi].measure, beat: beats[bi].beat });
          }
        }

        if (this.onProgress) {
          // Arrondi au millième : à 60 fps sur une pièce de 3 min, écrire le
          // DOM à chaque frame pour un déplacement sub-pixel est du gaspillage.
          const ratio = Math.round(Math.min(1, Math.max(0, pos / end)) * 1000) / 1000;
          if (ratio !== lastRatio) {
            lastRatio = ratio;
            this.onProgress(ratio);
          }
        }

        this.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
    }
  }

  /** Joue une note isolée (clavier du dock). `name` = notation Tone, ex. "C4". */
  async note(name: string, duration = 0.9): Promise<void> {
    await this.ensureReady();
    this.sampler?.triggerAttackRelease(name, duration);
  }

  /** Le sampler est-il prêt ? Le clavier reste inerte tant qu'il ne l'est pas. */
  isLoaded(): boolean {
    return this.loaded;
  }

  stop(): void {
    if (!this.tone) return;
    if (this.raf != null && typeof cancelAnimationFrame !== "undefined") {
      cancelAnimationFrame(this.raf);
    }
    this.raf = null;
    try {
      this.part?.dispose();
    } catch {
      /* rien */
    }
    this.part = null;
    this.tone.Transport.cancel();
    this.tone.Transport.stop();
    this.tone.Transport.position = 0;
    try {
      this.sampler?.releaseAll?.();
    } catch {
      /* rien */
    }
    // Efface le surlignage quelle que soit la cause de l'arrêt (fin, Stop,
    // changement de partition, dispose).
    this.onBeat?.(null);
    this.onBeat = null;
    this.onProgress?.(0);
    this.onProgress = null;
  }

  dispose(): void {
    this.stop();
    try {
      this.sampler?.dispose?.();
    } catch {
      /* rien */
    }
    this.sampler = null;
    this.loaded = false;
  }
}

let shared: PianoPlayer | null = null;

export function getPianoPlayer(): PianoPlayer {
  if (!shared) shared = new PianoPlayer();
  return shared;
}
