import { SavedScoreScreen } from "@/components/SavedScoreScreen";

/**
 * Partition ENREGISTRÉE : son id est dans l'URL, donc la page est partageable
 * et rechargeable. C'est le gain concret du passage aux vraies routes.
 */
export default function ScorePage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams: { vue?: string };
}) {
  return <SavedScoreScreen id={params.id} vue={searchParams.vue} />;
}
