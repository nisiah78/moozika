"use client";

import Link from "next/link";
import { useScoreDraft } from "@/components/ScoreDraftProvider";
import { ScoreWorkspace } from "@/components/ScoreWorkspace";
import { ROUTES } from "@/lib/navigation";

export function DraftScoreScreen() {
  const { draft } = useScoreDraft();

  // Cas réel : rechargement de la page (F5) ou lien collé. L'ébauche vit en
  // mémoire, elle ne survit pas à un rechargement — on le dit franchement au
  // lieu d'afficher une page vide.
  if (!draft) {
    return (
      <div className="mx-auto w-full max-w-[640px] px-8 py-10">
        <div className="moo-kicker mb-1.5">Aucune partition en cours</div>
        <h1 className="mb-3 text-[28px]">Cette ébauche n&apos;existe plus</h1>
        <p className="mb-6 text-sm opacity-75">
          Une partition importée mais non enregistrée vit uniquement en mémoire : elle ne
          survit pas à un rechargement de la page. Réimportez le fichier, puis enregistrez-la
          pour lui donner une adresse permanente.
        </p>
        <Link href={ROUTES.import()} className="moo-btn moo-btn--primary">
          Retour à l&apos;import
        </Link>
      </div>
    );
  }

  // Un import portée (Audiveris) s'ouvre en vue Partition : c'est elle qui
  // porte les outils de correction (octave de voix, renommage) dont un OMR de
  // portée a le plus besoin — pas la vue sol-fa.
  const initialMode = draft.source === "audiveris" ? "score" : "solfa";

  return <ScoreWorkspace initialScore={draft} initialScoreId={null} initialMode={initialMode} />;
}
