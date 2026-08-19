import type { MusicXmlParseResponse, ScoreResult } from "./types";

const MUSICXML_EXT = /\.(xml|musicxml|mxl)$/i;

export function isMusicXmlFile(file: File): boolean {
  if (isPdfFile(file)) return false;
  if (MUSICXML_EXT.test(file.name)) return true;
  const t = file.type.toLowerCase();
  return t.includes("xml") || t === "application/vnd.recordare.musicxml+xml";
}

export function isPdfFile(file: File): boolean {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

export function musicXmlResponseToScoreResult(
  data: MusicXmlParseResponse,
  file: File,
  musicxml: string,
): ScoreResult {
  const fallbackTitle = file.name.replace(/\.(xml|musicxml|mxl)$/i, "");
  const h = data.header;
  return {
    header: {
      title: h.title?.trim() || fallbackTitle,
      composer: h.composer?.trim() || undefined,
      work: h.work?.trim() || undefined,
      tonic: h.tonic,
      mode: h.mode === "minor" ? "minor" : "major",
      fifths: h.fifths ?? data.voices[0]?.model?.fifths ?? 0,
      timeSignature: {
        beats: h.beats,
        beatType: h.beatType,
      },
      tempo: h.tempo,
    },
    voices: data.voices,
    musicxml,
    uploadedFile: file.name.toLowerCase().endsWith(".mxl") ? file : undefined,
    warnings: data.warnings,
  };
}

/** Lit le contenu XML d'un fichier (vide pour .mxl — OSMD charge l'archive). */
export async function readMusicXmlContent(file: File): Promise<string> {
  if (file.name.toLowerCase().endsWith(".mxl")) return "";
  return file.text();
}
