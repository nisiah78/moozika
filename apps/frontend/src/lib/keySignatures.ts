import type { ScoreResult } from "@/lib/types";

export type KeyMode = "major" | "minor";

export interface KeySignatureEntry {
  id: string;
  fifths: number;
  mode: KeyMode;
  /** Doh (mouvable-do) — relative majeure en mineur la-based. */
  doh: string;
  labelFr: string;
  accDisplay: string;
}

const MAJOR: Array<{ fifths: number; doh: string; labelFr: string }> = [
  { fifths: 0, doh: "C", labelFr: "Do majeur" },
  { fifths: 1, doh: "G", labelFr: "Sol majeur" },
  { fifths: 2, doh: "D", labelFr: "Ré majeur" },
  { fifths: 3, doh: "A", labelFr: "La majeur" },
  { fifths: 4, doh: "E", labelFr: "Mi majeur" },
  { fifths: 5, doh: "B", labelFr: "Si majeur" },
  { fifths: 6, doh: "F#", labelFr: "Fa# majeur" },
  { fifths: 7, doh: "C#", labelFr: "Do# majeur" },
  { fifths: -1, doh: "F", labelFr: "Fa majeur" },
  { fifths: -2, doh: "Bb", labelFr: "Sib majeur" },
  { fifths: -3, doh: "Eb", labelFr: "Mib majeur" },
  { fifths: -4, doh: "Ab", labelFr: "Lab majeur" },
  { fifths: -5, doh: "Db", labelFr: "Réb majeur" },
  { fifths: -6, doh: "Gb", labelFr: "Solb majeur" },
  { fifths: -7, doh: "Cb", labelFr: "Dob majeur" },
];

const MINOR: Array<{ fifths: number; doh: string; labelFr: string }> = [
  { fifths: 0, doh: "C", labelFr: "La mineur" },
  { fifths: 1, doh: "G", labelFr: "Mi mineur" },
  { fifths: 2, doh: "D", labelFr: "Si mineur" },
  { fifths: 3, doh: "A", labelFr: "Fa# mineur" },
  { fifths: 4, doh: "E", labelFr: "Do# mineur" },
  { fifths: 5, doh: "B", labelFr: "Sol# mineur" },
  { fifths: 6, doh: "F#", labelFr: "Ré# mineur" },
  { fifths: 7, doh: "C#", labelFr: "La# mineur" },
  { fifths: -1, doh: "F", labelFr: "Ré mineur" },
  { fifths: -2, doh: "Bb", labelFr: "Sol mineur" },
  { fifths: -3, doh: "Eb", labelFr: "Do mineur" },
  { fifths: -4, doh: "Ab", labelFr: "Fa mineur" },
  { fifths: -5, doh: "Db", labelFr: "Sib mineur" },
  { fifths: -6, doh: "Gb", labelFr: "Mib mineur" },
  { fifths: -7, doh: "Cb", labelFr: "Lab mineur" },
];

function accDisplayFor(fifths: number): string {
  if (fifths === 0) return "—";
  if (fifths > 0) return `${fifths}#`;
  return `${-fifths}b`;
}

function buildEntries(
  rows: Array<{ fifths: number; doh: string; labelFr: string }>,
  mode: KeyMode,
): KeySignatureEntry[] {
  return rows.map((r) => ({
    id: `${r.fifths}:${mode}`,
    fifths: r.fifths,
    mode,
    doh: r.doh,
    labelFr: r.labelFr,
    accDisplay: accDisplayFor(r.fifths),
  }));
}

export const KEY_SIGNATURE_OPTIONS: KeySignatureEntry[] = [
  ...buildEntries(MAJOR, "major"),
  ...buildEntries(MINOR, "minor"),
];

export function formatKeyOption(entry: KeySignatureEntry): string {
  return `${entry.accDisplay.padStart(3, " ")}  ${entry.labelFr}`;
}

export function keySignatureFromHeader(
  header: ScoreResult["header"],
  voiceFifths?: number,
): KeySignatureEntry {
  const fifths = header.fifths ?? voiceFifths ?? 0;
  const mode = (header.mode ?? "major") as KeyMode;
  const doh = header.tonic || "C";
  const f = fifths ?? 0;
  const found = KEY_SIGNATURE_OPTIONS.find(
    (k) => k.fifths === f && k.mode === mode && k.doh === doh,
  );
  if (found) return found;
  const fallback = KEY_SIGNATURE_OPTIONS.find(
    (k) => k.fifths === f && k.mode === mode,
  );
  return fallback ?? KEY_SIGNATURE_OPTIONS[0]!;
}

export function applyKeySignature(entry: KeySignatureEntry): {
  tonic: string;
  mode: KeyMode;
  fifths: number;
} {
  return { tonic: entry.doh, mode: entry.mode, fifths: entry.fifths };
}
