"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  cancelTranscription,
  isActive,
  listTranscriptions,
  subscribeToTranscription,
  type Transcription,
} from "@/lib/transcriptionsApi";

/**
 * État des transcriptions asynchrones (OMR), monté DANS `layout.tsx`.
 *
 * Pourquoi ici et pas dans une page : ce state vivait dans `page.tsx` justement
 * pour survivre aux changements de vue, à l'époque où l'app était une seule
 * route pilotée par un `useState`. Avec de vraies routes, une page est démontée
 * à chaque navigation — laisser l'état là aurait coupé les abonnements SSE dès
 * que l'utilisateur quitte l'écran. Or une transcription dure 15 à 30 minutes.
 * Le layout, lui, ne se démonte pas d'une route à l'autre.
 */

interface TranscriptionsValue {
  /** Jobs en cours (états non terminaux). */
  jobs: Transcription[];
  /** Jobs terminés pas encore acquittés par l'utilisateur. */
  notifications: Transcription[];
  /** Incrémenté quand une transcription aboutit → la bibliothèque se recharge. */
  libraryReloadKey: number;
  watchJob: (job: Transcription) => void;
  cancelJob: (id: string) => Promise<void>;
  dismissNotification: (id: string) => void;
  /** Appelé à chaque passage en état terminal — branché sur les toasts. */
  onSettled: (handler: (job: Transcription) => void) => () => void;
}

const Ctx = createContext<TranscriptionsValue | null>(null);

export function useTranscriptions(): TranscriptionsValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTranscriptions hors TranscriptionsProvider");
  return v;
}

export function TranscriptionsProvider({ children }: { children: React.ReactNode }) {
  const [jobs, setJobs] = useState<Transcription[]>([]);
  const [notifications, setNotifications] = useState<Transcription[]>([]);
  const [libraryReloadKey, setLibraryReloadKey] = useState(0);
  const subsRef = useRef<Map<string, () => void>>(new Map());
  const settledHandlers = useRef<Set<(job: Transcription) => void>>(new Set());

  const onSettled = useCallback((handler: (job: Transcription) => void) => {
    settledHandlers.current.add(handler);
    return () => {
      settledHandlers.current.delete(handler);
    };
  }, []);

  const applyJobUpdate = useCallback((job: Transcription) => {
    if (isActive(job)) {
      setJobs((prev) => [job, ...prev.filter((j) => j.id !== job.id)]);
      return;
    }
    // État terminal : la carte quitte la grille et devient une notification.
    setJobs((prev) => prev.filter((j) => j.id !== job.id));
    if (job.status !== "cancelled") {
      // Pas de notification pour une annulation : l'utilisateur l'a demandée.
      setNotifications((prev) => [job, ...prev.filter((n) => n.id !== job.id)]);
      settledHandlers.current.forEach((h) => h(job));
    }
    if (job.status === "done") {
      setLibraryReloadKey((k) => k + 1);
    }
    const close = subsRef.current.get(job.id);
    if (close) {
      close();
      subsRef.current.delete(job.id);
    }
  }, []);

  const watchJob = useCallback(
    (job: Transcription) => {
      applyJobUpdate(job);
      if (!isActive(job) || subsRef.current.has(job.id)) return;
      subsRef.current.set(job.id, subscribeToTranscription(job.id, applyJobUpdate));
    },
    [applyJobUpdate],
  );

  // GET initial PUIS abonnement, dans cet ordre : un flux SSE ne rejoue pas
  // l'historique, les messages publiés avant la connexion sont perdus. C'est
  // aussi ce qui fait qu'une transcription en cours réapparaît après un
  // rechargement de page.
  useEffect(() => {
    let alive = true;
    void listTranscriptions()
      .then(({ items }) => {
        if (!alive) return;
        items.filter(isActive).forEach(watchJob);
      })
      .catch(() => {
        /* liste indisponible : on n'empêche pas l'app de démarrer */
      });
    const subs = subsRef.current;
    return () => {
      alive = false;
      subs.forEach((close) => close());
      subs.clear();
    };
  }, [watchJob]);

  const cancelJob = useCallback(
    async (id: string) => {
      applyJobUpdate(await cancelTranscription(id));
    },
    [applyJobUpdate],
  );

  const dismissNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const value = useMemo(
    () => ({
      jobs,
      notifications,
      libraryReloadKey,
      watchJob,
      cancelJob,
      dismissNotification,
      onSettled,
    }),
    [
      jobs,
      notifications,
      libraryReloadKey,
      watchJob,
      cancelJob,
      dismissNotification,
      onSettled,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
