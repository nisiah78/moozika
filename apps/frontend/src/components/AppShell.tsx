"use client";

import { useEffect } from "react";
import { Sidebar } from "@/components/Sidebar";
import { useTranscriptions } from "@/components/TranscriptionsProvider";
import { useToasts } from "@/components/Toasts";
import { useRouter } from "next/navigation";
import { ROUTES } from "@/lib/navigation";

/**
 * Coquille de l'application : sidebar persistante + zone principale.
 *
 * C'est aussi ici qu'on relie les transcriptions aux toasts : le provider
 * signale les passages en état terminal, la coquille les traduit en toasts.
 * Ce câblage vit au-dessus des pages pour que la notification arrive même si
 * l'utilisateur a quitté l'écran d'import — c'est tout l'intérêt d'un
 * traitement asynchrone de 15 à 30 minutes.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const { onSettled } = useTranscriptions();
  const { push } = useToasts();
  const router = useRouter();

  useEffect(
    () =>
      onSettled((job) => {
        const name = job.sourceFilename?.replace(/\.[^.]+$/, "") || "Transcription";
        if (job.status === "done" && job.scoreId) {
          const id = job.scoreId;
          push({
            kind: "ok",
            title: "Partition prête",
            body: `« ${name} » a été transcrite.`,
            sticky: true,
            action: { label: "Ouvrir la partition", run: () => router.push(ROUTES.score(id)) },
          });
        } else {
          push({
            kind: "err",
            title: "Transcription échouée",
            body: job.errorMessage || `« ${name} » n'a pas pu être transcrite.`,
            sticky: true,
          });
        }
      }),
    [onSettled, push, router],
  );

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col">{children}</main>
    </div>
  );
}
