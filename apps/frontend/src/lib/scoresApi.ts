import type { ScoreResult, Voice } from "@/lib/types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080").replace(/\/$/, "");

export interface ScoreListItem {
  id: string;
  title: string;
  tonic: string;
  sourceType: string;
  status: string;
  version: number;
  updatedAt: string;
  createdAt: string;
}

export interface ScoreDetail extends ScoreListItem {
  header: ScoreResult["header"];
  voices: Voice[];
  musicxml: string;
  source?: string;
  warnings?: string[];
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  const data = (await res.json().catch(() => ({}))) as T & { detail?: string };
  if (!res.ok) {
    throw new Error(data.detail || `HTTP ${res.status}`);
  }
  return data;
}

export function listScores(): Promise<{ items: ScoreListItem[] }> {
  return api("/scores");
}

export function getScore(id: string): Promise<ScoreDetail> {
  return api(`/scores/${id}`);
}

export function createScore(body: {
  title: string;
  tonic: string;
  sourceType?: string;
  origin?: string;
  musicxml: string;
  model: { header: ScoreResult["header"]; voices: Voice[]; source?: string; warnings?: string[] };
}): Promise<{ id: string; version: number }> {
  return api("/scores", { method: "POST", body: JSON.stringify(body) });
}

export function addScoreVersion(
  id: string,
  body: {
    title?: string;
    tonic?: string;
    origin?: string;
    musicxml: string;
    model: { header: ScoreResult["header"]; voices: Voice[]; source?: string; warnings?: string[] };
  },
): Promise<{ id: string; version: number }> {
  return api(`/scores/${id}/versions`, { method: "POST", body: JSON.stringify(body) });
}

export function modelToMusicxml(models: Voice["model"][], title: string): Promise<{
  musicxml: string;
  voices: Voice[];
}> {
  return api("/convert/model-to-musicxml", {
    method: "POST",
    body: JSON.stringify({ models, title }),
  });
}

export function detailToScoreResult(detail: ScoreDetail): ScoreResult {
  const h = detail.header;
  return {
    header: {
      title: h?.title || detail.title,
      tonic: h?.tonic || detail.tonic,
      timeSignature: h?.timeSignature || { beats: 4, beatType: 4 },
      tempo: h?.tempo ?? null,
      tempoBeatUnit: h?.tempoBeatUnit ?? null,
      tempoDotted: h?.tempoDotted ?? null,
    },
    voices: detail.voices || [],
    musicxml: detail.musicxml,
    source: detail.source,
    warnings: detail.warnings,
  };
}
