"use client";

import { progressView, type Transcription } from "@/lib/transcriptionsApi";
import { IconClose } from "@/components/icons";
import { displayName, extOf, toneOf } from "@/lib/transcriptionView";

/**
 * Ligne d'une transcription, telle que la maquette la dessine sur l'écran
 * d'import (et non plus une carte A4 dans la grille de la bibliothèque).
 *
 * Volontairement NON cliquable tant qu'il n'y a pas de partition : il n'y a
 * rien à ouvrir. Le lien d'ouverture apparaît dans « Terminées récemment ».
 */

export function TranscriptionRow({
  job,
  onCancel,
  cancelling,
}: {
  job: Transcription;
  onCancel: (id: string) => void;
  cancelling?: boolean;
}) {
  const { label: progressLabel, pct } = progressView(job);
  const tone = toneOf(job);
  const name = displayName(job);
  const failed = job.status === "failed";
  const active = job.status === "queued" || job.status === "running";

  return (
    <div className="flex items-center gap-4 bg-surface px-[18px] py-4">
      <div
        className="grid h-[46px] w-[38px] flex-none place-items-center border border-divider font-sans text-[9px] font-extrabold"
        style={{ background: "var(--paper)", color: "var(--paper-ink)" }}
        aria-hidden
      >
        {extOf(job.sourceFilename)}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <span className="truncate font-sans text-sm font-extrabold" title={name}>
            {name}
          </span>
          <span
            className="flex-none font-sans text-[11px] font-extrabold uppercase tracking-[0.04em]"
            style={{ color: tone.color }}
          >
            {tone.label}
          </span>
        </div>

        <ProgressBar job={job} pct={pct} />

        <div className="mt-1.5 text-[11px] opacity-55">
          {failed ? job.errorMessage || "Échec de la transcription." : progressLabel}
          {!failed && pct !== null && ` · ${pct} %`}
        </div>

        {failed && job.errorDetail && (
          <details className="mt-1 text-[11px]" style={{ color: "var(--err)" }}>
            <summary className="cursor-pointer">Détails techniques</summary>
            <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap break-words">
              {job.errorDetail}
            </pre>
          </details>
        )}
      </div>

      {active && (
        <button
          type="button"
          disabled={cancelling}
          onClick={() => onCancel(job.id)}
          title="Annuler cette transcription"
          aria-label={`Annuler la transcription de ${name}`}
          className="grid h-8 w-8 flex-none place-items-center border border-divider disabled:opacity-40"
        >
          <IconClose size={15} />
        </button>
      )}
    </div>
  );
}

function ProgressBar({ job, pct }: { job: Transcription; pct: number | null }) {
  // Piste 6px sur surface-2, comme la maquette.
  const track = "mt-2.5 h-1.5 overflow-hidden bg-surface-2";

  if (job.status === "done") {
    return (
      <div className={track}>
        <div className="h-full w-full" style={{ background: "var(--ok)" }} />
      </div>
    );
  }
  if (job.status === "failed") {
    return (
      <div className={track}>
        <div className="h-full w-full" style={{ background: "var(--err)" }} />
      </div>
    );
  }
  if (job.status === "cancelled") {
    return (
      <div className={track}>
        <div className="h-full w-full" style={{ background: "var(--color-divider)" }} />
      </div>
    );
  }

  // pct === null : progressView() dit que le pourcentage serait TROMPEUR
  // (phases `audiveris` et `ocr` mono-page restent figées 15-30 min). Le
  // shimmer du design est précisément une barre indéterminée : on l'utilise ici
  // et NULLE PART ailleurs, pour qu'il signale « progression non mesurable »
  // au lieu de simplement décorer.
  if (pct === null) {
    return (
      <div className={track}>
        <div
          className="h-full w-full"
          style={{
            background:
              "linear-gradient(90deg, var(--color-accent) 0%, var(--color-accent-600) 40%, var(--color-accent) 80%)",
            backgroundSize: "200% 100%",
            animation: "moo-shimmer 1.4s linear infinite",
          }}
        />
      </div>
    );
  }

  return (
    <div className={track}>
      <div
        className="h-full transition-[width] duration-500"
        style={{
          width: `${Math.max(2, pct)}%`,
          background: job.status === "queued" ? "var(--color-divider)" : "var(--color-accent)",
        }}
      />
    </div>
  );
}
