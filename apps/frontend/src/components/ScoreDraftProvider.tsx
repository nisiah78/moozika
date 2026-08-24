"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ScoreResult } from "@/lib/types";

/**
 * Porte la partition importée mais PAS ENCORE ENREGISTRÉE.
 *
 * Raison d'être : après un import MusicXML, le `ScoreResult` existe en mémoire
 * et n'a aucun `scoreId` — donc aucune URL ne peut le désigner. Avec de vraies
 * routes, la page d'import est démontée quand on navigue vers le viewer : sans
 * ce provider, le score importé serait perdu entre les deux.
 *
 * Ce n'est délibérément PAS un cache de partitions : une seule ébauche à la
 * fois, effacée dès qu'elle est enregistrée (elle a alors un id et une URL).
 */

interface DraftValue {
  draft: ScoreResult | null;
  setDraft: (s: ScoreResult | null) => void;
}

const Ctx = createContext<DraftValue | null>(null);

export function useScoreDraft(): DraftValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useScoreDraft hors ScoreDraftProvider");
  return v;
}

export function ScoreDraftProvider({ children }: { children: React.ReactNode }) {
  const [draft, setDraftState] = useState<ScoreResult | null>(null);
  const setDraft = useCallback((s: ScoreResult | null) => setDraftState(s), []);
  const value = useMemo(() => ({ draft, setDraft }), [draft, setDraft]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
