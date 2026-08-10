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
  const title = file.name.replace(/\.(xml|musicxml|mxl)$/i, "");
  return {
    header: {
      title,
      tonic: data.header.tonic,
      timeSignature: {
        beats: data.header.beats,
        beatType: data.header.beatType,
      },
      tempo: data.header.tempo,
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
