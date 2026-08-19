import { buildSolfaSystems, formatMeasureBeats } from "@/lib/solfaScore";
import type { TempoSettings } from "@/lib/tempo";
import { formatTempoLabel } from "@/lib/tempo";
import type { ScoreResult } from "@/lib/types";
import { voiceAbbr } from "@/lib/voiceAbbr";

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

function padRight(value: string, width: number): string {
  return value.padEnd(Math.max(width, value.length), " ");
}

function formatLyricsMeasure(
  measureAbs: number,
  beatCount: number,
  widths: number[],
  lyrics: Record<string, string>,
  beatsPerMeasure: number,
): string {
  const parts: string[] = [];
  for (let bi = 0; bi < beatCount; bi++) {
    const text = (lyrics[`${measureAbs}-${bi}`] ?? "").trim();
    const width = Math.max(widths[bi] ?? 1, text.length || 1);
    parts.push(padRight(text, width));
    if (bi < beatCount - 1) {
      const mid = beatsPerMeasure > 0 && bi + 1 === Math.floor(beatsPerMeasure / 2);
      parts.push(mid ? " ! " : " : ");
    }
  }
  return parts.join("");
}

function buildSystemLines(
  system: ReturnType<typeof buildSolfaSystems>[number],
  lyrics: Record<string, string>,
): string[] {
  const labelWidth = Math.max(
    1,
    ...system.voices.map((voice) => voiceAbbr(voice.name).length),
    Object.keys(lyrics).length > 0 ? 1 : 0,
  );

  const voiceLines = system.voices.map((voice) => {
    const measures = voice.measures.map((measure, mi) =>
      formatMeasureBeats(
        measure.beats.map((beat) => ({ ...beat, text: beat.text })),
        system.colWidths[mi] ?? [],
        measure.beats.length,
      ),
    );
    return `${padRight(voiceAbbr(voice.name), labelWidth)} | ${measures.join(" | ")} |`;
  });

  const lyricMeasures = Array.from({ length: system.voices[0]?.measures.length ?? 0 }, (_, mi) => {
    const measureAbs = system.startNumber - 1 + mi;
    const beatCount = system.voices[0]?.measures[mi]?.beats.length ?? 0;
    return formatLyricsMeasure(
      measureAbs,
      beatCount,
      system.colWidths[mi] ?? [],
      lyrics,
      beatCount,
    );
  });
  const hasLyrics = lyricMeasures.some((measure) => measure.trim().length > 0);

  return hasLyrics
    ? [...voiceLines, `${padRight("", labelWidth)} | ${lyricMeasures.join(" | ")} |`]
    : voiceLines;
}

export function buildSolfaMarkdown(
  result: ScoreResult,
  tempo: TempoSettings,
  lyrics: Record<string, string> = {},
): string {
  const title = prettyTitle(result.header.title);
  const subtitle = lookupSubtitle(title);
  const { beats, beatType } = result.header.timeSignature;
  const systems = buildSolfaSystems(result);

  const lines = [
    `# ${title}`,
    result.header.composer?.trim(),
    result.header.work?.trim(),
    !result.header.composer && subtitle ? `(${subtitle})` : null,
    "",
    `Do dia ${result.header.tonic}${result.header.mode === "minor" ? " (mineur)" : ""}, ${beats}/${beatType}`,
    formatTempoLabel(tempo),
    "",
    "```text",
    ...systems.flatMap((system, index) => [
      ...(index > 0 ? [""] : []),
      ...buildSystemLines(system, lyrics),
    ]),
    "```",
    "",
  ].flatMap((line) => (line == null ? [] : [line]));

  return `${lines.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd()}\n`;
}
