/**
 * Client SSE pour POST /api/pdf/parse/stream.
 * Contrat : packages/shared-contracts/omr-stream.md
 *
 * Si le flux est coupé (Chrome ERR_NETWORK_IO_SUSPENDED, proxy, sleep OS),
 * repli automatique sur POST /api/pdf/parse (sync).
 */
import type { OmStreamEvent, ScoreResult, Voice } from "./types";

function parseSseChunk(
  buffer: string,
): { events: OmStreamEvent[]; rest: string } {
  const events: OmStreamEvent[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";

  for (const block of parts) {
    const trimmed = block.trim();
    if (!trimmed || trimmed.startsWith(":")) continue; // heartbeat

    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of trimmed.split("\n")) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (!dataLines.length) continue;
    try {
      const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
      if (eventName === "progress") {
        events.push({
          event: "progress",
          phase: String(data.phase ?? ""),
          pct: Number(data.pct ?? 0),
          message: String(data.message ?? ""),
        });
      } else if (eventName === "voice") {
        events.push({
          event: "voice",
          index: Number(data.index ?? 0),
          total: Number(data.total ?? 0),
          voice: data.voice as Voice,
        });
      } else if (eventName === "done") {
        events.push({
          event: "done",
          result: data.result as ScoreResult,
        });
      } else if (eventName === "error") {
        events.push({
          event: "error",
          detail: String(data.detail ?? "erreur inconnue"),
        });
      }
    } catch {
      // ignore malformed JSON chunks
    }
  }
  return { events, rest };
}

export type StreamHandlers = {
  onProgress?: (phase: string, pct: number, message: string) => void;
  onVoice?: (index: number, total: number, voice: Voice) => void;
};

function isNetworkCut(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  return (
    err.name === "TypeError" ||
    msg.includes("network") ||
    msg.includes("fetch") ||
    msg.includes("failed to fetch") ||
    msg.includes("flux sse terminé") ||
    msg.includes("aborted")
  );
}

async function parsePdfSync(file: File): Promise<ScoreResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/pdf/parse", { method: "POST", body: form });
  const data = (await res.json()) as ScoreResult & { detail?: string };
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
  return data;
}

/**
 * Upload un PDF via le proxy SSE. Résout avec le ScoreResult final
 * ou rejette avec le message d'erreur. Repli sync si le flux est coupé.
 */
export async function parsePdfStream(
  file: File,
  handlers: StreamHandlers = {},
): Promise<ScoreResult> {
  const form = new FormData();
  form.append("file", file);

  let res: Response;
  try {
    res = await fetch("/api/pdf/parse/stream", {
      method: "POST",
      body: form,
      cache: "no-store",
    });
  } catch (err) {
    handlers.onProgress?.(
      "convert",
      5,
      "Flux interrompu, reprise sans progression…",
    );
    return parsePdfSync(file);
  }

  // JSON d'erreur (502 proxy) plutôt que SSE
  const ct = res.headers.get("content-type") ?? "";
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = (await res.json()) as { detail?: string };
      if (j.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  if (!res.body || !ct.includes("text/event-stream")) {
    // Proxy a renvoyé autre chose — tenter sync
    handlers.onProgress?.("convert", 5, "Reprise sans progression…");
    return parsePdfSync(file);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSseChunk(buffer);
      buffer = rest;

      for (const ev of events) {
        if (ev.event === "progress") {
          handlers.onProgress?.(ev.phase, ev.pct, ev.message);
        } else if (ev.event === "voice") {
          handlers.onVoice?.(ev.index, ev.total, ev.voice);
        } else if (ev.event === "done") {
          return ev.result;
        } else if (ev.event === "error") {
          throw new Error(ev.detail);
        }
      }
    }
    throw new Error("flux SSE terminé sans résultat");
  } catch (err) {
    try {
      await reader.cancel();
    } catch {
      /* ignore */
    }
    if (isNetworkCut(err)) {
      handlers.onProgress?.(
        "convert",
        5,
        "Connexion suspendue, reprise sans progression…",
      );
      return parsePdfSync(file);
    }
    throw err;
  }
}
