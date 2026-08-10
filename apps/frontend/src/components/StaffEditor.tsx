"use client";

import { useCallback, useMemo, useState } from "react";
import type { ScoreResult, Voice } from "@/lib/types";
import {
  SOLFEGE_OPTIONS,
  maxLedgerNeeded,
  pitchToStaffPos,
  staffPosToPitch,
  type SolfegeOptionId,
  type StaffClef,
} from "@/lib/staffPitch";
import { pitchForSyllableNear } from "@/lib/movableDo";
import {
  applyNoteDuration,
  applyNotePitch,
  cloneScore,
  makeNote,
  regenerateFromModels,
} from "@/lib/scoreEdit";
import { NotePicker, type NotePickerChoice } from "@/components/NotePicker";
import { MeasureDirectiveMenu } from "@/components/MeasureDirectiveMenu";
import {
  applyDirective,
  chipsForMeasure,
  effectiveTimeSignature,
  effectiveTonic,
  removeDirectiveChip,
  solfaPulseCount,
  type DirectiveChip,
  type DirectivePayload,
} from "@/lib/measureDirectives";
import {
  noteColumnWidth,
  resolveNoteValue,
  StaffNoteGlyph,
  StaffRestGlyph,
} from "@/lib/staffGlyphs";

const LINE_GAP = 10;
const STAFF_TOP = 44;
const MEASURE_PAD = 28;
const NOTE_COL_W = 28;
const STAFF_LEFT = 48;

/**
 * Largeur de chaque mesure = MAX du besoin sur TOUTES les voix (colonnes
 * alignées verticalement d'une portée à l'autre), et positions x partagées.
 * → un seul système : toutes les portées utilisent la même grille horizontale.
 */
function sharedMeasureLayout(voices: Voice[]): {
  widths: number[];
  starts: number[];
  totalW: number;
} {
  const n = Math.max(0, ...voices.map((v) => v.model.measures.length));
  const widths: number[] = [];
  for (let mi = 0; mi < n; mi++) {
    let w = MEASURE_PAD * 2;
    for (const v of voices) {
      const m = v.model.measures[mi];
      if (!m) continue;
      const div = v.model.divisions || 1;
      const notesW = m.notes.reduce(
        (s, note) =>
          s + noteColumnWidth(resolveNoteValue(note.type, note.duration, div, note.dots).type),
        0,
      );
      w = Math.max(w, notesW + NOTE_COL_W + MEASURE_PAD);
    }
    widths.push(w);
  }
  const starts: number[] = [];
  let x = STAFF_LEFT;
  for (const w of widths) {
    starts.push(x);
    x += w;
  }
  const totalW = STAFF_LEFT + widths.reduce((a, b) => a + b, 0) + 24;
  return { widths, starts, totalW };
}

/** Une voix d'accompagnement (piano/orgue) — pour l'espace avant l'accompagnement. */
function isAccompaniment(name: string): boolean {
  return /piano|orgue|organ|keyboard|accomp/i.test(name);
}

type PickerTarget =
  | { kind: "note"; voiceIndex: number; measureIndex: number; noteIndex: number }
  | {
      kind: "slot";
      voiceIndex: number;
      measureIndex: number;
      staffPos: number;
      insertAt: number;
    };

function optionToPitch(
  id: SolfegeOptionId,
  staffPos: number,
  clef: StaffClef,
  tonic: string,
  dohOctave: number,
): {
  isRest: boolean;
  pitch: ReturnType<typeof pitchForSyllableNear> | null;
} {
  const opt = SOLFEGE_OPTIONS.find((o) => o.id === id);
  if (!opt || opt.kind === "rest") return { isRest: true, pitch: null };
  const near = staffPosToPitch(staffPos, clef);
  const pitch = pitchForSyllableNear(opt.syllable, near, tonic, dohOctave);
  return { isRest: false, pitch };
}

function VoiceStaff({
  voice,
  voiceIndex,
  ledgerAbove,
  ledgerBelow,
  onAddLedger,
  onOpenPicker,
  onOpenDirective,
  onRemoveChip,
  onShiftOctave,
  showDirectives,
  busy,
  measureWidths,
  measureStarts,
  totalW,
}: {
  voice: Voice;
  voiceIndex: number;
  ledgerAbove: number;
  ledgerBelow: number;
  onAddLedger: (dir: "above" | "below") => void;
  onOpenPicker: (target: PickerTarget, clientX: number, clientY: number) => void;
  onOpenDirective: (measureIndex: number, clientX: number, clientY: number) => void;
  onRemoveChip: (measureIndex: number, chip: DirectiveChip) => void;
  onShiftOctave: (delta: number) => void;
  showDirectives: boolean;
  busy: boolean;
  /** Grille horizontale PARTAGÉE par toutes les voix (alignement + scroll unique). */
  measureWidths: number[];
  measureStarts: number[];
  totalW: number;
}) {
  const clef = (voice.model.clef === "bass" ? "bass" : "treble") as StaffClef;
  const measures = voice.model.measures;
  const divisions = voice.model.divisions || 1;
  const topPos = 8 + ledgerAbove * 2;
  const bottomPos = 0 - ledgerBelow * 2;
  const yOf = (pos: number) => STAFF_TOP + (topPos - pos) * (LINE_GAP / 2);
  const staffBottomY = yOf(bottomPos);
  const staffTopY = yOf(topPos);
  const totalH = staffBottomY + 30;

  // UNIQUEMENT les 5 lignes de la portée (pos 0..8). Les notes hors portée
  // reçoivent des lignes supplémentaires COURTES (au niveau de la tête, cf. plus
  // bas). Dessiner des lignes pleine largeur au-dessus/en-dessous faisait une
  // portée à 7-8 lignes ambiguë → on lisait les notes une octave trop haut.
  const linePositions = [0, 2, 4, 6, 8];

  return (
    <>
      {/* Étiquette de voix : collée à gauche (reste visible pendant le scroll). */}
      <div className="staff-label sticky left-0 z-30 flex w-fit items-center gap-1 bg-[#fffcf5] pr-3 text-[11px] font-semibold text-stone-600">
        <span>
          {voice.name}{" "}
          <span className="font-normal text-stone-400">
            ({clef === "bass" ? "clé de fa" : "clé de sol"})
          </span>
        </span>
        {/* Décaler toute la voix d'une octave (corrige une erreur d'octave OMR). */}
        <span className="ml-1 inline-flex overflow-hidden rounded border border-stone-300">
          <button
            type="button"
            className="px-1 leading-none text-stone-500 hover:bg-stone-100 disabled:opacity-40"
            title="Descendre toute la voix d'une octave"
            disabled={busy}
            onClick={() => onShiftOctave(-1)}
          >
            8↓
          </button>
          <button
            type="button"
            className="border-l border-stone-300 px-1 leading-none text-stone-500 hover:bg-stone-100 disabled:opacity-40"
            title="Monter toute la voix d'une octave"
            disabled={busy}
            onClick={() => onShiftOctave(1)}
          >
            8↑
          </button>
        </span>
      </div>
      <div className="staff-stage relative" style={{ width: totalW, height: totalH }}>
        {showDirectives &&
          measures.map((measure, mi) => {
            const mx = measureStarts[mi];
            const chips = chipsForMeasure(measure);
            return (
              <div
                key={`dir-${mi}`}
                className="pointer-events-none absolute z-20 flex items-center gap-1"
                style={{ left: mx - 2, top: 4, maxWidth: measureWidths[mi] - 4 }}
              >
                <button
                  type="button"
                  className="pointer-events-auto flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-stone-400 bg-white text-xs font-bold text-stone-600 opacity-70 shadow-sm hover:opacity-100"
                  title="Directive en tête de mesure (D.C., tempo, métrique, Doh…)"
                  disabled={busy}
                  aria-label={`Ajouter une directive mesure ${mi + 1}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    const r = (e.target as HTMLElement).getBoundingClientRect();
                    onOpenDirective(mi, r.left, r.bottom + 4);
                  }}
                >
                  +
                </button>
                <div className="pointer-events-auto flex min-w-0 flex-wrap gap-1">
                  {chips.map((chip) => (
                    <span
                      key={chip.key}
                      className="inline-flex items-center gap-0.5 rounded border border-stone-300 bg-white/95 px-1 py-0.5 text-[10px] font-semibold text-stone-700"
                    >
                      {chip.label}
                      <button
                        type="button"
                        className="text-stone-400 hover:text-red-700"
                        disabled={busy}
                        aria-label={`Retirer ${chip.label}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onRemoveChip(mi, chip);
                        }}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            );
          })}

        <svg
          width={totalW}
          height={totalH}
          viewBox={`0 0 ${totalW} ${totalH}`}
          className="absolute inset-0 block select-none"
        >
          <text x={10} y={yOf(4) + 5} className="fill-stone-700" fontSize="20">
            {clef === "bass" ? "𝄢" : "𝄞"}
          </text>

          {measures.map((measure, mi) => {
            const mx = measureStarts[mi];
            const mw = measureWidths[mi];
            const noteCount = measure.notes.length;
            const ts = effectiveTimeSignature(voice.model, mi);
            const prevTs = mi > 0 ? effectiveTimeSignature(voice.model, mi - 1) : null;
            const meterChanged =
              !!prevTs && (ts.beats !== prevTs.beats || ts.beatType !== prevTs.beatType);

            return (
              <g key={mi}>
                {Array.from({ length: topPos - bottomPos + 1 }, (_, i) => {
                  const pos = topPos - i;
                  const y = yOf(pos);
                  return (
                    <rect
                      key={`slot-${mi}-${pos}`}
                      x={mx}
                      y={y - LINE_GAP / 4}
                      width={mw}
                      height={LINE_GAP / 2}
                      className="fill-transparent hover:fill-amber-200/35 cursor-pointer"
                      onClick={(e) => {
                        e.stopPropagation();
                        const svgRect = (e.target as SVGRectElement).ownerSVGElement!.getBoundingClientRect();
                        const localX = e.clientX - svgRect.left - mx;
                        let acc = MEASURE_PAD / 2;
                        let col = noteCount;
                        for (let j = 0; j < noteCount; j++) {
                          const w = noteColumnWidth(measure.notes[j].type);
                          if (localX < acc + w) {
                            col = j;
                            break;
                          }
                          acc += w;
                        }
                        if (localX >= acc) col = noteCount;
                        onOpenPicker(
                          {
                            kind: "slot",
                            voiceIndex,
                            measureIndex: mi,
                            staffPos: pos,
                            insertAt: col,
                          },
                          e.clientX,
                          e.clientY,
                        );
                      }}
                    />
                  );
                })}

                {linePositions.map((pos) => {
                  const isMain = pos >= 0 && pos <= 8;
                  return (
                    <line
                      key={`line-${mi}-${pos}`}
                      x1={mx}
                      x2={mx + mw}
                      y1={yOf(pos)}
                      y2={yOf(pos)}
                      stroke={isMain ? "#444" : "#999"}
                      strokeWidth={isMain ? 1 : 0.75}
                      pointerEvents="none"
                    />
                  );
                })}

                <line
                  x1={mx + mw}
                  x2={mx + mw}
                  y1={yOf(8)}
                  y2={yOf(0)}
                  stroke="#333"
                  strokeWidth={1.2}
                  pointerEvents="none"
                />

                {/* Barre initiale (départ du système) */}
                {mi === 0 && (
                  <line
                    x1={mx}
                    x2={mx}
                    y1={yOf(8)}
                    y2={yOf(0)}
                    stroke="#333"
                    strokeWidth={1.2}
                    pointerEvents="none"
                  />
                )}

                {/* Double barre avant un changement de métrique */}
                {meterChanged && (
                  <g pointerEvents="none">
                    <line x1={mx - 6} x2={mx - 6} y1={yOf(8)} y2={yOf(0)} stroke="#333" strokeWidth={1} />
                    <line x1={mx - 2.5} x2={mx - 2.5} y1={yOf(8)} y2={yOf(0)} stroke="#333" strokeWidth={1.4} />
                  </g>
                )}

                {/* Signature rythmique : au début et à chaque changement */}
                {(mi === 0 || meterChanged) && (
                  <g pointerEvents="none" className="fill-stone-700">
                    <text x={mx + 5} y={yOf(6) + 5} fontSize="13" fontWeight={700} textAnchor="middle">
                      {ts.beats}
                    </text>
                    <text x={mx + 5} y={yOf(2) + 5} fontSize="13" fontWeight={700} textAnchor="middle">
                      {ts.beatType}
                    </text>
                  </g>
                )}

                {/* Numéro de mesure (voix du haut uniquement) */}
                {voiceIndex === 0 && (
                  <text
                    x={mx + 2}
                    y={yOf(8) - 5}
                    fontSize="9"
                    className="fill-stone-400"
                    pointerEvents="none"
                  >
                    {mi + 1}
                  </text>
                )}

                {measure.notes.map((note, ni) => {
                  const value = resolveNoteValue(
                    note.type,
                    note.duration,
                    divisions,
                    note.dots,
                  );
                  let nx = mx + MEASURE_PAD / 2 + 10;
                  for (let j = 0; j < ni; j++) {
                    const prev = resolveNoteValue(
                      measure.notes[j].type,
                      measure.notes[j].duration,
                      divisions,
                      measure.notes[j].dots,
                    );
                    nx += noteColumnWidth(prev.type);
                  }
                  nx += noteColumnWidth(value.type) / 2 - 10;

                  if (note.isRest) {
                    return (
                      <g
                        key={ni}
                        className="cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpenPicker(
                            { kind: "note", voiceIndex, measureIndex: mi, noteIndex: ni },
                            e.clientX,
                            e.clientY,
                          );
                        }}
                      >
                        <StaffRestGlyph
                          nx={nx}
                          cy={yOf(4)}
                          type={value.type}
                          dots={value.dots}
                        />
                      </g>
                    );
                  }
                  const pitch = note.pitch!;
                  const pos = pitchToStaffPos(pitch, clef);
                  const cy = yOf(pos);
                  const stemUp = pos < 4;
                  const ledgers: number[] = [];
                  if (pos > 8) {
                    for (let p = 10; p <= pos; p += 2) ledgers.push(p);
                  }
                  if (pos < 0) {
                    for (let p = -2; p >= pos; p -= 2) ledgers.push(p);
                  }
                  return (
                    <g
                      key={ni}
                      className="cursor-pointer"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenPicker(
                          { kind: "note", voiceIndex, measureIndex: mi, noteIndex: ni },
                          e.clientX,
                          e.clientY,
                        );
                      }}
                    >
                      {ledgers.map((lp) => (
                        <line
                          key={lp}
                          x1={nx - 8}
                          x2={nx + 8}
                          y1={yOf(lp)}
                          y2={yOf(lp)}
                          stroke="#444"
                          strokeWidth={1}
                        />
                      ))}
                      <StaffNoteGlyph
                        nx={nx}
                        cy={cy}
                        type={value.type}
                        dots={value.dots}
                        stemUp={stemUp}
                      />
                    </g>
                  );
                })}
              </g>
            );
          })}
        </svg>

        {/* + lignes supplémentaires : au survol de chaque mesure */}
        {measures.map((_, mi) => {
          const mx = measureStarts[mi];
          const mw = measureWidths[mi];
          const mts = effectiveTimeSignature(voice.model, mi);
          const pulses = Math.max(1, solfaPulseCount(mts.beats, mts.beatType));
          return (
            <div
              key={`plus-${mi}`}
              className="staff-measure-cell group/measure pointer-events-none absolute"
              data-pm={mi}
              data-pulses={pulses}
              style={{ left: mx, width: mw, top: 0, height: totalH }}
            >
              {/* Bande de surlignage du TEMPS joué (positionnée par le
                  surligneur impératif : left/width/display). Vertical fixe. */}
              <span
                className="staff-playhead"
                style={{ top: staffTopY, height: staffBottomY - staffTopY }}
              />
              <button
                type="button"
                className="pointer-events-auto absolute left-1/2 z-10 flex h-5 w-5 -translate-x-1/2 items-center justify-center rounded-full border border-stone-400 bg-white text-xs font-bold text-stone-700 opacity-0 shadow transition group-hover/measure:opacity-100"
                style={{ top: Math.max(2, staffTopY - 22) }}
                title="Ajouter une ligne supplémentaire au-dessus"
                onClick={() => onAddLedger("above")}
              >
                +
              </button>
              <button
                type="button"
                className="pointer-events-auto absolute left-1/2 z-10 flex h-5 w-5 -translate-x-1/2 items-center justify-center rounded-full border border-stone-400 bg-white text-xs font-bold text-stone-700 opacity-0 shadow transition group-hover/measure:opacity-100"
                style={{ top: staffBottomY + 8 }}
                title="Ajouter une ligne supplémentaire en-dessous"
                onClick={() => onAddLedger("below")}
              >
                +
              </button>
            </div>
          );
        })}
      </div>
    </>
  );
}

export function StaffEditor({
  result,
  onChange,
}: {
  result: ScoreResult;
  onChange: (next: ScoreResult) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picker, setPicker] = useState<{
    target: PickerTarget;
    x: number;
    y: number;
  } | null>(null);
  const [directiveMenu, setDirectiveMenu] = useState<{
    measureIndex: number;
    x: number;
    y: number;
  } | null>(null);
  const [ledgers, setLedgers] = useState<Record<number, { above: number; below: number }>>(
    {},
  );

  const needed = useMemo(() => {
    const map: Record<number, { above: number; below: number }> = {};
    result.voices.forEach((v, i) => {
      const clef = (v.model.clef === "bass" ? "bass" : "treble") as StaffClef;
      const pitches = v.model.measures.flatMap((m) =>
        m.notes.map((n) =>
          n.isRest || !n.pitch
            ? null
            : { step: n.pitch.step, alter: n.pitch.alter, octave: n.pitch.octave },
        ),
      );
      map[i] = maxLedgerNeeded(pitches, clef);
    });
    return map;
  }, [result.voices]);

  // Grille horizontale partagée → mesures alignées + un seul scroll pour tout le système.
  const layout = useMemo(() => sharedMeasureLayout(result.voices), [result.voices]);

  const ledgerFor = (vi: number) => {
    const n = needed[vi] || { above: 0, below: 0 };
    const u = ledgers[vi] || { above: 0, below: 0 };
    return {
      above: Math.max(n.above, u.above),
      below: Math.max(n.below, u.below),
    };
  };

  const openPicker = useCallback((target: PickerTarget, x: number, y: number) => {
    setDirectiveMenu(null);
    setPicker({ target, x, y });
  }, []);

  const applyDirectiveAndRegen = async (
    measureIndex: number,
    payload: DirectivePayload,
  ) => {
    setDirectiveMenu(null);
    setBusy(true);
    setError(null);
    try {
      const { score: mutated, meterWarnings } = applyDirective(
        result,
        measureIndex,
        payload,
      );
      onChange(await regenerateFromModels(mutated, mutated.voices));
      if (meterWarnings.length) {
        setError(meterWarnings.slice(0, 3).join(" · "));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeChipAndRegen = async (measureIndex: number, chip: DirectiveChip) => {
    setBusy(true);
    setError(null);
    try {
      const mutated = removeDirectiveChip(result, measureIndex, chip);
      onChange(await regenerateFromModels(mutated, mutated.voices));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  /** Décale TOUTE une voix de ±1 octave (corrige une erreur d'octave OMR : le
   *  son ET l'affichage utilisent la même hauteur, donc les deux se remettent
   *  d'aplomb). Réversible d'un clic. */
  const shiftVoiceOctave = async (vi: number, delta: number) => {
    const voice = result.voices[vi];
    if (!voice) return;
    const pitched = voice.model.measures.flatMap((m) =>
      m.notes.filter((n) => !n.isRest && n.pitch),
    );
    if (pitched.length === 0) return;
    // Décalage ATOMIQUE : on ne bouge QUE l'octave, et seulement si TOUTES les
    // notes restent dans [0,9] — sinon on n'en bouge aucune (l'écart entre notes
    // ne doit jamais changer). step/altération/durée/liaisons restent intacts.
    const octs = pitched.map((n) => n.pitch!.octave);
    if (Math.min(...octs) + delta < 0 || Math.max(...octs) + delta > 9) {
      setError("Décalage impossible : octave hors limites (0–9).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = cloneScore(result);
      for (const m of next.voices[vi].model.measures) {
        for (const n of m.notes) {
          if (!n.isRest && n.pitch) n.pitch.octave += delta;
        }
      }
      onChange(await regenerateFromModels(next, next.voices));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const applyChoice = async (choice: NotePickerChoice) => {
    if (!picker) return;
    const { target } = picker;
    setPicker(null);
    setBusy(true);
    setError(null);
    try {
      const next = cloneScore(result);
      const voice = next.voices[target.voiceIndex];
      const clef = (voice.model.clef === "bass" ? "bass" : "treble") as StaffClef;
      const measure = voice.model.measures[target.measureIndex];
      const tonic = voice.model.tonic || result.header.tonic || "C";
      const dohOctave = voice.model.dohOctave ?? 4;
      const divisions = voice.model.divisions || 1;

      if (choice.kind === "duration") {
        if (target.kind === "note") {
          applyNoteDuration(
            measure.notes[target.noteIndex],
            choice.type,
            divisions,
            choice.dots,
          );
        } else if (target.insertAt < measure.notes.length) {
          applyNoteDuration(
            measure.notes[target.insertAt],
            choice.type,
            divisions,
            choice.dots,
          );
        } else {
          // Nouvelle case vide : silence de la valeur choisie
          measure.notes.push(
            makeNote(voice.model, null, true, choice.type, choice.dots),
          );
        }
      } else if (target.kind === "note") {
        const note = measure.notes[target.noteIndex];
        const staffPos =
          note.isRest || !note.pitch ? 4 : pitchToStaffPos(note.pitch, clef);
        const { isRest, pitch } = optionToPitch(
          choice.id,
          staffPos,
          clef,
          tonic,
          dohOctave,
        );
        applyNotePitch(note, pitch, isRest, tonic, dohOctave);
      } else {
        const { isRest, pitch } = optionToPitch(
          choice.id,
          target.staffPos,
          clef,
          tonic,
          dohOctave,
        );
        if (target.insertAt < measure.notes.length) {
          applyNotePitch(
            measure.notes[target.insertAt],
            pitch,
            isRest,
            tonic,
            dohOctave,
          );
        } else {
          measure.notes.push(makeNote(voice.model, pitch, isRest));
        }
      }

      onChange(await regenerateFromModels(next, next.voices));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      {busy && <p className="text-xs text-stone-500">Mise à jour de la partition…</p>}
      {error && <p className="text-xs text-red-700">{error}</p>}
      {/* Un SEUL système : toutes les portées empilées partagent un unique scroll
          horizontal et la même grille de mesures (colonnes alignées). */}
      <div className="staff-scroll overflow-x-auto rounded border border-stone-200 bg-[#fffcf5] py-2">
        <div className="staff-system" style={{ width: layout.totalW }}>
          {result.voices.map((voice, vi) => {
            const L = ledgerFor(vi);
            // Espace : petit entre voix, plus large avant l'accompagnement (piano).
            const startsAccomp =
              isAccompaniment(voice.name) &&
              (vi === 0 || !isAccompaniment(result.voices[vi - 1].name));
            return (
              <div key={voice.name} className={startsAccomp ? "mt-4" : vi > 0 ? "mt-1" : ""}>
                <VoiceStaff
                  voice={voice}
                  voiceIndex={vi}
                  ledgerAbove={L.above}
                  ledgerBelow={L.below}
                  onAddLedger={(dir) => {
                    setLedgers((prev) => {
                      const cur = ledgerFor(vi);
                      return {
                        ...prev,
                        [vi]: {
                          above: dir === "above" ? cur.above + 1 : cur.above,
                          below: dir === "below" ? cur.below + 1 : cur.below,
                        },
                      };
                    });
                  }}
                  onOpenPicker={openPicker}
                  onOpenDirective={(mi, x, y) => {
                    setPicker(null);
                    setDirectiveMenu({ measureIndex: mi, x, y });
                  }}
                  onRemoveChip={(mi, chip) => void removeChipAndRegen(mi, chip)}
                  onShiftOctave={(delta) => void shiftVoiceOctave(vi, delta)}
                  showDirectives={vi === 0}
                  busy={busy}
                  measureWidths={layout.widths}
                  measureStarts={layout.starts}
                  totalW={layout.totalW}
                />
              </div>
            );
          })}
        </div>
      </div>
      {picker && (
        <NotePicker
          x={picker.x}
          y={picker.y}
          currentType={
            picker.target.kind === "note"
              ? result.voices[picker.target.voiceIndex]?.model.measures[
                  picker.target.measureIndex
                ]?.notes[picker.target.noteIndex]?.type
              : undefined
          }
          currentDots={
            picker.target.kind === "note"
              ? result.voices[picker.target.voiceIndex]?.model.measures[
                  picker.target.measureIndex
                ]?.notes[picker.target.noteIndex]?.dots
              : 0
          }
          onSelect={(choice) => void applyChoice(choice)}
          onClose={() => setPicker(null)}
        />
      )}
      {directiveMenu && result.voices[0] && (
        <MeasureDirectiveMenu
          x={directiveMenu.x}
          y={directiveMenu.y}
          defaultBpm={
            Number(
              result.voices[0].model.measures[
                directiveMenu.measureIndex
              ]?.directions?.find((d) => d.kind === "metronome")?.value,
            ) ||
            result.voices[0].model.tempo ||
            result.header.tempo ||
            120
          }
          defaultBeats={
            effectiveTimeSignature(
              result.voices[0].model,
              directiveMenu.measureIndex,
            ).beats
          }
          defaultBeatType={
            effectiveTimeSignature(
              result.voices[0].model,
              directiveMenu.measureIndex,
            ).beatType
          }
          defaultTonic={effectiveTonic(
            result.voices[0].model,
            directiveMenu.measureIndex,
          )}
          onClose={() => setDirectiveMenu(null)}
          onSelect={(payload) =>
            void applyDirectiveAndRegen(directiveMenu.measureIndex, payload)
          }
        />
      )}
      <p className="text-xs text-stone-500">
        Cliquez une note/silence : hauteur (d–t, Doh = {result.header.tonic}) ou
        valeur (ronde…double-croche). Le + en tête de mesure ajoute D.C./tempo/métrique/tonalité.
      </p>
    </div>
  );
}
