import type { ScoreResult, VoiceModel } from "@/lib/types";
import type { KeySignatureEntry } from "@/lib/keySignatures";
import { parseSolfaNotation, rebuildVoiceNotation } from "@/lib/scoreEdit";
import { modelToMusicxml } from "@/lib/scoresApi";

export interface NewScoreSpec {
  title: string;
  composer: string;
  keyEntry: KeySignatureEntry;
  beats: number;
  beatType: number;
  totalMeasures: number;
  voiceNames: string[];
}

/**
 * Le modèle n'a que deux clefs possibles (`treble` | `bass`,
 * `apps/omr-service/app/solfa/model.py`) : Basse en clé de fa, tout le reste
 * (y compris une voix au nom libre) en clé de sol.
 */
function clefForVoice(name: string): "treble" | "bass" {
  return name.trim().toLowerCase() === "bass" ? "bass" : "treble";
}

/**
 * Construit une partition vierge (silences complets) pour les voix données.
 * Un temps entièrement vide vaut silence (`solfa-format.md`) : la notation
 * générée passe donc par le parseur sol-fa existant, qui garantit que chaque
 * mesure totalise exactement 1 temps, sans dupliquer ce calcul ici.
 */
export async function createBlankScore(spec: NewScoreSpec): Promise<ScoreResult> {
  const { title, composer, keyEntry, beats, beatType, totalMeasures, voiceNames } = spec;

  const blankMeasures: string[][] = Array.from({ length: totalMeasures }, () =>
    Array.from({ length: beats }, () => ""),
  );
  const notation = rebuildVoiceNotation(blankMeasures, beats);

  const parsed = await Promise.all(
    voiceNames.map((name) =>
      parseSolfaNotation(notation, keyEntry.doh, clefForVoice(name), beats, beatType),
    ),
  );

  const models: VoiceModel[] = parsed.map((p, i) => ({
    ...p.model,
    partName: voiceNames[i]!,
  }));

  const converted = await modelToMusicxml(models, { title, composer });
  const baseVoices =
    converted.voices?.length ? converted.voices : parsed.map((p, i) => ({
      name: voiceNames[i]!,
      notation,
      model: models[i]!,
    }));
  const voices = baseVoices.map((v, i) => ({
    ...v,
    name: voiceNames[i] ?? v.name,
    model: { ...v.model, partName: voiceNames[i] ?? v.model.partName },
  }));

  return {
    header: {
      title,
      composer: composer || undefined,
      tonic: keyEntry.doh,
      mode: keyEntry.mode,
      fifths: keyEntry.fifths,
      timeSignature: { beats, beatType },
      tempo: null,
    },
    voices,
    musicxml: converted.musicxml,
  };
}
