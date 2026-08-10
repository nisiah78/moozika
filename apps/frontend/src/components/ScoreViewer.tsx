"use client";

import { forwardRef } from "react";
import type { TempoSettings } from "@/lib/tempo";
import type { ScoreResult } from "@/lib/types";
import { SolfaScore, type SolfaScoreHandle } from "@/components/SolfaScore";
import { StaffEditor } from "@/components/StaffEditor";

type Mode = "score" | "solfa";

export type ScoreViewerHandle = SolfaScoreHandle;

/**
 * Un seul éditeur monté à la fois.
 * Monter les deux (l'un en `hidden`) forçait React à réconcilier tout le SVG
 * StaffEditor à chaque édition sol-fa — catastrophique au-delà de ~30 mesures.
 */
export const ScoreViewer = forwardRef<
  ScoreViewerHandle,
  {
    result: ScoreResult;
    mode: Mode;
    tempo: TempoSettings;
    onTempoChange: (next: TempoSettings) => void;
    onChange: (next: ScoreResult) => void;
  }
>(function ScoreViewer(
  { result, mode, tempo, onTempoChange, onChange },
  ref,
) {
  if (mode === "score") {
    return <StaffEditor result={result} onChange={onChange} />;
  }

  return (
    <SolfaScore
      ref={ref}
      result={result}
      tempo={tempo}
      onTempoChange={onTempoChange}
      onChange={onChange}
    />
  );
});
