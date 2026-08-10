"use client";

import { useEffect, useRef, useState } from "react";
import type { TempoSettings } from "@/lib/tempo";
import type { ScoreResult } from "@/lib/types";
import { getPianoPlayer, type PlayState, type PlaybackPosition } from "@/lib/playback";

// ──────────────────────────────────────────────────────────────────────────────
// Sélecteur de voix (dropdown + checkboxes)
// ──────────────────────────────────────────────────────────────────────────────

function VoiceSelector({
  voices,
  enabled,
  onChange,
  disabled,
}: {
  voices: string[];
  enabled: Set<string>;
  onChange: (next: Set<string>) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Ferme au clic extérieur.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Reset si `voices` change (nouvelle partition).
  useEffect(() => {
    onChange(new Set(voices));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voices.join(",")]);

  const allEnabled = voices.length > 0 && voices.every((v) => enabled.has(v));
  const noneEnabled = enabled.size === 0;

  const label = noneEnabled
    ? "Aucune voix"
    : allEnabled
      ? "Toutes les voix"
      : `${enabled.size} / ${voices.length} voix`;

  const toggleVoice = (name: string) => {
    const next = new Set(enabled);
    if (next.has(name)) {
      // Garde toujours au moins une voix cochée.
      if (next.size > 1) next.delete(name);
    } else {
      next.add(name);
    }
    onChange(next);
  };

  const toggleAll = () => {
    onChange(allEnabled ? new Set([voices[0]]) : new Set(voices));
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        className={`
          inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium
          transition-colors
          ${open
            ? "border-gray-400 bg-gray-100 text-gray-900"
            : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
          }
          disabled:opacity-50 disabled:cursor-not-allowed
        `}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <MusicIcon />
        <span>{label}</span>
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div
          role="listbox"
          aria-multiselectable
          className="absolute right-0 top-full z-30 mt-1 min-w-[11rem] overflow-hidden rounded-md border border-gray-200 bg-white py-1 shadow-lg"
        >
          {/* Tout cocher / décocher */}
          <label className="flex cursor-pointer items-center gap-2.5 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50 select-none">
            <input
              type="checkbox"
              checked={allEnabled}
              onChange={toggleAll}
              className="h-3.5 w-3.5 rounded accent-gray-700"
            />
            <span className="italic">Toutes</span>
          </label>

          <div className="mx-3 my-1 border-t border-gray-100" />

          {voices.map((name) => (
            <label
              key={name}
              className="flex cursor-pointer items-center gap-2.5 px-3 py-1.5 text-sm text-gray-800 hover:bg-gray-50 select-none"
            >
              <input
                type="checkbox"
                checked={enabled.has(name)}
                onChange={() => toggleVoice(name)}
                className="h-3.5 w-3.5 rounded accent-gray-700"
              />
              <span>{name}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Contrôles de lecture
// ──────────────────────────────────────────────────────────────────────────────

export function PlaybackControls({
  result,
  tempo,
  onBeforePlay,
  onBeatChange,
}: {
  result: ScoreResult;
  tempo: TempoSettings;
  /** Commit les éditions sol-fa locales ; peut renvoyer le score à jour. */
  onBeforePlay?: () => Promise<ScoreResult | void>;
  /** Temps en cours de lecture (mesure + pulsation) ou null quand ça cesse. */
  onBeatChange?: (pos: PlaybackPosition | null) => void;
}) {
  const [state, setState] = useState<PlayState>("idle");
  const [error, setError] = useState<string | null>(null);

  const voiceNames = result.voices.map((v) => v.name);
  const [enabledVoices, setEnabledVoices] = useState<Set<string>>(
    () => new Set(voiceNames),
  );

  // Stoppe + réinitialise la sélection si la partition change.
  useEffect(() => {
    getPianoPlayer().stop();
    setState("idle");
    setEnabledVoices(new Set(result.voices.map((v) => v.name)));
  }, [result]);

  const onPlay = async () => {
    setError(null);
    setState("loading");
    try {
      const flushed = onBeforePlay ? await onBeforePlay() : undefined;
      await getPianoPlayer().play(
        flushed || result,
        () => setState("stopped"),
        enabledVoices,
        tempo,
        onBeatChange,
      );
      setState("playing");
    } catch (e) {
      setState("idle");
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onStop = () => {
    getPianoPlayer().stop();
    setState("stopped");
  };

  const busy = state === "loading";
  const playing = state === "playing";

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Sélecteur de voix — caché s'il n'y a qu'une seule voix */}
      {voiceNames.length > 1 && (
        <VoiceSelector
          voices={voiceNames}
          enabled={enabledVoices}
          onChange={setEnabledVoices}
          disabled={playing || busy}
        />
      )}

      {/* Bouton lecture / stop */}
      {playing ? (
        <button
          type="button"
          onClick={onStop}
          className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-800 hover:bg-gray-50"
          aria-label="Arrêter la lecture"
        >
          <StopIcon />
          Stop
        </button>
      ) : (
        <button
          type="button"
          onClick={onPlay}
          disabled={busy || enabledVoices.size === 0}
          className="inline-flex items-center gap-1.5 rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60"
          aria-label="Lire au piano"
        >
          <PlayIcon />
          {busy ? "Chargement…" : "Lecture"}
        </button>
      )}

      {error && (
        <span className="text-xs text-red-600">{error}</span>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Icônes SVG
// ──────────────────────────────────────────────────────────────────────────────

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <rect x="6" y="6" width="12" height="12" rx="1" />
    </svg>
  );
}

function MusicIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={`transition-transform duration-150 ${open ? "rotate-180" : ""}`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}
