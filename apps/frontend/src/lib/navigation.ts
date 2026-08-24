/**
 * Contrat de navigation. Le type de vue vivait dans `AppDrawer.tsx` ; ce
 * composant disparaît avec le drawer overlay, et le type devait donc sortir
 * avant, sinon `tsc --noEmit` casse (la porte est à tolérance zéro).
 */

/**
 * Notation de lecture. ATTENTION : ne pas confondre avec `Mode`
 * (`"score" | "solfa"`) qui choisit l'éditeur monté DANS le viewer. Ici il
 * s'agit du choix de la sidebar, qui décide dans quelle notation une partition
 * s'OUVRE par défaut.
 *
 * Ce n'est délibérément PAS un filtre de contenu : `sourceType` décrit la
 * provenance d'une partition (`solfa` / `staff` / `musicxml`), pas ce qu'on
 * peut en lire. Toute partition est stockée en MusicXML et lisible dans les
 * deux notations — filtrer là-dessus ferait « disparaître » des partitions et
 * l'étiquette mentirait sur son sens.
 */
export type Notation = "solfa" | "solfege";

export const NOTATIONS: readonly Notation[] = ["solfa", "solfege"] as const;

export const NOTATION_LABEL: Record<Notation, string> = {
  solfa: "Sol-fa",
  solfege: "Solfège",
};

export function isNotation(value: string | undefined): value is Notation {
  return value === "solfa" || value === "solfege";
}

/** Notation → mode d'éditeur du viewer. */
export function notationToMode(n: Notation): "solfa" | "score" {
  return n === "solfa" ? "solfa" : "score";
}

export const ROUTES = {
  library: (n: Notation = "solfa") => `/bibliotheque/${n}`,
  import: () => "/import",
  learn: (n: Notation = "solfa") => `/apprendre/${n}`,
  contact: () => "/contact",
  about: () => "/a-propos",
  score: (id: string) => `/partition/${id}`,
  /** Partition importée mais pas encore enregistrée : elle n'a pas d'id. */
  draft: () => "/partition/nouveau",
} as const;

/**
 * Un item de la sidebar est actif si le chemin courant est le sien ou l'un de
 * ses descendants. On compare sur des segments et non avec `startsWith` brut,
 * pour que `/import` ne s'active pas sur un futur `/importation`.
 */
export function isPathActive(pathname: string, href: string): boolean {
  if (pathname === href) return true;
  return pathname.startsWith(href.endsWith("/") ? href : `${href}/`);
}
