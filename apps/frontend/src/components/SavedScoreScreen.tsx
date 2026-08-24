"use client";

import { useEffect, useState } from "react";
import { detailToScoreResult, getScore } from "@/lib/scoresApi";
import type { ScoreResult } from "@/lib/types";
import { ScoreWorkspace } from "@/components/ScoreWorkspace";
import { isNotation, notationToMode } from "@/lib/navigation";

export function SavedScoreScreen({ id, vue }: { id: string; vue?: string }) {
  const [score, setScore] = useState<ScoreResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setScore(null);
    setError(null);
    void getScore(id)
      .then((detail) => {
        if (alive) setScore(detailToScoreResult(detail));
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) {
    return (
      <div className="px-8 py-8">
        <p className="text-sm" style={{ color: "var(--err)" }}>
          Impossible de charger cette partition : {error}
        </p>
      </div>
    );
  }
  if (!score) return <div className="px-8 py-8 text-sm opacity-70">Chargement…</div>;

  return (
    <ScoreWorkspace
      initialScore={score}
      initialScoreId={id}
      initialMode={isNotation(vue) ? notationToMode(vue) : "solfa"}
    />
  );
}
