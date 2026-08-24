import type { ScoreListItem } from "@/lib/scoresApi";
import type { Notation } from "@/lib/navigation";

/**
 * Recherche et étiquetage de la bibliothèque, côté CLIENT.
 *
 * Côté client parce que `GET /scores` n'a aucun paramètre de recherche : filtrer
 * ici porte sur les partitions déjà chargées. Le placeholder du champ le dit
 * (« Rechercher un titre… ») — la maquette annonçait « un titre, un
 * compositeur… », or `ScoreListItem` n'expose pas de compositeur.
 */

/** Normalise pour une comparaison insensible à la casse ET aux accents. */
function fold(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

export function searchScores(items: ScoreListItem[], query: string): ScoreListItem[] {
  const q = fold(query.trim());
  if (!q) return items;
  return items.filter((it) => fold(it.title || "").includes(q));
}

const SOURCE_LABEL: Record<string, string> = {
  solfa: "PDF sol-fa",
  staff: "PDF solfège",
  musicxml: "MusicXML",
};

export function sourceLabel(sourceType: string): string {
  return SOURCE_LABEL[sourceType] ?? sourceType;
}

/**
 * À quelle(s) liste(s) de la sidebar une partition appartient.
 *
 * La seule clé disponible sur `GET /scores` est `sourceType` — la liste
 * n'expose ni les voix ni l'en-tête. Le mapping est donc :
 *   solfa    → transcrite d'un PDF sol-fa      → liste Sol-fa
 *   staff    → transcrite d'un PDF de solfège  → liste Solfège
 *   musicxml → import agnostique de notation   → LES DEUX
 *
 * `musicxml` dans les deux listes est un choix délibéré : un MusicXML n'est ni
 * l'un ni l'autre à la source, et le ranger d'un seul côté ferait « disparaître »
 * des partitions de l'autre liste — un ressenti de perte de données. Un
 * `sourceType` inconnu apparaît aussi partout, pour la même raison.
 */
export function notationsOf(sourceType: string): Notation[] {
  if (sourceType === "solfa") return ["solfa"];
  if (sourceType === "staff") return ["solfege"];
  return ["solfa", "solfege"];
}

export function filterByNotation(items: ScoreListItem[], notation: Notation): ScoreListItem[] {
  return items.filter((it) => notationsOf(it.sourceType).includes(notation));
}

/** « 21 août 2026 ». Renvoie null sur une date absente ou invalide. */
export function formatUpdated(iso: string | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
}
