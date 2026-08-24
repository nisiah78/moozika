"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/scoresApi";

export type HealthState = "checking" | "up" | "down";

const POLL_MS = 30_000;

/**
 * Sonde l'API Symfony. Le design affiche « Service OMR ● en ligne », mais
 * `HealthResource` renvoie un `status: 'ok'` STATIQUE : Symfony ne sonde pas
 * omr-service. Prétendre connaître l'état du service OMR serait donc une
 * information fabriquée — on nomme ce qu'on mesure réellement, l'API.
 */
export function useApiHealth(): HealthState {
  const [state, setState] = useState<HealthState>("checking");

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;

    const ping = async () => {
      try {
        await api<{ status: string }>("/health");
        if (alive) setState("up");
      } catch {
        if (alive) setState("down");
      } finally {
        if (alive) timer = window.setTimeout(ping, POLL_MS);
      }
    };
    void ping();

    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  return state;
}
