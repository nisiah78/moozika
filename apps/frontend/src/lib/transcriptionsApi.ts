import { API_URL, api } from "@/lib/scoresApi";

/**
 * Client des transcriptions asynchrones (Symfony `/transcriptions`).
 *
 * Rappel de forme : l'API **omet** les champs nuls au lieu de les sérialiser à `null`
 * (comportement d'API Platform, vérifié sur le fil). Tous les champs optionnels sont donc
 * typés `?:` et non `| null`.
 */

export type TranscriptionStatus = "queued" | "running" | "done" | "failed" | "cancelled";

/** Phases du contrat SSE — cf. packages/shared-contracts/omr-stream.md. */
export type TranscriptionPhase = "detect" | "ocr" | "layout" | "audiveris" | "convert";

export interface Transcription {
  id: string;
  status: TranscriptionStatus;
  pct?: number;
  phase?: TranscriptionPhase | string;
  message?: string;
  sourceFilename?: string;
  tonic?: string;
  errorCode?: string;
  /** Message destiné à l'affichage. */
  errorMessage?: string;
  /** Détail technique brut (logs Java, trace Python) — jamais le message principal. */
  errorDetail?: string;
  /** Renseigné au succès : c'est ce qui rend la carte cliquable. */
  scoreId?: string;
  createdAt?: string;
  updatedAt?: string;
}

const MERCURE_URL = (
  process.env.NEXT_PUBLIC_MERCURE_URL || "http://localhost:3001/.well-known/mercure"
).replace(/\/$/, "");

export const ACTIVE_STATUSES: TranscriptionStatus[] = ["queued", "running"];

export function isActive(job: Transcription): boolean {
  return ACTIVE_STATUSES.includes(job.status);
}

/** Lance une transcription. Répond 202 : le travail se fait dans le worker. */
export async function createTranscription(file: File, tonic?: string): Promise<Transcription> {
  const form = new FormData();
  form.append("file", file);
  if (tonic) form.append("tonic", tonic);

  // Pas via api() : multipart, donc surtout ne pas poser Content-Type à la main —
  // le navigateur doit calculer lui-même le boundary.
  const res = await fetch(`${API_URL}/transcriptions`, {
    method: "POST",
    headers: { Accept: "application/json" },
    body: form,
  });
  const data = (await res.json().catch(() => ({}))) as Transcription & { detail?: string };
  if (!res.ok) {
    throw new Error(data.detail || `HTTP ${res.status}`);
  }
  return data;
}

export function listTranscriptions(): Promise<{ items: Transcription[] }> {
  return api<{ items: Transcription[] }>("/transcriptions");
}

export function getTranscription(id: string): Promise<Transcription> {
  return api<Transcription>(`/transcriptions/${id}`);
}

export function cancelTranscription(id: string): Promise<Transcription> {
  return api<Transcription>(`/transcriptions/${id}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

/**
 * S'abonne aux mises à jour d'un job via Mercure.
 *
 * `EventSource` natif suffit : l'abonnement Mercure est un GET, contrairement au POST-SSE
 * de `omrStream.ts` qui imposait `fetch` + `getReader`. Aucune dépendance à ajouter.
 *
 * ⚠️ Un abonnement SSE ne rejoue PAS l'historique : les messages publiés avant la connexion
 * sont perdus. L'appelant doit donc faire un `getTranscription()` d'abord et s'abonner
 * ensuite — c'est ce qui fait aussi survivre un rechargement de page.
 */
export function subscribeToTranscription(
  id: string,
  onUpdate: (job: Transcription) => void,
): () => void {
  const url = new URL(MERCURE_URL);
  url.searchParams.append("topic", `/transcriptions/${id}`);

  const source = new EventSource(url.toString());
  source.onmessage = (event: MessageEvent<string>) => {
    try {
      onUpdate(JSON.parse(event.data) as Transcription);
    } catch {
      /* message illisible : on ignore plutôt que de casser l'abonnement */
    }
  };
  // Pas de gestion d'erreur : EventSource se reconnecte tout seul. Et la base reste la
  // source de vérité — un GET de rattrapage corrige tout écart.

  return () => source.close();
}

/**
 * Libellé et mode d'affichage de la progression.
 *
 * Le `%` est un MENSONGE pendant la phase `audiveris` : mesuré, il reste bloqué à 20 pendant
 * 15-30 min (omr-service n'émet aucun événement intermédiaire), ce qui fait passer un
 * traitement sain pour un plantage. Même problème sur un scan mono-page, où `pct` vaut
 * 10 + 55×0/1 = 10 du début à la fin de l'OCR. Dans ces cas : barre indéterminée.
 */
export function progressView(job: Transcription): {
  label: string;
  pct: number | null;
} {
  const label = job.message?.trim() || phaseLabel(job.phase);
  const indeterminate = job.phase === "audiveris" || job.phase === "ocr";
  return { label, pct: indeterminate ? null : (job.pct ?? 0) };
}

function phaseLabel(phase?: string): string {
  switch (phase) {
    case "detect":
      return "Analyse du document…";
    case "ocr":
      return "Lecture du texte…";
    case "layout":
      return "Reconstruction des voix…";
    case "audiveris":
      return "Reconnaissance de la portée…";
    case "convert":
      return "Conversion en partition…";
    default:
      return "En attente…";
  }
}
