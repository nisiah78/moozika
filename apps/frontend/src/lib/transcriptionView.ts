import type { Transcription } from "@/lib/transcriptionsApi";

/**
 * Traduction d'une transcription en éléments d'affichage.
 *
 * Dans `lib/` et non dans le composant : ce sont des fonctions pures, et le
 * runner de tests du projet exécute du TypeScript sans DOM — de la logique
 * enfermée dans un `.tsx` qui importe des composants React n'y serait pas
 * testable.
 */

export interface StatusTone {
  label: string;
  color: string;
}

/**
 * Les 5 états réels de l'API mappés sur les libellés du design.
 * `cancelled` n'existe pas dans la maquette mais bien dans l'API : l'omettre
 * laisserait une ligne sans état.
 */
export function toneOf(job: Transcription): StatusTone {
  switch (job.status) {
    case "queued":
      return { label: "En file", color: "color-mix(in srgb, var(--color-text) 45%, transparent)" };
    case "running":
      return { label: "Analyse OMR", color: "var(--color-accent)" };
    case "done":
      return { label: "Prête", color: "var(--ok)" };
    case "failed":
      return { label: "Échec", color: "var(--err)" };
    case "cancelled":
      return { label: "Annulée", color: "color-mix(in srgb, var(--color-text) 45%, transparent)" };
  }
}

/** Vignette d'extension : PDF / MXL / XML, comme dans la maquette. */
export function extOf(filename: string | undefined): string {
  const ext = filename?.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "PDF";
  if (ext === "mxl") return "MXL";
  if (ext === "xml" || ext === "musicxml") return "XML";
  return "?";
}

/** Nom affiché : le fichier sans son extension. */
export function displayName(job: Transcription): string {
  return job.sourceFilename?.replace(/\.[^.]+$/, "") || "Transcription";
}
