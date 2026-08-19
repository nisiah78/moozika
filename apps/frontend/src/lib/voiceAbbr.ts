import type { Voice } from "@/lib/types";

const VOICE_ABBR: Record<string, string> = {
  Soprano: "S",
  Alto: "A",
  Tenor: "T",
  Bass: "B",
  Piano: "P",
  Violon: "V",
  Violoncelle: "Vc",
  Violoncelles: "Vc",
  Orgue: "O",
  Flute: "Fl",
  Flûte: "Fl",
  Hautbois: "H",
  Clarinette: "Cl",
  Cor: "Co",
  Trompette: "Tr",
  Harpe: "Hp",
};

const PERCUSSION_RE = /percussion|battery|timbales?|drums?|caisse claire|caisse|tambour/i;

/** Abréviation affichée sur la partition (S, S1, P, V…). */
export function voiceAbbr(name: string): string {
  const m = name.match(/^(.*?)\s*(\d+)$/);
  if (m) {
    const baseAbbr = VOICE_ABBR[m[1].trim()] ?? m[1].trim().charAt(0).toUpperCase();
    return `${baseAbbr}${m[2]}`;
  }
  return VOICE_ABBR[name] ?? name.charAt(0).toUpperCase();
}

export function isPercussionVoice(voice: Voice): boolean {
  if (voice.model.midiProgram === 115) return true;
  const label = `${voice.name} ${voice.model.partName}`;
  return PERCUSSION_RE.test(label);
}

export function editableVoiceIndices(voices: Voice[]): number[] {
  return voices.map((v, i) => (isPercussionVoice(v) ? -1 : i)).filter((i) => i >= 0);
}
