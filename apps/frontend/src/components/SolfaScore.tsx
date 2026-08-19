"use client";

import {
  useState,
  useCallback,
  useMemo,
  useEffect,
  useRef,
  forwardRef,
  useImperativeHandle,
  memo,
} from "react";
import { flushSync } from "react-dom";
import { IBM_Plex_Mono, Source_Serif_4 } from "next/font/google";
import type { Measure as ModelMeasure, ScoreResult, TripletMark, VoiceModel } from "@/lib/types";
import { TempoControl } from "@/components/TempoControl";
import { buildSolfaMarkdown } from "@/lib/solfaMarkdown";
import {
  beatScheduleForScore,
  buildSolfaSystems,
  measuresPerSystemFor,
  printMeasuresPerSystemFor,
  stripMeasureAnnotations,
  type SolfaSystem,
} from "@/lib/solfaScore";
import type { TempoSettings } from "@/lib/tempo";
import {
  cloneScore,
  parseSolfaNotation,
  rebuildVoiceNotation,
  regenerateFromModels,
  splitVoiceForDivisi,
} from "@/lib/scoreEdit";
import { voiceAbbr } from "@/lib/voiceAbbr";
import {
  analyzeBeatFill,
  analyzeTripletFill,
  beatDivisionsFor,
  gridHasBeatErrors,
  normalizeGridCascade,
  deletePullNextNote,
  pullBeatsLeft,
  resolveBeatSchedule,
  shiftBeatTailToNext,
} from "@/lib/solfaRhythmEdit";
import {
  applyDirective,
  beatDivScheduleForModel,
  beatScheduleForModel,
  chipsForMeasure,
  effectiveTimeSignature,
  effectiveTonic,
  removeDirectiveChip,
  solfaPulseCount,
  type DirectiveChip,
  type DirectivePayload,
} from "@/lib/measureDirectives";
import { MeasureDirectiveMenu } from "@/components/MeasureDirectiveMenu";
import { AddVoiceMenu } from "@/components/AddVoiceMenu";
import { BeatAnnotationMenu } from "@/components/BeatAnnotationMenu";
import {
  applyBeatAnnotation,
  globalChipsForBeat,
  removeBeatAnnotationChip,
  type BeatAnnotationChip,
  type BeatAnnotationPayload,
} from "@/lib/beatAnnotations";
import { TripletChoiceMenu } from "@/components/TripletChoiceMenu";
import { TripletBracket } from "@/components/TripletBracket";
import {
  applyTriplet,
  applyTripletToGrid,
  beatIndexAfterTriplet,
  expandGridSlotsForTriplets,
  isTripletPairContinuation,
  mergeTripletBeatRaw,
  removeTripletAt,
  tripletPlusAction,
  tripletRoleAt,
  tripletSpanBeatsAt,
} from "@/lib/triplets";

const solfaMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

const solfaSerif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  display: "swap",
  style: ["normal", "italic"],
});

const KNOWN_SUBTITLES: Record<string, string> = {
  "hitahy anao anie ny tompo": "The Lord bless you and keep you",
};

function prettyTitle(raw: string): string {
  const t = raw.replace(/\s+/g, " ").trim();
  if (!t) return "Partition";
  if (/\s/.test(t) && t.length < 80) return t;
  return t
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim();
}

function lookupSubtitle(title: string): string | null {
  const key = title.toLowerCase().replace(/\s+/g, " ").trim();
  return KNOWN_SUBTITLES[key] ?? null;
}

export function notationToGrid(
  notation: string,
  beatsPerMeasure: number | number[],
): string[][] {
  const rawRows = notation
    .split("|")
    .map((m) => stripMeasureAnnotations(m).split(/[:!]/).map((b) => b.trim()))
    .filter((beats) => beats.length > 0);
  const schedule = resolveBeatSchedule(
    beatsPerMeasure,
    Math.max(1, rawRows.length),
  );
  const rows = rawRows.map((beats, mi) => {
    const bpm = schedule[mi] ?? schedule[schedule.length - 1] ?? 4;
    const row = [...beats];
    while (row.length < bpm) row.push("");
    return row.slice(0, bpm);
  });
  return rows.length
    ? rows
    : [Array.from({ length: schedule[0] ?? 4 }, () => "")];
}

function emptyMeasureRow(schedule: number[], measureIndex: number): string[] {
  const bpm =
    schedule[Math.min(measureIndex, schedule.length - 1)] ??
    schedule[schedule.length - 1] ??
    4;
  return Array.from({ length: bpm }, () => "");
}

function meterPrefixesFromModel(
  model: VoiceModel,
  measureCount: number,
): Array<{ beats?: number; beatType?: number; keyTonic?: string } | null> {
  return Array.from({ length: measureCount }, (_, i) => {
    const m = model.measures[i];
    const ts = m?.timeSignature;
    const keyTonic = m?.keyTonic;
    // Changement de métrique et/ou de tonalité (Doh=X) en tête de mesure :
    // réémis dans la notation pour que le parseur les relise.
    if (!ts && !keyTonic) return null;
    return {
      ...(ts ? { beats: ts.beats, beatType: ts.beatType } : {}),
      ...(keyTonic ? { keyTonic } : {}),
    };
  });
}

function schedulesForScore(result: ScoreResult, measureCount: number): {
  beatSchedule: number[];
  beatDivSchedule: number[];
} {
  const model = result.voices[0]?.model;
  if (model && model.measures.length > 0) {
    return {
      beatSchedule: beatScheduleForModel(model, measureCount),
      beatDivSchedule: beatDivScheduleForModel(model, measureCount),
    };
  }
  const { beats, beatType } = result.header.timeSignature;
  const pulses = solfaPulseCount(beats || 4, beatType || 4);
  const div = beatDivisionsFor(beatType || 4, beats || 4);
  return {
    beatSchedule: Array.from({ length: Math.max(1, measureCount) }, () => pulses),
    beatDivSchedule: Array.from({ length: Math.max(1, measureCount) }, () => div),
  };
}

function beatKey(voiceName: string, measureAbs: number, beatIndex: number): string {
  return `${voiceName}::${measureAbs}::${beatIndex}`;
}

function beatSepLabel(beatIndex: number, midBeat: number): string {
  return beatIndex + 1 === midBeat ? "!" : ":";
}

function renderTripletPlus(
  voiceName: string,
  measureAbs: number,
  beatIndex: number,
  tripletRole: ReturnType<typeof tripletRoleAt>,
  busy: boolean,
  onTripletPlusClick: (
    voiceName: string,
    measureAbs: number,
    beatIndex: number,
    clientX: number,
    clientY: number,
  ) => void,
) {
  return (
    <button
      type="button"
      className="solfa-beat-plus solfa-beat-plus--voice"
      title={tripletRole ? "Retirer le triolet" : "Triolet (3 notes)"}
      disabled={busy}
      aria-label={`Triolet ${voiceName} mesure ${measureAbs + 1} temps ${beatIndex + 1}`}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        const r = (e.target as HTMLElement).getBoundingClientRect();
        onTripletPlusClick(
          voiceName,
          measureAbs,
          beatIndex,
          r.left + r.width / 2,
          r.top - 4,
        );
      }}
    >
      +
    </button>
  );
}

function focusBeatInput(voiceName: string, measureAbs: number, beatIndex: number): boolean {
  const key = beatKey(voiceName, measureAbs, beatIndex);
  const el = document.querySelector<HTMLInputElement>(
    `input[data-solfa-beat="${CSS.escape(key)}"]`,
  );
  if (!el || el.disabled) return false;
  el.focus();
  el.select();
  el.scrollIntoView({ block: "nearest", inline: "nearest" });
  return true;
}

type BeatNavDir = "left" | "right" | "up" | "down";

function bpmAtSchedule(schedule: number[], measureAbs: number): number {
  return (
    schedule[Math.min(measureAbs, schedule.length - 1)] ??
    schedule[schedule.length - 1] ??
    4
  );
}

/** Cellule éditable voisine (saute les slots compagnons de triolet 2 temps). */
function neighborBeatCell(
  voiceNames: string[],
  voiceTriplets: (name: string) => TripletMark[] | undefined,
  voiceSchedule: (name: string) => number[],
  measureCount: number,
  voiceName: string,
  measureAbs: number,
  beatIndex: number,
  dir: BeatNavDir,
): { voiceName: string; measureAbs: number; beatIndex: number } | null {
  if (dir === "up" || dir === "down") {
    const vi = voiceNames.indexOf(voiceName);
    if (vi < 0) return null;
    const step = dir === "up" ? -1 : 1;
    for (let i = vi + step; i >= 0 && i < voiceNames.length; i += step) {
      const vn = voiceNames[i]!;
      const triplets = voiceTriplets(vn);
      let bi = beatIndex;
      if (isTripletPairContinuation(triplets, measureAbs, bi)) bi -= 1;
      if (bi < 0) continue;
      return { voiceName: vn, measureAbs, beatIndex: bi };
    }
    return null;
  }

  const triplets = voiceTriplets(voiceName);
  const sched = voiceSchedule(voiceName);
  let mi = measureAbs;
  let bi = beatIndex;

  if (dir === "right") {
    bi = beatIndexAfterTriplet(triplets, mi, bi);
    if (bi >= bpmAtSchedule(sched, mi)) {
      mi += 1;
      bi = 0;
    }
    if (mi >= measureCount) return null;
    if (isTripletPairContinuation(triplets, mi, bi)) {
      bi = beatIndexAfterTriplet(triplets, mi, bi - 1);
      if (bi >= bpmAtSchedule(sched, mi)) {
        mi += 1;
        bi = 0;
      }
      if (mi >= measureCount) return null;
    }
    return { voiceName, measureAbs: mi, beatIndex: bi };
  }

  // left
  bi -= 1;
  if (bi < 0) {
    mi -= 1;
    if (mi < 0) return null;
    bi = bpmAtSchedule(sched, mi) - 1;
  }
  while (bi >= 0 && isTripletPairContinuation(triplets, mi, bi)) bi -= 1;
  if (bi < 0) {
    mi -= 1;
    if (mi < 0) return null;
    bi = bpmAtSchedule(sched, mi) - 1;
    while (bi >= 0 && isTripletPairContinuation(triplets, mi, bi)) bi -= 1;
    if (bi < 0) return null;
  }
  return { voiceName, measureAbs: mi, beatIndex: bi };
}

/** Focus immédiat sans setState — blur de la cellule courante commit via refs. */
function navigateBeatCell(
  voiceNames: string[],
  voiceTriplets: (name: string) => TripletMark[] | undefined,
  voiceSchedule: (name: string) => number[],
  measureCount: number,
  voiceName: string,
  measureAbs: number,
  beatIndex: number,
  dir: BeatNavDir,
): boolean {
  let vn = voiceName;
  let mi = measureAbs;
  let bi = beatIndex;
  for (let attempt = 0; attempt < 64; attempt++) {
    const next = neighborBeatCell(
      voiceNames,
      voiceTriplets,
      voiceSchedule,
      measureCount,
      vn,
      mi,
      bi,
      dir,
    );
    if (!next) return false;
    if (focusBeatInput(next.voiceName, next.measureAbs, next.beatIndex)) {
      return true;
    }
    // Voix absente sur cette mesure (enterMeasure) → continuer dans la même direction.
    vn = next.voiceName;
    mi = next.measureAbs;
    bi = next.beatIndex;
  }
  return false;
}

function shouldLeaveCellOnArrow(input: HTMLInputElement, dir: "left" | "right"): boolean {
  const start = input.selectionStart ?? 0;
  const end = input.selectionEnd ?? 0;
  const len = input.value.length;
  const allSelected = start === 0 && end === len;
  const collapsed = start === end;
  if (dir === "left") return allSelected || (collapsed && start === 0);
  return allSelected || (collapsed && end === len);
}

type LyricsState = Record<string, string>;
type LyricsChange = (key: string, value: string) => void;

/**
 * Input d'un temps : état local pour la frappe.
 * Évite de re-rendre toute la partition (milliers d'inputs) à chaque touche —
 * les brouillons sont synchronisés via `onDraft` (ref parent, pas de setState).
 */
const SolfaBeatInput = memo(function SolfaBeatInput({
  cellKey,
  committedValue,
  beatDiv,
  tripletSpan,
  gridHasError,
  busy,
  voiceName,
  measureAbs,
  beatIndex,
  onDraft,
  onCommit,
  onSpaceShift,
  onBackspacePull,
  onDeletePull,
  onNavigate,
}: {
  cellKey: string;
  committedValue: string;
  beatDiv: number;
  tripletSpan?: 1 | 2 | null;
  gridHasError: boolean;
  busy: boolean;
  voiceName: string;
  measureAbs: number;
  beatIndex: number;
  onDraft: (key: string, value: string) => void;
  onCommit: (voiceName: string, measureAbs: number, beatIndex: number, value: string) => void;
  onSpaceShift: (
    voiceName: string,
    measureAbs: number,
    beatIndex: number,
    value: string,
    caretIndex: number,
  ) => void;
  onBackspacePull: (voiceName: string, measureAbs: number, beatIndex: number) => void;
  onDeletePull: (
    voiceName: string,
    measureAbs: number,
    beatIndex: number,
    value: string,
    caretIndex: number,
  ) => void;
  onNavigate: (
    voiceName: string,
    measureAbs: number,
    beatIndex: number,
    dir: BeatNavDir,
  ) => void;
}) {
  const [draft, setDraft] = useState(committedValue);
  useEffect(() => {
    setDraft(committedValue);
  }, [committedValue]);

  const fill = tripletSpan
    ? analyzeTripletFill(draft, tripletSpan, beatDiv)
    : analyzeBeatFill(draft, beatDiv);
  const hasError =
    fill.status === "under" ||
    fill.status === "over" ||
    fill.status === "invalid" ||
    (draft === committedValue && gridHasError);

  return (
    <input
      data-solfa-beat={cellKey}
      className={`solfa-note-input${hasError ? " solfa-note-input--error" : ""}${tripletSpan === 2 ? " solfa-note-input--triplet-pair" : ""}${tripletSpan ? " solfa-note-input--triplet" : ""}`}
      value={draft}
      disabled={busy}
      spellCheck={false}
      title={
        hasError
          ? tripletSpan
            ? "Triolet : 3 notes collées attendues (ex. drm)"
            : "Temps incomplet ou trop long (total ≠ 1 temps)"
          : tripletSpan
            ? "Triolet : saisir 3 notes collées (ex. drm) · ←→↑↓ naviguer"
            : "Espace = couper · ←→↑↓ naviguer · Backspace (vide) = remonter · Suppr (fin) = tirer la note suivante"
      }
      aria-invalid={hasError}
      aria-label={`${voiceName} mesure ${measureAbs + 1} temps ${beatIndex + 1}`}
      onChange={(e) => {
        const value = e.target.value;
        setDraft(value);
        onDraft(cellKey, value);
      }}
      onBlur={(e) => {
        const value = e.target.value;
        queueMicrotask(() => {
          onCommit(voiceName, measureAbs, beatIndex, value);
        });
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
          return;
        }

        const input = e.target as HTMLInputElement;
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          const dir = e.key === "ArrowLeft" ? "left" : "right";
          if (shouldLeaveCellOnArrow(input, dir)) {
            e.preventDefault();
            onNavigate(voiceName, measureAbs, beatIndex, dir);
          }
          return;
        }
        if (e.key === "ArrowUp" || e.key === "ArrowDown") {
          e.preventDefault();
          onNavigate(
            voiceName,
            measureAbs,
            beatIndex,
            e.key === "ArrowUp" ? "up" : "down",
          );
          return;
        }

        // Triolet : aucune auto-correction (pas de découpe / pull / cascade).
        if (tripletSpan) {
          if (e.key === " " || e.code === "Space") {
            e.preventDefault();
          }
          return;
        }
        if (e.key === " " || e.code === "Space") {
          e.preventDefault();
          const caret = input.selectionStart ?? input.value.length;
          onSpaceShift(voiceName, measureAbs, beatIndex, input.value, caret);
          return;
        }
        if (e.key === "Backspace") {
          if (input.value.trim() === "") {
            e.preventDefault();
            onBackspacePull(voiceName, measureAbs, beatIndex);
          }
          return;
        }
        if (e.key === "Delete") {
          const caret = input.selectionStart ?? input.value.length;
          const end = input.selectionEnd ?? caret;
          if (caret !== end || caret < input.value.length) return;
          e.preventDefault();
          onDeletePull(voiceName, measureAbs, beatIndex, input.value, caret);
        }
      }}
    />
  );
});

const EMPTY_OVERRIDES: Record<string, string> = {};

const SolfaSystemBlock = memo(function SolfaSystemBlock({
  system,
  lyrics,
  onLyricChange,
  onBeatDraft,
  onBeatCommit,
  onSpaceShift,
  onBackspacePull,
  onDeletePull,
  beatErrors,
  beatDivSchedule,
  cellOverrides,
  busy,
  measureModel,
  onOpenDirective,
  onRemoveChip,
  onNavigate,
  onOpenAnnotation,
  onRemoveAnnotationChip,
  voiceMeasure,
  voiceModel,
  primaryVoiceName,
  beatSchedule,
  onTripletPlusClick,
  onAddVoice,
}: {
  system: SolfaSystem;
  lyrics: LyricsState;
  onLyricChange: LyricsChange;
  onBeatDraft: (key: string, value: string) => void;
  onBeatCommit: (voiceName: string, measureAbs: number, beatIndex: number, value: string) => void;
  onSpaceShift: (
    voiceName: string,
    measureAbs: number,
    beatIndex: number,
    value: string,
    caretIndex: number,
  ) => void;
  onBackspacePull: (voiceName: string, measureAbs: number, beatIndex: number) => void;
  onDeletePull: (
    voiceName: string,
    measureAbs: number,
    beatIndex: number,
    value: string,
    caretIndex: number,
  ) => void;
  beatErrors: Record<string, boolean>;
  beatDivSchedule: number[];
  /** Overrides de cellules pour ce système uniquement (ref stable si vide). */
  cellOverrides: Record<string, string>;
  busy: boolean;
  measureModel: (measureAbs: number) => ModelMeasure | undefined;
  onOpenDirective: (measureAbs: number, clientX: number, clientY: number) => void;
  onRemoveChip: (measureAbs: number, chip: DirectiveChip) => void;
  onNavigate: (
    voiceName: string,
    measureAbs: number,
    beatIndex: number,
    dir: BeatNavDir,
  ) => void;
  onOpenAnnotation: (
    voiceName: string,
    measureAbs: number,
    beatIndex: number,
    clientX: number,
    clientY: number,
  ) => void;
  onRemoveAnnotationChip: (
    voiceName: string,
    measureAbs: number,
    chip: BeatAnnotationChip,
  ) => void;
  voiceMeasure: (voiceName: string, measureAbs: number) => ModelMeasure | undefined;
  voiceModel: (voiceName: string) => VoiceModel | undefined;
  primaryVoiceName: string;
  beatSchedule: number[];
  onTripletPlusClick: (
    voiceName: string,
    measureAbs: number,
    beatIndex: number,
    clientX: number,
    clientY: number,
  ) => void;
  onAddVoice: (measureAbs: number, clientX: number, clientY: number) => void;
}) {
  const N = system.voices[0]?.measures.length ?? 0;

  return (
    <div className="solfa-system">
      <div className="solfa-meta-row" aria-label="Directives et nuances">
        <div className="solfa-label" aria-hidden />
        <div className="solfa-row-content">
          {Array.from({ length: N }, (_, mi) => {
            const measureAbs = system.startNumber - 1 + mi;
            const B = system.voices[0]?.measures[mi]?.beats.length ?? 0;
            const measureChips = chipsForMeasure(measureModel(measureAbs));
            const pm = voiceMeasure(primaryVoiceName, measureAbs);
            const pvm = voiceModel(primaryVoiceName);
            return (
              <div key={mi} className="solfa-measure">
                <span className="solfa-bar-slot solfa-bar-slot--meta">
                  <button
                    type="button"
                    className="solfa-bar-plus"
                    title="Directive de mesure (D.C., tempo, mesure, Doh…)"
                    disabled={busy}
                    aria-label={`Directive mesure ${measureAbs + 1}`}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      const r = (e.target as HTMLElement).getBoundingClientRect();
                      onOpenDirective(measureAbs, r.left, r.bottom + 4);
                    }}
                  >
                    +
                  </button>
                  {mi === 0 && (
                    <span className="solfa-measure-num">{system.startNumber}</span>
                  )}
                </span>
                {Array.from({ length: B }, (_, bi) => {
                  const exprChips =
                    pm && pvm ? globalChipsForBeat(pm, pvm, measureAbs, bi) : [];
                  return (
                    <span key={bi} className="solfa-meta-cell">
                      <span className="solfa-meta-stack">
                        {bi === 0 &&
                          measureChips.map((chip) => (
                            <span key={chip.key} className="solfa-meta-chip solfa-meta-chip--measure">
                              <span>{chip.label}</span>
                              <button
                                type="button"
                                className="solfa-meta-chip-x"
                                title="Retirer"
                                aria-label={`Retirer ${chip.label}`}
                                disabled={busy}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onRemoveChip(measureAbs, chip);
                                }}
                              >
                                ×
                              </button>
                            </span>
                          ))}
                        {exprChips.map((chip) => (
                          <span key={chip.key} className="solfa-meta-chip">
                            <span>{chip.label}</span>
                            <button
                              type="button"
                              className="solfa-meta-chip-x"
                              title="Retirer"
                              aria-label={`Retirer ${chip.label}`}
                              disabled={busy}
                              onClick={(e) => {
                                e.stopPropagation();
                                onRemoveAnnotationChip(primaryVoiceName, measureAbs, chip);
                              }}
                            >
                              ×
                            </button>
                          </span>
                        ))}
                      </span>
                      <button
                        type="button"
                        className="solfa-beat-plus solfa-beat-plus--expr"
                        title="Nuance ou soufflet (toutes les voix)"
                        disabled={busy}
                        aria-label={`Nuance mesure ${measureAbs + 1} temps ${bi + 1}`}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          const r = (e.target as HTMLElement).getBoundingClientRect();
                          onOpenAnnotation(
                            primaryVoiceName,
                            measureAbs,
                            bi,
                            r.left + r.width / 2,
                            r.top - 4,
                          );
                        }}
                      >
                        +
                      </button>
                    </span>
                  );
                })}
              </div>
            );
          })}
          <span className="solfa-bar-slot solfa-bar-slot--meta" aria-hidden />
        </div>
      </div>

      <div className="solfa-music">
        {system.voices.map((voice, vi) => (
          <div key={voice.name} className="solfa-voice-row">
            <div className="solfa-label">
              <span className="solfa-abbr">{voiceAbbr(voice.name)}</span>
            </div>

            <div className="solfa-row-content">
              {voice.measures.map((measure, mi) => {
                const measureAbs = system.startNumber - 1 + mi;
                const B = measure.beats.length;
                const midBeat = Math.floor(B / 2);
                const div =
                  beatDivSchedule[Math.min(measureAbs, beatDivSchedule.length - 1)] ??
                  beatDivSchedule[beatDivSchedule.length - 1] ??
                  4;
                return (
                  <div key={mi} className="solfa-measure">
                    <span className="solfa-bar">|</span>
                    {measure.beats.map((beat, bi) => {
                      const key = beatKey(voice.name, measureAbs, bi);
                      const committed = cellOverrides[key] ?? beat.raw;
                      const vm = voiceModel(voice.name);
                      const triplets = vm?.triplets;
                      if (isTripletPairContinuation(triplets, measureAbs, bi)) {
                        return null;
                      }
                      const tripletRole = tripletRoleAt(triplets, measureAbs, bi);

                      if (tripletRole === "start" && measure.beats[bi + 1]) {
                        const beat2 = measure.beats[bi + 1]!;
                        const key2 = beatKey(voice.name, measureAbs, bi + 1);
                        const committedPair = mergeTripletBeatRaw(
                          committed,
                          cellOverrides[key2] ?? beat2.raw,
                        );
                        const lastInPair = bi + 1;
                        return (
                          <span
                            key={bi}
                            className="solfa-beat-group solfa-beat-group--triplet solfa-beat-group--triplet-pair"
                            data-pm={measureAbs}
                            data-pbf={bi}
                            data-pbt={bi + 1}
                          >
                            <TripletBracket role="pair" />
                            {renderTripletPlus(
                              voice.name,
                              measureAbs,
                              bi,
                              tripletRole,
                              busy,
                              onTripletPlusClick,
                            )}
                            <span className="solfa-beat-row solfa-beat-row--triplet-pair">
                              <SolfaBeatInput
                                cellKey={key}
                                committedValue={committedPair}
                                beatDiv={div}
                                tripletSpan={2}
                                gridHasError={!!beatErrors[key]}
                                busy={busy}
                                voiceName={voice.name}
                                measureAbs={measureAbs}
                                beatIndex={bi}
                                onDraft={onBeatDraft}
                                onCommit={onBeatCommit}
                                onSpaceShift={onSpaceShift}
                                onBackspacePull={onBackspacePull}
                                onDeletePull={onDeletePull}
                                onNavigate={onNavigate}
                              />
                              {lastInPair < B - 1 && (
                                <span className="solfa-sep">
                                  {beatSepLabel(lastInPair, midBeat)}
                                </span>
                              )}
                            </span>
                          </span>
                        );
                      }

                      return (
                        <span
                          key={bi}
                          className={`solfa-beat-group${tripletRole ? " solfa-beat-group--triplet" : ""}`}
                          data-pm={measureAbs}
                          data-pbf={bi}
                          data-pbt={bi}
                        >
                          {tripletRole === "single" && <TripletBracket role="single" />}
                          {renderTripletPlus(
                            voice.name,
                            measureAbs,
                            bi,
                            tripletRole,
                            busy,
                            onTripletPlusClick,
                          )}
                          <span className="solfa-beat-row">
                            <SolfaBeatInput
                              cellKey={key}
                              committedValue={committed}
                              beatDiv={div}
                              tripletSpan={tripletRole === "single" ? 1 : null}
                              gridHasError={!!beatErrors[key]}
                              busy={busy}
                              voiceName={voice.name}
                              measureAbs={measureAbs}
                              beatIndex={bi}
                              onDraft={onBeatDraft}
                              onCommit={onBeatCommit}
                              onSpaceShift={onSpaceShift}
                              onBackspacePull={onBackspacePull}
                              onDeletePull={onDeletePull}
                              onNavigate={onNavigate}
                            />
                            {bi < B - 1 && (
                              <span className="solfa-sep">{beatSepLabel(bi, midBeat)}</span>
                            )}
                          </span>
                        </span>
                      );
                    })}
                  </div>
                );
              })}
              <span className="solfa-bar">|</span>
            </div>
          </div>
        ))}
      </div>

      <div className="solfa-addvoice-row" aria-label="Ajouter une voix">
        <div className="solfa-label" aria-hidden />
        <div className="solfa-row-content">
          {Array.from({ length: N }, (_, mi) => {
            const measureAbs = system.startNumber - 1 + mi;
            return (
              <div key={mi} className="solfa-addvoice-cell">
                <div className="solfa-bar-slot">
                  <button
                    type="button"
                    className="solfa-bar-plus"
                    title="Ajouter une voix (divisi) à partir de cette mesure"
                    disabled={busy}
                    aria-label={`Ajouter une voix à partir de la mesure ${measureAbs + 1}`}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      const r = (e.target as HTMLElement).getBoundingClientRect();
                      onAddVoice(measureAbs, r.left, r.bottom + 4);
                    }}
                  >
                    +
                  </button>
                </div>
              </div>
            );
          })}
          <div className="solfa-bar-slot" aria-hidden />
        </div>
      </div>

      <div className="solfa-lyrics-row">
        <div className="solfa-label solfa-label--lyrics" aria-hidden />
        <div className="solfa-row-content">
          {Array.from({ length: N }, (_, mi) => {
            const B = system.voices[0]?.measures[mi]?.beats.length ?? 0;
            const midBeat = Math.floor(B / 2);
            // Clé indexée sur la mesure ABSOLUE (pas la position dans le système)
            // pour que les paroles suivent leur mesure quand la mise en page
            // change — notamment le reflow d'impression (moins de mesures/ligne).
            const measureAbs = system.startNumber - 1 + mi;
            return (
              <div key={mi} className="solfa-measure solfa-measure--lyrics">
                <span className="solfa-bar solfa-bar--ghost">|</span>
                {Array.from({ length: B }, (_, bi) => (
                  <span key={bi} className="solfa-beat-group">
                    <input
                      className="solfa-lyric-input"
                      value={lyrics[`${measureAbs}-${bi}`] ?? ""}
                      onChange={(e) =>
                        onLyricChange(`${measureAbs}-${bi}`, e.target.value)
                      }
                      aria-label={`Paroles mesure ${measureAbs + 1} temps ${bi + 1}`}
                    />
                    {bi < B - 1 && (
                      <span className="solfa-sep solfa-sep--ghost" aria-hidden>
                        {bi + 1 === midBeat ? "!" : ":"}
                      </span>
                    )}
                  </span>
                ))}
              </div>
            );
          })}
          <span className="solfa-bar solfa-bar--ghost">|</span>
        </div>
      </div>
    </div>
  );
});

function errorsForVoice(
  voiceName: string,
  grid: string[][],
  beatDiv: number | number[],
  triplets?: TripletMark[],
): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  grid.forEach((measure, mi) => {
    const div = Array.isArray(beatDiv)
      ? beatDiv[Math.min(mi, beatDiv.length - 1)] ?? beatDiv[beatDiv.length - 1] ?? 4
      : beatDiv;
    measure.forEach((beat, bi) => {
      if (isTripletPairContinuation(triplets, mi, bi)) {
        out[beatKey(voiceName, mi, bi)] = false;
        return;
      }
      const span = tripletSpanBeatsAt(triplets, mi, bi);
      const fill = span
        ? analyzeTripletFill(beat, span, div)
        : analyzeBeatFill(beat, div);
      out[beatKey(voiceName, mi, bi)] =
        fill.status === "under" || fill.status === "over" || fill.status === "invalid";
    });
  });
  return out;
}

function padGrid(grid: string[][], beatsPerMeasure: number | number[]): string[][] {
  const schedule = resolveBeatSchedule(beatsPerMeasure, grid.length);
  return grid.map((row, mi) => {
    const bpm = schedule[mi] ?? schedule[schedule.length - 1] ?? 4;
    const r = [...row];
    while (r.length < bpm) r.push("");
    return r.slice(0, bpm);
  });
}

export type SolfaScoreHandle = {
  /** Commit cellule active + brouillons, attend le parse, renvoie le score à jour. */
  flush: () => Promise<ScoreResult>;
  /** Exporte la partition sol-fa rendue en Markdown monospacé. */
  exportMarkdown: () => Promise<string>;
};

type SolfaScoreProps = {
  result: ScoreResult;
  tempo: TempoSettings;
  onTempoChange: (next: TempoSettings) => void;
  onChange?: (next: ScoreResult) => void;
};

export const SolfaScore = forwardRef<SolfaScoreHandle, SolfaScoreProps>(
  function SolfaScore({ result, tempo, onTempoChange, onChange }, ref) {
  const [lyrics, setLyrics] = useState<LyricsState>({});
  const [localGrids, setLocalGrids] = useState<Record<string, string[][]>>({});
  /** Commits simples (1 cellule) sans rebuild de toute la partition. */
  const [cellOverrides, setCellOverrides] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  /** Actif pendant l'impression : resserre le nombre de mesures par système. */
  const [printLayout, setPrintLayout] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [directiveMenu, setDirectiveMenu] = useState<{
    measureAbs: number;
    x: number;
    y: number;
  } | null>(null);
  const [annotationMenu, setAnnotationMenu] = useState<{
    voiceName: string;
    measureAbs: number;
    beatIndex: number;
    x: number;
    y: number;
  } | null>(null);
  const [tripletMenu, setTripletMenu] = useState<{
    voiceName: string;
    measureAbs: number;
    beatIndex: number;
    x: number;
    y: number;
  } | null>(null);
  const [addVoiceMenu, setAddVoiceMenu] = useState<{
    measureAbs: number;
    x: number;
    y: number;
  } | null>(null);
  /** Évite que le blur après Space re-commit l'ancienne cellule. */
  const skipBlurRef = useRef<string | null>(null);
  /** Focus post-décalage, appliqué après le re-render de la grille. */
  const pendingFocusRef = useRef<{
    voiceName: string;
    measureAbs: number;
    beatIndex: number;
  } | null>(null);

  const resultRef = useRef(result);
  resultRef.current = result;
  const localGridsRef = useRef(localGrids);
  localGridsRef.current = localGrids;
  const lyricsRef = useRef(lyrics);
  lyricsRef.current = lyrics;
  /** Brouillons de frappe : ref seule (pas de setState) pour ne pas re-rendre toute la partition. */
  const beatDraftsRef = useRef<Record<string, string>>({});
  const cellOverridesRef = useRef(cellOverrides);
  cellOverridesRef.current = cellOverrides;
  const latestResultRef = useRef(result);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  /** File d'attente des commits (blur / flush) pour éviter les courses. */
  const commitTailRef = useRef(Promise.resolve());
  /**
   * Après un flush local (triolet…) les grilles sont déjà à jour :
   * le prochain `result` ne doit pas les reconstruire depuis l'ancienne notation.
   */
  const skipNextGridResetRef = useRef(false);
  const handleLyricChange = useCallback<LyricsChange>((key, value) => {
    setLyrics((prev) => {
      const next = { ...prev, [key]: value };
      lyricsRef.current = next;
      return next;
    });
  }, []);

  const handleBeatDraft = useCallback((key: string, value: string) => {
    beatDraftsRef.current = { ...beatDraftsRef.current, [key]: value };
  }, []);

  const clearVoiceDrafts = useCallback((voiceName?: string) => {
    if (!voiceName) {
      beatDraftsRef.current = {};
      return;
    }
    const next = { ...beatDraftsRef.current };
    for (const k of Object.keys(next)) {
      if (k.startsWith(`${voiceName}::`)) delete next[k];
    }
    beatDraftsRef.current = next;
  }, []);

  const clearVoiceOverrides = useCallback((voiceName?: string) => {
    if (!voiceName) {
      cellOverridesRef.current = {};
      setCellOverrides({});
      return;
    }
    setCellOverrides((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const k of Object.keys(next)) {
        if (k.startsWith(`${voiceName}::`)) {
          delete next[k];
          changed = true;
        }
      }
      if (!changed) return prev;
      cellOverridesRef.current = next;
      return next;
    });
  }, []);

  const applyOverridesToGrid = useCallback(
    (voiceName: string, grid: string[][], sched: number[]) => {
      const out = grid.map((row) => [...row]);
      for (const src of [cellOverridesRef.current, beatDraftsRef.current]) {
        for (const [key, draft] of Object.entries(src)) {
          if (!key.startsWith(`${voiceName}::`)) continue;
          const [, miStr, biStr] = key.split("::");
          const mi = Number(miStr);
          const bi = Number(biStr);
          while (out.length <= mi) out.push(emptyMeasureRow(sched, out.length));
          if (!out[mi]) out[mi] = emptyMeasureRow(sched, mi);
          out[mi][bi] = draft;
        }
      }
      return out;
    },
    [],
  );

  const { header } = result;
  const beats = header.timeSignature.beats;
  const beatType = header.timeSignature.beatType;
  const headerPulses = solfaPulseCount(beats, beatType);

  // À l'impression, resserrer le nombre de mesures/système (voir
  // printMeasuresPerSystemFor). flushSync applique la bascule de façon
  // synchrone pendant beforeprint, avant que le navigateur ne fige la page ;
  // afterprint restaure la mise en page écran. Couvre le bouton PDF ET Ctrl+P.
  useEffect(() => {
    const before = () => flushSync(() => setPrintLayout(true));
    const after = () => flushSync(() => setPrintLayout(false));
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);

  const measureCountHint = useMemo(() => {
    const fromModel = Math.max(0, ...result.voices.map((v) => v.model.measures.length));
    const fromNotation = Math.max(
      0,
      ...result.voices.map(
        (v) =>
          v.notation
            .split("|")
            .map((m) => m.trim())
            .filter(Boolean).length,
      ),
    );
    const fromGrids = Math.max(
      0,
      ...Object.values(localGrids).map((g) => g.length),
    );
    return Math.max(1, fromModel, fromNotation, fromGrids);
  }, [result, localGrids]);

  const { beatSchedule, beatDivSchedule } = useMemo(
    () => schedulesForScore(result, measureCountHint),
    [result, measureCountHint],
  );

  useEffect(() => {
    latestResultRef.current = result;
    if (skipNextGridResetRef.current) {
      skipNextGridResetRef.current = false;
      beatDraftsRef.current = {};
      cellOverridesRef.current = {};
      setCellOverrides({});
      return;
    }
    const next: Record<string, string[][]> = {};
    let anyError = false;
    for (const voice of result.voices) {
      const n = Math.max(
        voice.model.measures.length,
        voice.notation.split("|").filter((m) => m.trim()).length,
        1,
      );
      const voiceBeatSchedule =
        voice.model.measures.length > 0
          ? beatScheduleForModel(voice.model, n)
          : beatScheduleForScore(result, n);
      const voiceDivSchedule =
        voice.model.measures.length > 0
          ? beatDivScheduleForModel(voice.model, n)
          : Array.from({ length: n }, () => beatDivisionsFor(beatType, beats));
      const raw = expandGridSlotsForTriplets(
        notationToGrid(voice.notation, voiceBeatSchedule),
        voiceBeatSchedule,
        voice.model.triplets,
      );
      const normalized = normalizeGridCascade(
        raw,
        voiceBeatSchedule,
        voiceDivSchedule,
        voice.model.triplets,
      );
      next[voice.name] = normalized;
      if (gridHasBeatErrors(normalized, voiceDivSchedule, voice.model.triplets)) anyError = true;
    }
    setLocalGrids(next);
    localGridsRef.current = next;
    beatDraftsRef.current = {};
    cellOverridesRef.current = {};
    setCellOverrides({});
    setError(
      anyError
        ? "Certains temps sont incomplets ou trop longs (surlignés en rouge)."
        : null,
    );
  }, [result, beats, beatType]);

  useEffect(() => {
    const pending = pendingFocusRef.current;
    if (!pending) return;
    pendingFocusRef.current = null;
    focusBeatInput(pending.voiceName, pending.measureAbs, pending.beatIndex);
  }, [localGrids]);

  const displayResult = useMemo(() => {
    if (Object.keys(localGrids).length === 0) return result;
    // Pas de cloneScore profond : uniquement la notation projetée depuis les grilles.
    return {
      ...result,
      voices: result.voices.map((voice) => {
        const grid = localGrids[voice.name];
        if (!grid) return voice;
        const sched =
          voice.model.measures.length > 0
            ? beatScheduleForModel(voice.model, grid.length)
            : beatSchedule;
        return {
          ...voice,
          notation: rebuildVoiceNotation(
            grid,
            sched,
            meterPrefixesFromModel(voice.model, grid.length),
            voice.model.triplets,
          ),
        };
      }),
    };
  }, [result, localGrids, beatSchedule]);

  const measuresPerSystem = printLayout
    ? printMeasuresPerSystemFor(headerPulses)
    : measuresPerSystemFor(headerPulses);
  const systems = useMemo(
    () => buildSolfaSystems(displayResult, measuresPerSystem),
    [displayResult, measuresPerSystem],
  );

  /** Overrides découpés par système — EMPTY stable si le système n'est pas touché (memo). */
  const overridesBySystem = useMemo(() => {
    const map = new Map<number, Record<string, string>>();
    for (const [key, val] of Object.entries(cellOverrides)) {
      const mi = Number(key.split("::")[1]);
      if (!Number.isFinite(mi)) continue;
      const sys = systems.find((s) => {
        const start = s.startNumber - 1;
        const n = s.voices[0]?.measures.length ?? 0;
        return mi >= start && mi < start + n;
      });
      if (!sys) continue;
      let bag = map.get(sys.startNumber);
      if (!bag) {
        bag = {};
        map.set(sys.startNumber, bag);
      }
      bag[key] = val;
    }
    return map;
  }, [cellOverrides, systems]);

  const denseLayout = measuresPerSystem < 4;
  const title = prettyTitle(header.title);
  const subtitle = lookupSubtitle(title);

  const beatErrors = useMemo(() => {
    const map: Record<string, boolean> = {};
    for (const voice of displayResult.voices) {
      const grid =
        localGrids[voice.name] ??
        notationToGrid(voice.notation, beatSchedule);
      Object.assign(
        map,
        errorsForVoice(voice.name, grid, beatDivSchedule, voice.model.triplets),
      );
    }
    return map;
  }, [displayResult.voices, localGrids, beatSchedule, beatDivSchedule]);

  const runExclusive = useCallback((fn: () => Promise<void>) => {
    const next = commitTailRef.current.then(fn, fn);
    commitTailRef.current = next.then(
      () => undefined,
      () => undefined,
    );
    return next;
  }, []);

  const publishParsed = useCallback(
    async (
      grids: Record<string, string[][]>,
      primaryVoice?: string,
    ): Promise<ScoreResult> => {
      const base = cloneScore(latestResultRef.current);
      setLocalGrids(grids);
      beatDraftsRef.current = {};
      cellOverridesRef.current = {};
      setCellOverrides({});
      localGridsRef.current = grids;

      for (const [name, grid] of Object.entries(grids)) {
        const voice = base.voices.find((v) => v.name === name);
        const divs =
          voice && voice.model.measures.length > 0
            ? beatDivScheduleForModel(voice.model, grid.length)
            : beatDivSchedule;
        if (gridHasBeatErrors(grid, divs, voice?.model.triplets)) {
          if (!primaryVoice || name === primaryVoice) {
            setError(
              "Certains temps sont incomplets ou trop longs (surlignés en rouge).",
            );
          }
          return latestResultRef.current;
        }
      }

      setBusy(true);
      setError(null);
      try {
        for (const voice of base.voices) {
          const grid = grids[voice.name];
          if (!grid) continue;
          const sched =
            voice.model.measures.length > 0
              ? beatScheduleForModel(voice.model, grid.length)
              : beatSchedule;
          const notation = rebuildVoiceNotation(
            grid,
            sched,
            meterPrefixesFromModel(voice.model, grid.length),
            voice.model.triplets,
          );
          const parsed = await parseSolfaNotation(
            notation,
            voice.model.tonic || base.header.tonic,
            voice.model.clef || "treble",
            beats,
            beatType,
            voice.model.triplets,
          );
          const vi = base.voices.findIndex((v) => v.name === voice.name);
          if (vi < 0) continue;
          // Préserver directives / time mid-score si le re-parse les perd
          const merged = {
            ...parsed.model,
            partName: voice.name,
            triplets: voice.model.triplets,
            enterMeasure: voice.model.enterMeasure,
          };
          for (
            let mi = 0;
            mi < Math.min(merged.measures.length, voice.model.measures.length);
            mi++
          ) {
            const prev = voice.model.measures[mi];
            const nextM = merged.measures[mi];
            if (!nextM.timeSignature && prev.timeSignature) {
              nextM.timeSignature = prev.timeSignature;
            }
            if (!nextM.keyTonic && prev.keyTonic) {
              nextM.keyTonic = prev.keyTonic;
              nextM.keyFifths = prev.keyFifths;
            }
            if ((!nextM.directions || nextM.directions.length === 0) && prev.directions?.length) {
              nextM.directions = prev.directions;
            }
          }
          base.voices[vi] = {
            name: voice.name,
            notation,
            model: merged,
          };
        }
        const regenerated = await regenerateFromModels(base, base.voices);
        // Grilles déjà alignées sur `grids` / notation rebuild — ne pas
        // reconstruire depuis to_solfa au prochain setResult.
        skipNextGridResetRef.current = true;
        localGridsRef.current = grids;
        setLocalGrids(grids);
        latestResultRef.current = regenerated;
        onChangeRef.current?.(regenerated);
        return regenerated;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return latestResultRef.current;
      } finally {
        setBusy(false);
      }
    },
    [beatSchedule, beatDivSchedule, beats, beatType],
  );

  const commitBeat = useCallback(
    (
      voiceName: string,
      measureAbs: number,
      beatIndex: number,
      value: string,
    ) => {
      const skipKey = beatKey(voiceName, measureAbs, beatIndex);
      if (skipBlurRef.current === skipKey) {
        skipBlurRef.current = null;
        return;
      }

      // O(1) — aucun setState sur le chemin navigation / édition simple :
      // SolfaBeatInput garde déjà `draft` localement ; les refs suffisent pour flush.
      const baseCell =
        localGridsRef.current[voiceName]?.[measureAbs]?.[beatIndex] ?? "";
      const prevValue = cellOverridesRef.current[skipKey] ?? baseCell;

      if (prevValue === value) {
        if (beatDraftsRef.current[skipKey] !== undefined) {
          const nextDrafts = { ...beatDraftsRef.current };
          delete nextDrafts[skipKey];
          beatDraftsRef.current = nextDrafts;
        }
        return;
      }

      const cellDiv =
        beatDivSchedule[Math.min(measureAbs, beatDivSchedule.length - 1)] ??
        beatDivSchedule[beatDivSchedule.length - 1] ??
        4;
      const voice = latestResultRef.current.voices.find((v) => v.name === voiceName);
      const tripletSpan = tripletSpanBeatsAt(
        voice?.model.triplets,
        measureAbs,
        beatIndex,
      );
      const fillCheck = tripletSpan
        ? analyzeTripletFill(value, tripletSpan, cellDiv)
        : analyzeBeatFill(value, cellDiv);
      // Triolet : jamais de cascade / auto-correction (même si « over »).
      const needsCascade = !tripletSpan && fillCheck.status === "over";

      if (!needsCascade) {
        // Persistance pour flush / rebuild sans re-render (curseur immédiat).
        beatDraftsRef.current = {
          ...beatDraftsRef.current,
          [skipKey]: value,
        };
        if (tripletSpan === 2) {
          const companionKey = beatKey(voiceName, measureAbs, beatIndex + 1);
          delete beatDraftsRef.current[companionKey];
          if (companionKey in cellOverridesRef.current) {
            const nextOverrides = { ...cellOverridesRef.current };
            delete nextOverrides[companionKey];
            cellOverridesRef.current = nextOverrides;
          }
          const voiceGrid = localGridsRef.current[voiceName];
          if (voiceGrid?.[measureAbs]) {
            const nextGrid = voiceGrid.map((row) => [...row]);
            nextGrid[measureAbs][beatIndex] = value;
            nextGrid[measureAbs][beatIndex + 1] = "";
            localGridsRef.current = {
              ...localGridsRef.current,
              [voiceName]: nextGrid,
            };
          }
        }
        if (value === baseCell) {
          if (skipKey in cellOverridesRef.current) {
            const next = { ...cellOverridesRef.current };
            delete next[skipKey];
            cellOverridesRef.current = next;
          }
        } else {
          cellOverridesRef.current = {
            ...cellOverridesRef.current,
            [skipKey]: value,
          };
        }
        return;
      }

      // Surplus rythmique : cascade (rare) — file exclusive, hors du chemin focus.
      void runExclusive(async () => {
        const base = latestResultRef.current;
        const voice = base.voices.find((v) => v.name === voiceName);
        if (!voice) return;

        const n = Math.max(
          voice.model.measures.length,
          (localGridsRef.current[voiceName] ?? []).length,
          measureAbs + 1,
        );
        const sched =
          voice.model.measures.length > 0
            ? beatScheduleForModel(voice.model, n)
            : beatSchedule;
        const divs =
          voice.model.measures.length > 0
            ? beatDivScheduleForModel(voice.model, n)
            : beatDivSchedule;

        let grid = padGrid(
          localGridsRef.current[voiceName] ??
            notationToGrid(voice.notation, sched),
          sched,
        );
        while (grid.length <= measureAbs) {
          grid.push(emptyMeasureRow(sched, grid.length));
        }
        grid = applyOverridesToGrid(voiceName, grid, sched);
        grid[measureAbs][beatIndex] = value;
        grid = normalizeGridCascade(grid, sched, divs, voice.model.triplets);

        const grids = { ...localGridsRef.current, [voiceName]: grid };
        for (const v of base.voices) {
          if (!grids[v.name]) {
            const vn = Math.max(v.model.measures.length, 1);
            const vs =
              v.model.measures.length > 0
                ? beatScheduleForModel(v.model, vn)
                : beatSchedule;
            grids[v.name] = notationToGrid(v.notation, vs);
          }
        }

        clearVoiceDrafts(voiceName);
        clearVoiceOverrides(voiceName);
        localGridsRef.current = grids;
        setLocalGrids(grids);
        setError(
          gridHasBeatErrors(grid, divs, voice.model.triplets)
            ? "Certains temps sont incomplets ou trop longs (surlignés en rouge)."
            : null,
        );
      });
    },
    [
      beatSchedule,
      beatDivSchedule,
      runExclusive,
      clearVoiceDrafts,
      clearVoiceOverrides,
      applyOverridesToGrid,
    ],
  );

  const flushCurrent = useCallback(async () => {
    skipBlurRef.current = null;
    await runExclusive(async () => {
          const drafts = {
            ...cellOverridesRef.current,
            ...beatDraftsRef.current,
          };
          const active = document.activeElement;
          if (
            active instanceof HTMLInputElement &&
            active.dataset.solfaBeat
          ) {
            drafts[active.dataset.solfaBeat] = active.value;
          }

          const base = latestResultRef.current;
          const grids: Record<string, string[][]> = {};
          for (const voice of base.voices) {
            const n = Math.max(
              voice.model.measures.length,
              (localGridsRef.current[voice.name] ?? []).length,
              1,
            );
            const sched =
              voice.model.measures.length > 0
                ? beatScheduleForModel(voice.model, n)
                : beatSchedule;
            grids[voice.name] = padGrid(
              localGridsRef.current[voice.name] ??
                notationToGrid(voice.notation, sched),
              sched,
            );
          }

          for (const [key, draft] of Object.entries(drafts)) {
            const [vn, miStr, biStr] = key.split("::");
            const mi = Number(miStr);
            const bi = Number(biStr);
            if (!grids[vn]) continue;
            const voice = base.voices.find((v) => v.name === vn);
            const sched =
              voice && voice.model.measures.length > 0
                ? beatScheduleForModel(
                    voice.model,
                    Math.max(grids[vn].length, mi + 1),
                  )
                : beatSchedule;
            while (grids[vn].length <= mi) {
              grids[vn].push(emptyMeasureRow(sched, grids[vn].length));
            }
            grids[vn][mi][bi] = draft;
          }

          for (const name of Object.keys(grids)) {
            const voice = base.voices.find((v) => v.name === name);
            const n = grids[name].length;
            const sched =
              voice && voice.model.measures.length > 0
                ? beatScheduleForModel(voice.model, n)
                : beatSchedule;
            const divs =
              voice && voice.model.measures.length > 0
                ? beatDivScheduleForModel(voice.model, n)
                : beatDivSchedule;
            grids[name] = normalizeGridCascade(
              grids[name],
              sched,
              divs,
              voice?.model.triplets,
            );
          }

          const afterKey = Object.entries(grids)
            .map(([name, grid]) => {
              const voice = base.voices.find((v) => v.name === name);
              const sched =
                voice && voice.model.measures.length > 0
                  ? beatScheduleForModel(voice.model, grid.length)
                  : beatSchedule;
              return `${name}\0${rebuildVoiceNotation(
                grid,
                sched,
                voice ? meterPrefixesFromModel(voice.model, grid.length) : undefined,
                voice?.model.triplets,
              )}`;
            })
            .sort()
            .join("\n");
          const baseKey = base.voices
            .map((v) => `${v.name}\0${v.notation}`)
            .sort()
            .join("\n");

          if (afterKey === baseKey && Object.keys(drafts).length === 0) {
            beatDraftsRef.current = {};
            cellOverridesRef.current = {};
            setCellOverrides({});
            return;
          }

          for (const [name, grid] of Object.entries(grids)) {
            const voice = base.voices.find((v) => v.name === name);
            const divs =
              voice && voice.model.measures.length > 0
                ? beatDivScheduleForModel(voice.model, grid.length)
                : beatDivSchedule;
            if (gridHasBeatErrors(grid, divs, voice?.model.triplets)) {
              setLocalGrids(grids);
              localGridsRef.current = grids;
              beatDraftsRef.current = {};
              cellOverridesRef.current = {};
              setCellOverrides({});
              setError(
                "Certains temps sont incomplets ou trop longs (surlignés en rouge).",
              );
              throw new Error(
                "Corrections incomplètes — terminez les temps en erreur avant d'enregistrer.",
              );
            }
          }

      await publishParsed(grids);
    });
    return latestResultRef.current;
  }, [beatSchedule, beatDivSchedule, runExclusive, publishParsed]);

  useImperativeHandle(
    ref,
    () => ({
      flush: flushCurrent,
      exportMarkdown: async () => {
        const next = await flushCurrent();
        return buildSolfaMarkdown(next, tempo, lyricsRef.current);
      },
    }),
    [flushCurrent, tempo],
  );

  const buildVoiceGrid = useCallback(
    (voiceName: string, measureAbs: number, beatIndex: number, currentValue?: string) => {
      const voice = displayResult.voices.find((v) => v.name === voiceName);
      if (!voice) return null;

      const n = Math.max(
        voice.model.measures.length,
        (localGrids[voiceName] ?? []).length,
        measureAbs + 1,
      );
      const sched =
        voice.model.measures.length > 0
          ? beatScheduleForModel(voice.model, n)
          : beatSchedule;

      let grid = padGrid(
        localGrids[voiceName] ?? notationToGrid(voice.notation, sched),
        sched,
      );
      while (grid.length <= measureAbs) {
        grid.push(emptyMeasureRow(sched, grid.length));
      }
      grid = applyOverridesToGrid(voiceName, grid, sched);
      if (currentValue !== undefined) {
        grid[measureAbs][beatIndex] = currentValue;
      }
      return grid;
    },
    [displayResult.voices, localGrids, beatSchedule, applyOverridesToGrid],
  );

  const applyLocalGrid = useCallback(
    (voiceName: string, grid: string[][]) => {
      clearVoiceDrafts(voiceName);
      clearVoiceOverrides(voiceName);
      setLocalGrids((prev) => ({ ...prev, [voiceName]: grid }));
    },
    [clearVoiceDrafts, clearVoiceOverrides],
  );

  const spaceShift = useCallback(
    (
      voiceName: string,
      measureAbs: number,
      beatIndex: number,
      value: string,
      caretIndex: number,
    ) => {
      const grid = buildVoiceGrid(voiceName, measureAbs, beatIndex);
      if (!grid) return;

      const voice = displayResult.voices.find((v) => v.name === voiceName);
      const triplets = voice?.model.triplets;
      const sched =
        voice && voice.model.measures.length > 0
          ? beatScheduleForModel(voice.model, grid.length)
          : beatSchedule;

      const shifted = shiftBeatTailToNext(
        grid,
        measureAbs,
        beatIndex,
        sched,
        value,
        caretIndex,
      );

      let nextMi = shifted.nextMeasure;
      let nextBi = shifted.nextBeat;
      if (isTripletPairContinuation(triplets, nextMi, nextBi)) {
        nextBi = beatIndexAfterTriplet(triplets, nextMi, nextBi - 1);
        const bpm = sched[nextMi] ?? sched[sched.length - 1] ?? 4;
        if (nextBi >= bpm) {
          nextMi++;
          nextBi = 0;
        }
      }

      skipBlurRef.current = beatKey(voiceName, measureAbs, beatIndex);
      pendingFocusRef.current = {
        voiceName,
        measureAbs: nextMi,
        beatIndex: nextBi,
      };

      if (!shifted.moved) {
        setLocalGrids((prev) => ({ ...prev }));
        return;
      }

      applyLocalGrid(voiceName, shifted.grid);
    },
    [buildVoiceGrid, beatSchedule, applyLocalGrid, displayResult.voices],
  );

  const backspacePull = useCallback(
    (voiceName: string, measureAbs: number, beatIndex: number) => {
      const grid = buildVoiceGrid(voiceName, measureAbs, beatIndex, "");
      if (!grid) return;

      const pulled = pullBeatsLeft(grid, measureAbs, beatIndex, beatSchedule);

      skipBlurRef.current = beatKey(voiceName, measureAbs, beatIndex);
      pendingFocusRef.current = {
        voiceName,
        measureAbs: pulled.focusMeasure,
        beatIndex: pulled.focusBeat,
      };

      if (!pulled.moved) {
        setLocalGrids((prev) => ({ ...prev }));
        return;
      }

      applyLocalGrid(voiceName, pulled.grid);
    },
    [buildVoiceGrid, beatSchedule, applyLocalGrid],
  );

  const deletePull = useCallback(
    (
      voiceName: string,
      measureAbs: number,
      beatIndex: number,
      value: string,
      caretIndex: number,
    ) => {
      const grid = buildVoiceGrid(voiceName, measureAbs, beatIndex, value);
      if (!grid) return;

      const pulled = deletePullNextNote(
        grid,
        measureAbs,
        beatIndex,
        beatSchedule,
        value,
        caretIndex,
      );

      skipBlurRef.current = beatKey(voiceName, measureAbs, beatIndex);
      pendingFocusRef.current = {
        voiceName,
        measureAbs: pulled.focusMeasure,
        beatIndex: pulled.focusBeat,
      };

      if (!pulled.moved) {
        setLocalGrids((prev) => ({ ...prev }));
        return;
      }

      applyLocalGrid(voiceName, pulled.grid);
    },
    [buildVoiceGrid, beatSchedule, applyLocalGrid],
  );

  const handleBeatCommit = useCallback(
    (vn: string, mi: number, bi: number, val: string) => {
      void commitBeat(vn, mi, bi, val);
    },
    [commitBeat],
  );

  const measureModel = useCallback(
    (measureAbs: number) => result.voices[0]?.model.measures[measureAbs],
    [result.voices],
  );

  const voiceMeasure = useCallback(
    (voiceName: string, measureAbs: number) =>
      result.voices.find((v) => v.name === voiceName)?.model.measures[measureAbs],
    [result.voices],
  );

  const voiceModelFor = useCallback(
    (voiceName: string) => result.voices.find((v) => v.name === voiceName)?.model,
    [result.voices],
  );

  const handleOpenDirective = useCallback((measureAbs: number, x: number, y: number) => {
    setDirectiveMenu({ measureAbs, x, y });
  }, []);

  const handleNavigateBeat = useCallback(
    (voiceName: string, measureAbs: number, beatIndex: number, dir: BeatNavDir) => {
      const base = latestResultRef.current;
      const voiceNames = base.voices.map((v) => v.name);
      const measureCount = Math.max(
        1,
        ...base.voices.map((v) =>
          Math.max(v.model.measures.length, (localGridsRef.current[v.name] ?? []).length),
        ),
        beatSchedule.length,
      );
      navigateBeatCell(
        voiceNames,
        (name) => base.voices.find((v) => v.name === name)?.model.triplets,
        (name) => {
          const voice = base.voices.find((v) => v.name === name);
          const n = Math.max(
            voice?.model.measures.length ?? 0,
            (localGridsRef.current[name] ?? []).length,
            measureCount,
          );
          return voice && voice.model.measures.length > 0
            ? beatScheduleForModel(voice.model, n)
            : beatSchedule;
        },
        measureCount,
        voiceName,
        measureAbs,
        beatIndex,
        dir,
      );
    },
    [beatSchedule],
  );

  const handleOpenAnnotation = useCallback(
    (
      voiceName: string,
      measureAbs: number,
      beatIndex: number,
      x: number,
      y: number,
    ) => {
      setAnnotationMenu({ voiceName, measureAbs, beatIndex, x, y });
    },
    [],
  );

  const beatScheduleForVoice = useCallback(
    (voiceName: string, measureAbs: number) => {
      const voice = latestResultRef.current.voices.find((v) => v.name === voiceName);
      const n = Math.max(voice?.model.measures.length ?? 0, measureAbs + 2);
      return voice && voice.model.measures.length > 0
        ? beatScheduleForModel(voice.model, n)
        : beatSchedule;
    },
    [beatSchedule],
  );

  /** Assemble la grille de chaque voix avec brouillons / overrides / input actif. */
  const collectPendingGrids = useCallback((): Record<string, string[][]> => {
    const drafts: Record<string, string> = {
      ...cellOverridesRef.current,
      ...beatDraftsRef.current,
    };
    const active = document.activeElement;
    if (active instanceof HTMLInputElement && active.dataset.solfaBeat) {
      drafts[active.dataset.solfaBeat] = active.value;
    }

    const base = latestResultRef.current;
    const grids: Record<string, string[][]> = {};
    for (const voice of base.voices) {
      const n = Math.max(
        voice.model.measures.length,
        (localGridsRef.current[voice.name] ?? []).length,
        1,
      );
      const sched =
        voice.model.measures.length > 0
          ? beatScheduleForModel(voice.model, n)
          : beatSchedule;
      grids[voice.name] = padGrid(
        localGridsRef.current[voice.name] ??
          notationToGrid(voice.notation, sched),
        sched,
      );
    }

    for (const [key, draft] of Object.entries(drafts)) {
      const [vn, miStr, biStr] = key.split("::");
      const mi = Number(miStr);
      const bi = Number(biStr);
      if (!grids[vn] || !Number.isFinite(mi) || !Number.isFinite(bi)) continue;
      const voice = base.voices.find((v) => v.name === vn);
      const sched =
        voice && voice.model.measures.length > 0
          ? beatScheduleForModel(voice.model, Math.max(grids[vn].length, mi + 1))
          : beatSchedule;
      while (grids[vn].length <= mi) {
        grids[vn].push(emptyMeasureRow(sched, grids[vn].length));
      }
      grids[vn][mi][bi] = draft;
    }
    return grids;
  }, [beatSchedule]);

  /**
   * Persiste les éditions locales (brouillons / overrides) dans le score,
   * applique une mutation (triolet, nuance…), puis notifie le parent
   * sans reconstruire la grille depuis l'ancienne notation.
   */
  const persistPendingAndMutateScore = useCallback(
    (
      mutate: (score: ScoreResult) => ScoreResult,
      patchGrids?: (
        grids: Record<string, string[][]>,
        score: ScoreResult,
      ) => Record<string, string[][]>,
    ): Promise<void> => {
      if (!onChange) return Promise.resolve();
      return runExclusive(async () => {
        setBusy(true);
        setError(null);
        try {
          let grids = collectPendingGrids();
          let score = mutate(cloneScore(latestResultRef.current));
          if (patchGrids) {
            grids = patchGrids(grids, score);
          }

          // Réécrire les notations depuis la grille (éditions non sauvées incluses).
          for (let vi = 0; vi < score.voices.length; vi++) {
            const voice = score.voices[vi];
            const grid = grids[voice.name];
            if (!grid) continue;
            const sched =
              voice.model.measures.length > 0
                ? beatScheduleForModel(voice.model, grid.length)
                : beatSchedule;
            const notation = rebuildVoiceNotation(
              grid,
              sched,
              meterPrefixesFromModel(voice.model, grid.length),
              voice.model.triplets,
            );
            try {
              const parsed = await parseSolfaNotation(
                notation,
                voice.model.tonic || score.header.tonic,
                voice.model.clef || "treble",
                beats,
                beatType,
                voice.model.triplets,
              );
              const merged = {
                ...parsed.model,
                partName: voice.name,
                triplets: voice.model.triplets,
                enterMeasure: voice.model.enterMeasure,
              };
              for (
                let mi = 0;
                mi < Math.min(merged.measures.length, voice.model.measures.length);
                mi++
              ) {
                const prev = voice.model.measures[mi];
                const nextM = merged.measures[mi];
                if (!nextM.timeSignature && prev.timeSignature) {
                  nextM.timeSignature = prev.timeSignature;
                }
                if (!nextM.keyTonic && prev.keyTonic) {
                  nextM.keyTonic = prev.keyTonic;
                  nextM.keyFifths = prev.keyFifths;
                }
                if (
                  (!nextM.directions || nextM.directions.length === 0) &&
                  prev.directions?.length
                ) {
                  nextM.directions = prev.directions;
                }
              }
              score.voices[vi] = { name: voice.name, notation, model: merged };
            } catch {
              // Parse impossible (ex. triolet `drm` non supporté côté omr) :
              // on garde le modèle existant + la notation éditée + les triolets.
              score.voices[vi] = {
                ...voice,
                notation,
                model: { ...voice.model, triplets: voice.model.triplets },
              };
            }
          }

          const regenerated = await regenerateFromModels(score, score.voices);
          const next: ScoreResult = {
            ...regenerated,
            voices: regenerated.voices.map((v, i) => ({
              ...v,
              notation: score.voices[i]?.notation ?? v.notation,
              model: {
                ...v.model,
                triplets: score.voices[i]?.model.triplets ?? v.model.triplets,
              },
            })),
          };

          localGridsRef.current = grids;
          setLocalGrids(grids);
          beatDraftsRef.current = {};
          cellOverridesRef.current = {};
          setCellOverrides({});
          latestResultRef.current = next;
          skipNextGridResetRef.current = true;
          onChange(next);

          const anyError = score.voices.some((voice) => {
            const grid = grids[voice.name];
            if (!grid) return false;
            const divs =
              voice.model.measures.length > 0
                ? beatDivScheduleForModel(voice.model, grid.length)
                : beatDivSchedule;
            return gridHasBeatErrors(grid, divs, voice.model.triplets);
          });
          setError(
            anyError
              ? "Certains temps sont incomplets ou trop longs (surlignés en rouge)."
              : null,
          );
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
        } finally {
          setBusy(false);
        }
      });
    },
    [
      onChange,
      runExclusive,
      collectPendingGrids,
      beatSchedule,
      beatDivSchedule,
      beats,
      beatType,
    ],
  );

  const handleTripletPlusClick = useCallback(
    (
      voiceName: string,
      measureAbs: number,
      beatIndex: number,
      x: number,
      y: number,
    ) => {
      if (!onChange) return;
      const voice = latestResultRef.current.voices.find((v) => v.name === voiceName);
      const sched = beatScheduleForVoice(voiceName, measureAbs);
      const action = tripletPlusAction(
        voice?.model.triplets,
        measureAbs,
        beatIndex,
        sched,
      );
      if (action === "remove") {
        persistPendingAndMutateScore((score) =>
          removeTripletAt(score, voiceName, measureAbs, beatIndex),
        );
        return;
      }
      if (action === "apply-one") {
        persistPendingAndMutateScore(
          (score) => applyTriplet(score, voiceName, measureAbs, beatIndex, 1, sched),
          (grids) => ({
            ...grids,
            [voiceName]: applyTripletToGrid(
              grids[voiceName] ?? [],
              measureAbs,
              beatIndex,
              1,
            ),
          }),
        );
        return;
      }
      setTripletMenu({ voiceName, measureAbs, beatIndex, x, y });
    },
    [onChange, beatScheduleForVoice, persistPendingAndMutateScore],
  );

  const applyTripletChoice = useCallback(
    (spanBeats: 1 | 2) => {
      if (!tripletMenu) return;
      const { voiceName, measureAbs, beatIndex } = tripletMenu;
      setTripletMenu(null);
      const sched = beatScheduleForVoice(voiceName, measureAbs);
      persistPendingAndMutateScore(
        (score) =>
          applyTriplet(score, voiceName, measureAbs, beatIndex, spanBeats, sched),
        (grids) => ({
          ...grids,
          [voiceName]: applyTripletToGrid(
            grids[voiceName] ?? [],
            measureAbs,
            beatIndex,
            spanBeats,
          ),
        }),
      );
    },
    [tripletMenu, beatScheduleForVoice, persistPendingAndMutateScore],
  );

  const applyDirectiveAndRegen = useCallback(
    (measureAbs: number, payload: DirectivePayload) => {
      if (!onChange) return;
      setDirectiveMenu(null);

      // Changement de tonalité : transpose les hauteurs (syllabes inchangées)
      // puis régénère le MusicXML — sans re-parse qui écraserait le modèle.
      if (payload.id === "key") {
        void runExclusive(async () => {
          setBusy(true);
          setError(null);
          try {
            const grids = collectPendingGrids();
            let score = cloneScore(latestResultRef.current);

            // Intégrer les éditions locales dans la notation avant transposition
            for (let vi = 0; vi < score.voices.length; vi++) {
              const voice = score.voices[vi];
              const grid = grids[voice.name];
              if (!grid) continue;
              const sched =
                voice.model.measures.length > 0
                  ? beatScheduleForModel(voice.model, grid.length)
                  : beatSchedule;
              score.voices[vi] = {
                ...voice,
                notation: rebuildVoiceNotation(
                  grid,
                  sched,
                  meterPrefixesFromModel(voice.model, grid.length),
                  voice.model.triplets,
                ),
              };
            }

            const { score: mutated, meterWarnings } = applyDirective(
              score,
              measureAbs,
              payload,
            );

            // Réémettre `(Doh=X)` dans la notation (syllabes inchangées).
            for (let vi = 0; vi < mutated.voices.length; vi++) {
              const voice = mutated.voices[vi];
              const grid = grids[voice.name];
              if (!grid) continue;
              const sched =
                voice.model.measures.length > 0
                  ? beatScheduleForModel(voice.model, grid.length)
                  : beatSchedule;
              mutated.voices[vi] = {
                ...voice,
                notation: rebuildVoiceNotation(
                  grid,
                  sched,
                  meterPrefixesFromModel(voice.model, grid.length),
                  voice.model.triplets,
                ),
              };
            }

            const regenerated = await regenerateFromModels(
              mutated,
              mutated.voices,
            );
            const next: ScoreResult = {
              ...regenerated,
              voices: regenerated.voices.map((v, i) => ({
                ...v,
                // Notation + modèle (pitches, keyTonic) issus de applyDirective
                notation: mutated.voices[i]?.notation ?? v.notation,
                model: mutated.voices[i]?.model ?? v.model,
              })),
            };

            const nextGrids: Record<string, string[][]> = {};
            for (const voice of next.voices) {
              const n = Math.max(voice.model.measures.length, 1);
              const sched =
                voice.model.measures.length > 0
                  ? beatScheduleForModel(voice.model, n)
                  : beatSchedule;
              nextGrids[voice.name] = notationToGrid(voice.notation, sched);
            }

            localGridsRef.current = nextGrids;
            setLocalGrids(nextGrids);
            beatDraftsRef.current = {};
            cellOverridesRef.current = {};
            setCellOverrides({});
            latestResultRef.current = next;
            skipNextGridResetRef.current = true;
            onChange(next);
            if (meterWarnings.length) {
              setError(meterWarnings.slice(0, 3).join(" · "));
            }
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        });
        return;
      }

      let warnings: string[] = [];
      void persistPendingAndMutateScore((score) => {
        const { score: mutated, meterWarnings } = applyDirective(
          score,
          measureAbs,
          payload,
        );
        warnings = meterWarnings;
        return mutated;
      }).then(() => {
        if (warnings.length) {
          setError(warnings.slice(0, 3).join(" · "));
        }
      });
    },
    [
      onChange,
      persistPendingAndMutateScore,
      runExclusive,
      collectPendingGrids,
      beatSchedule,
    ],
  );

  const removeChipAndRegen = useCallback(
    (measureAbs: number, chip: DirectiveChip) => {
      if (!onChange) return;
      persistPendingAndMutateScore((score) =>
        removeDirectiveChip(score, measureAbs, chip),
      );
    },
    [onChange, persistPendingAndMutateScore],
  );

  const handleOpenAddVoice = useCallback(
    (measureAbs: number, x: number, y: number) => {
      setAddVoiceMenu({ measureAbs, x, y });
    },
    [],
  );

  /** Divisi : la voix choisie devient V1 et une V2 silencieuse entre à la mesure. */
  const addVoiceAndRegen = useCallback(
    (measureAbs: number, targetVoiceName: string) => {
      if (!onChange) return;
      setAddVoiceMenu(null);
      persistPendingAndMutateScore(
        (score) => splitVoiceForDivisi(score, targetVoiceName, measureAbs).score,
      );
    },
    [onChange, persistPendingAndMutateScore],
  );

  const applyAnnotationAndRegen = useCallback(
    (payload: BeatAnnotationPayload) => {
      if (!onChange || !annotationMenu) return;
      const { voiceName, measureAbs, beatIndex } = annotationMenu;
      setAnnotationMenu(null);
      persistPendingAndMutateScore((score) =>
        applyBeatAnnotation(score, voiceName, measureAbs, beatIndex, payload),
      );
    },
    [onChange, annotationMenu, persistPendingAndMutateScore],
  );

  const removeAnnotationAndRegen = useCallback(
    (voiceName: string, measureAbs: number, chip: BeatAnnotationChip) => {
      if (!onChange) return;
      persistPendingAndMutateScore((score) =>
        removeBeatAnnotationChip(score, voiceName, measureAbs, chip),
      );
    },
    [onChange, persistPendingAndMutateScore],
  );

  const handleRemoveAnnotationChip = useCallback(
    (voiceName: string, measureAbs: number, chip: BeatAnnotationChip) => {
      void removeAnnotationAndRegen(voiceName, measureAbs, chip);
    },
    [removeAnnotationAndRegen],
  );

  const handleRemoveChip = useCallback(
    (measureAbs: number, chip: DirectiveChip) => {
      void removeChipAndRegen(measureAbs, chip);
    },
    [removeChipAndRegen],
  );

  const primaryModel = result.voices[0]?.model;
  const primaryVoiceName = result.voices[0]?.name ?? "Soprano";

  return (
    <article
      className={`solfa-score ${solfaMono.className}${denseLayout ? " solfa-score--dense-measure" : ""}`}
    >
      <header className="solfa-score__header">
        <p className="solfa-score__meta-left">
          Do dia {header.tonic}
          {header.mode === "minor" ? " (mineur)" : ""}, {beats}/{beatType}
        </p>
        <div className={`solfa-score__titles ${solfaSerif.className}`}>
          <h2 className="solfa-score__title">{title}</h2>
          {header.composer && (
            <p className="solfa-score__subtitle">{header.composer}</p>
          )}
          {header.work && (
            <p className="solfa-score__subtitle text-stone-500">{header.work}</p>
          )}
          {subtitle && !header.composer && (
            <p className="solfa-score__subtitle">({subtitle})</p>
          )}
        </div>
        <div className="solfa-score__meta-right">
          <TempoControl value={tempo} onChange={onTempoChange} />
        </div>
      </header>

      {(busy || error) && (
        <div className="mb-3 px-1 text-xs">
          {busy && <span className="text-stone-500">Mise à jour…</span>}
          {error && <span className="text-red-700">{error}</span>}
        </div>
      )}

      <div className="solfa-score__body">
        {systems.map((system) => (
          <SolfaSystemBlock
            key={system.startNumber}
            system={system}
            lyrics={lyrics}
            onLyricChange={handleLyricChange}
            onBeatDraft={handleBeatDraft}
            onBeatCommit={handleBeatCommit}
            onSpaceShift={spaceShift}
            onBackspacePull={backspacePull}
            onDeletePull={deletePull}
            beatErrors={beatErrors}
            beatDivSchedule={beatDivSchedule}
            cellOverrides={
              overridesBySystem.get(system.startNumber) ?? EMPTY_OVERRIDES
            }
            busy={busy}
            measureModel={measureModel}
            onOpenDirective={handleOpenDirective}
            onRemoveChip={handleRemoveChip}
            onNavigate={handleNavigateBeat}
            onOpenAnnotation={handleOpenAnnotation}
            onRemoveAnnotationChip={handleRemoveAnnotationChip}
            voiceMeasure={voiceMeasure}
            voiceModel={voiceModelFor}
            primaryVoiceName={primaryVoiceName}
            beatSchedule={beatSchedule}
            onTripletPlusClick={handleTripletPlusClick}
            onAddVoice={handleOpenAddVoice}
          />
        ))}
      </div>

      {addVoiceMenu && (
        <AddVoiceMenu
          x={addVoiceMenu.x}
          y={addVoiceMenu.y}
          voices={result.voices.map((v) => ({
            name: v.name,
            label: `${voiceAbbr(v.name)} · ${v.name}`,
          }))}
          onSelect={(voiceName) =>
            addVoiceAndRegen(addVoiceMenu.measureAbs, voiceName)
          }
          onClose={() => setAddVoiceMenu(null)}
        />
      )}

      {annotationMenu && (
        <BeatAnnotationMenu
          x={annotationMenu.x}
          y={annotationMenu.y}
          voiceName={annotationMenu.voiceName}
          measureNumber={annotationMenu.measureAbs + 1}
          beatNumber={annotationMenu.beatIndex + 1}
          onClose={() => setAnnotationMenu(null)}
          onSelect={(payload) => void applyAnnotationAndRegen(payload)}
        />
      )}

      {tripletMenu && (
        <TripletChoiceMenu
          x={tripletMenu.x}
          y={tripletMenu.y}
          voiceName={tripletMenu.voiceName}
          measureNumber={tripletMenu.measureAbs + 1}
          beatNumber={tripletMenu.beatIndex + 1}
          onClose={() => setTripletMenu(null)}
          onSelect={applyTripletChoice}
        />
      )}

      {directiveMenu && primaryModel && (
        <MeasureDirectiveMenu
          x={directiveMenu.x}
          y={directiveMenu.y}
          defaultBpm={
            Number(
              primaryModel.measures[directiveMenu.measureAbs]?.directions?.find(
                (d) => d.kind === "metronome",
              )?.value,
            ) ||
            primaryModel.tempo ||
            tempo.bpm ||
            120
          }
          defaultBeats={
            effectiveTimeSignature(primaryModel, directiveMenu.measureAbs).beats
          }
          defaultBeatType={
            effectiveTimeSignature(primaryModel, directiveMenu.measureAbs)
              .beatType
          }
          defaultTonic={effectiveTonic(primaryModel, directiveMenu.measureAbs)}
          onClose={() => setDirectiveMenu(null)}
          onSelect={(payload) =>
            void applyDirectiveAndRegen(directiveMenu.measureAbs, payload)
          }
        />
      )}
    </article>
  );
});
