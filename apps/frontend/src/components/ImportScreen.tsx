"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  isMusicXmlFile,
  isPdfFile,
  musicXmlResponseToScoreResult,
  readMusicXmlContent,
} from "@/lib/scoreImport";
import type { MusicXmlParseResponse } from "@/lib/types";
import { createTranscription } from "@/lib/transcriptionsApi";
import { useTranscriptions } from "@/components/TranscriptionsProvider";
import { useScoreDraft } from "@/components/ScoreDraftProvider";
import { useToasts } from "@/components/Toasts";
import { ROUTES } from "@/lib/navigation";
import { TranscriptionRow } from "@/components/TranscriptionRow";
import { IconPlus, IconUpload } from "@/components/icons";

export function ImportScreen() {
  const router = useRouter();
  const { watchJob, jobs, cancelJob, notifications, dismissNotification } = useTranscriptions();
  const { setDraft } = useScoreDraft();
  const { push } = useToasts();
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fail = useCallback(
    (e: unknown) =>
      push({
        kind: "err",
        title: "Import impossible",
        body: e instanceof Error ? e.message : String(e),
      }),
    [push],
  );

  // Import PDF = transcription ASYNCHRONE. On ne bloque pas l'écran sur un flux
  // de 15-30 min : Symfony répond 202, le travail part dans le worker, et
  // l'utilisateur voit une ligne « en cours ».
  const uploadPdf = useCallback(
    async (file: File) => {
      try {
        watchJob(await createTranscription(file));
        push({ kind: "info", title: "Import lancé", body: "Traitement OMR en file d'attente…" });
      } catch (e) {
        fail(e);
      }
    },
    [watchJob, push, fail],
  );

  const uploadMusicXml = useCallback(
    async (file: File) => {
      setLoading(true);
      try {
        const form = new FormData();
        form.append("file", file);
        const [musicxml, res] = await Promise.all([
          readMusicXmlContent(file),
          fetch("/api/musicxml/parse", { method: "POST", body: form }),
        ]);
        const data = (await res.json()) as MusicXmlParseResponse & { detail?: string };
        if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
        // Le score n'a pas encore d'id : il traverse la frontière de route par
        // le provider d'ébauche, puis /partition/nouveau l'affiche.
        setDraft(musicXmlResponseToScoreResult(data, file, musicxml));
        router.push(ROUTES.draft());
      } catch (e) {
        fail(e);
      } finally {
        setLoading(false);
      }
    },
    [setDraft, router, fail],
  );

  const onFile = useCallback(
    (file: File) => {
      if (isPdfFile(file)) return void uploadPdf(file);
      if (isMusicXmlFile(file)) return void uploadMusicXml(file);
      fail(
        new Error(
          "Format non supporté. PDF sol-fa malgache, PDF de solfège, " +
            "ou MusicXML (.xml, .musicxml, .mxl) exporté depuis un logiciel de notation.",
        ),
      );
    },
    [uploadPdf, uploadMusicXml, fail],
  );

  const pick = useCallback((file: File | undefined) => {
    if (file) onFile(file);
  }, [onFile]);

  return (
    <div className="mx-auto w-full max-w-[860px] px-[34px] py-[34px]">
      <div className="moo-kicker mb-1.5">Import</div>
      <h1 className="mb-[22px] text-[34px]">Importer une partition</h1>

      {/* Zone de dépôt. `label` + input caché : le clic natif du label ouvre le
          sélecteur, donc le clavier y accède sans handler maison. */}
      <label className="block cursor-pointer">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pick(e.dataTransfer.files?.[0]);
          }}
          className="border-2 border-dashed px-6 py-[52px] text-center transition-colors"
          style={{
            borderColor: dragging ? "var(--color-accent)" : "var(--color-divider)",
            background: dragging
              ? "color-mix(in srgb, var(--color-accent) 8%, var(--color-surface))"
              : "var(--color-surface)",
          }}
        >
          <div
            className="mx-auto mb-4 grid h-14 w-14 place-items-center"
            style={{ background: "var(--color-surface-2)", color: "var(--color-accent)" }}
          >
            <IconUpload size={26} />
          </div>
          <div className="font-sans text-[19px] font-extrabold">
            Déposez un fichier ou cliquez pour parcourir
          </div>
          <div className="mt-2 text-[13px] opacity-70">
            PDF sol-fa malgache · PDF solfège · MusicXML (.xml / .mxl)
          </div>
          <div className="moo-btn moo-btn--primary mt-5 gap-2">
            <IconPlus size={16} />
            Choisir un fichier
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,.xml,.musicxml,.mxl"
          className="hidden"
          onChange={(e) => {
            pick(e.target.files?.[0]);
            // Réinitialise pour que réimporter le MÊME fichier redéclenche
            // `change` (sinon la valeur identique n'émet plus rien).
            e.target.value = "";
          }}
        />
      </label>

      {loading && <p className="mt-4 text-sm opacity-70">Analyse du MusicXML…</p>}

      {jobs.length > 0 && (
        <>
          <hr className="moo-hr" />
          <div className="mb-2.5 flex items-center justify-between">
            <h4 className="m-0 text-base">Transcriptions en cours</h4>
            <span className="text-[11px] opacity-55">Traitement asynchrone · OMR</span>
          </div>
          <div className="flex flex-col gap-0.5 bg-divider">
            {jobs.map((job) => (
              <TranscriptionRow
                key={job.id}
                job={job}
                cancelling={cancelling === job.id}
                onCancel={(id) => {
                  setCancelling(id);
                  void cancelJob(id)
                    .catch(fail)
                    .finally(() => setCancelling(null));
                }}
              />
            ))}
          </div>
        </>
      )}

      {notifications.length > 0 && (
        /* Doublure des toasts : si l'utilisateur en manque un, la trace reste
           consultable ici. La cloche de l'ancien header a disparu. */
        <>
          <hr className="moo-hr" />
          <div className="mb-2.5 flex items-center justify-between">
            <h4 className="m-0 text-base">Terminées récemment</h4>
            <button
              type="button"
              onClick={() => notifications.forEach((n) => dismissNotification(n.id))}
              className="moo-btn moo-btn--ghost text-[13px]"
            >
              Tout masquer
            </button>
          </div>
          <div className="flex flex-col gap-0.5 bg-divider">
            {notifications.map((job) => {
              const name = job.sourceFilename?.replace(/\.[^.]+$/, "") || "Transcription";
              const ok = job.status === "done" && Boolean(job.scoreId);
              return (
                <div key={job.id} className="flex items-center gap-4 bg-surface px-[18px] py-3.5">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-sans text-sm font-extrabold">{name}</div>
                    <div
                      className="mt-0.5 text-[11px]"
                      style={{ color: ok ? "var(--ok)" : "var(--err)" }}
                    >
                      {ok ? "Prête" : job.errorMessage || "Échec"}
                    </div>
                  </div>
                  {ok && (
                    <button
                      type="button"
                      onClick={() => router.push(ROUTES.score(job.scoreId as string))}
                      className="moo-btn moo-btn--ghost"
                    >
                      Ouvrir
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => dismissNotification(job.id)}
                    aria-label={`Masquer ${name}`}
                    className="flex-none opacity-50 hover:opacity-100"
                  >
                    ✕
                  </button>
                </div>
              );
            })}
          </div>
        </>
      )}

      {jobs.length === 0 && notifications.length === 0 && (
        <p className="mt-6 text-[13px] opacity-55">
          Les PDF sont transcrits en tâche de fond : vous pouvez quitter cet écran, une
          notification vous prévient dès que la partition est prête.
        </p>
      )}
    </div>
  );
}
