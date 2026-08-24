import { DraftScoreScreen } from "@/components/DraftScoreScreen";

/**
 * Partition importée mais PAS ENREGISTRÉE : elle n'a pas d'id, donc aucune URL
 * ne peut porter son contenu. Elle vit dans `ScoreDraftProvider` (monté dans le
 * layout, donc survivant à la navigation depuis /import). Ce segment statique
 * est résolu avant le segment dynamique [id], donc pas de collision.
 */
export default function DraftScorePage() {
  return <DraftScoreScreen />;
}
