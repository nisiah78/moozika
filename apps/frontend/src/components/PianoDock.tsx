"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { TempoSettings } from "@/lib/tempo";
import { formatTempoLabel } from "@/lib/tempo";
import type { ScoreResult } from "@/lib/types";
import { getPianoPlayer, type PlayState, type PlaybackPosition } from "@/lib/playback";
import { BLACK_KEYS, WHITE_KEYS } from "@/lib/pianoKeys";
import { voiceAbbr } from "@/lib/voiceAbbr";
import { IconClose, IconPause, IconPlay } from "@/components/icons";

/**
 * Dock de lecture : transport, sélection des voix par chips, avancement, et
 * clavier cliquable.
 *
 * Règle non négociable de ce composant : RIEN qui se produise par pulsation ne
 * passe par un `setState`. L'avancement est écrit directement dans le style du
 * nœud via une ref — un rendu React 60 fois par seconde saturerait le thread
 * principal et ferait décrocher l'ordonnanceur de Tone (notes en retard, notes
 * coupées, surlignage désynchronisé).
 */
export function PianoDock({
  result,
  tempo,
  onBeforePlay,
  onBeatChange,
  onClose,
}: {
  result: ScoreResult;
  tempo: TempoSettings;
  /** Commit les éditions sol-fa locales ; peut renvoyer le score à jour. */
  onBeforePlay?: () => Promise<ScoreResult | void>;
  /** Temps en cours de lecture (mesure + pulsation) ou null quand ça cesse. */
  onBeatChange?: (pos: PlaybackPosition | null) => void;
  onClose: () => void;
}) {
  const [state, setState] = useState<PlayState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [keysReady, setKeysReady] = useState(() => getPianoPlayer().isLoaded());
  const [loadingKeys, setLoadingKeys] = useState(false);
  const progressRef = useRef<HTMLDivElement>(null);

  const voiceNames = result.voices.map((v) => v.name);
  const [enabled, setEnabled] = useState<Set<string>>(() => new Set(voiceNames));

  // Stoppe et réinitialise la sélection quand la partition change.
  useEffect(() => {
    getPianoPlayer().stop();
    setState("idle");
    setEnabled(new Set(result.voices.map((v) => v.name)));
  }, [result]);

  // Arrête la lecture au démontage : fermer le dock ne doit pas laisser le son
  // tourner sans aucun contrôle à l'écran.
  useEffect(() => () => getPianoPlayer().stop(), []);

  const setProgress = useCallback((ratio: number) => {
    // Écriture DOM directe — voir l'en-tête du composant.
    if (progressRef.current) progressRef.current.style.width = `${ratio * 100}%`;
  }, []);

  const onPlay = async () => {
    setError(null);
    setState("loading");
    try {
      const flushed = onBeforePlay ? await onBeforePlay() : undefined;
      await getPianoPlayer().play(
        flushed || result,
        () => {
          setState("stopped");
          setProgress(0);
        },
        enabled,
        tempo,
        onBeatChange,
        setProgress,
      );
      setState("playing");
      setKeysReady(true);
    } catch (e) {
      setState("idle");
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onStop = () => {
    getPianoPlayer().stop();
    setState("stopped");
    setProgress(0);
  };

  const playing = state === "playing";
  const busy = state === "loading";

  const allOn = voiceNames.length > 0 && voiceNames.every((v) => enabled.has(v));

  const toggleVoice = (name: string) => {
    const next = new Set(enabled);
    // Garde toujours au moins une voix : une lecture sans voix est un silence
    // que rien n'explique à l'écran.
    if (next.has(name)) {
      if (next.size > 1) next.delete(name);
    } else {
      next.add(name);
    }
    setEnabled(next);
  };

  /** Le clavier déclenche le sampler Salamander, pas un oscillateur : même
      timbre que la lecture. Premier appui = chargement (plusieurs Mo). */
  const hitKey = async (note: string) => {
    if (!keysReady) {
      setLoadingKeys(true);
      try {
        await getPianoPlayer().note(note);
        setKeysReady(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoadingKeys(false);
      }
      return;
    }
    void getPianoPlayer().note(note);
  };

  return (
    <div className="moo-dock print:hidden">
      <div className="flex flex-wrap items-center gap-4 border-b border-divider px-6 py-3">
        <button
          type="button"
          onClick={() => (playing ? onStop() : void onPlay())}
          disabled={busy || enabled.size === 0}
          className="moo-btn moo-btn--primary h-[42px] w-[42px] justify-center p-0"
          aria-label={playing ? "Arrêter la lecture" : "Lire au piano"}
          title={playing ? "Arrêter" : "Lire au piano"}
        >
          {playing ? <IconPause size={18} /> : <IconPlay size={18} />}
        </button>

        {voiceNames.length > 1 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-0.5 font-sans text-[13px] font-extrabold">Voix</span>
            <Chip
              label="Toutes"
              on={allOn}
              disabled={playing || busy}
              onClick={() => setEnabled(allOn ? new Set([voiceNames[0]]) : new Set(voiceNames))}
              title="Toutes les voix"
            />
            {voiceNames.map((name) => (
              <Chip
                key={name}
                label={voiceAbbr(name)}
                on={enabled.has(name)}
                disabled={playing || busy}
                onClick={() => toggleVoice(name)}
                title={name}
              />
            ))}
          </div>
        )}

        <div className="h-1 min-w-[80px] flex-1 overflow-hidden bg-surface-2">
          <div
            ref={progressRef}
            className="h-full bg-accent"
            style={{ width: 0, transition: "width .3s linear" }}
          />
        </div>

        <span className="font-mono text-xs opacity-70">{formatTempoLabel(tempo)}</span>

        <button
          type="button"
          onClick={onClose}
          aria-label="Fermer le lecteur"
          className="opacity-70 hover:opacity-100"
        >
          <IconClose size={18} />
        </button>
      </div>

      {(error || busy || loadingKeys) && (
        <div className="px-6 pt-2 text-[11px]" style={{ color: error ? "var(--err)" : undefined }}>
          {error ?? (loadingKeys ? "Chargement du piano…" : "Préparation de la lecture…")}
        </div>
      )}

      <div className="relative flex h-[130px] select-none px-6 pb-3.5">
        <div className="relative mt-2.5 flex flex-1">
          {WHITE_KEYS.map((k) => (
            <button
              key={k.note}
              type="button"
              onMouseDown={() => void hitKey(k.note)}
              tabIndex={-1}
              aria-label={`Note ${k.note}`}
              className="flex flex-1 items-end justify-center border border-r-0 pb-2 text-[10px] last:border-r hover:brightness-95"
              style={{ background: "var(--paper)", borderColor: "#2b2620", color: "#8a8172" }}
            >
              {k.label}
            </button>
          ))}
          {BLACK_KEYS.map((k) => (
            <button
              key={k.note}
              type="button"
              onMouseDown={() => void hitKey(k.note)}
              tabIndex={-1}
              aria-label={`Note ${k.note}`}
              className="absolute top-0 z-[3] h-[62%] w-[5.6%] border hover:bg-accent-700"
              style={{ left: `${k.left}%`, background: "#17130d", borderColor: "#000" }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function Chip({
  label,
  on,
  disabled,
  onClick,
  title,
}: {
  label: string;
  on: boolean;
  disabled?: boolean;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-pressed={on}
      className="h-7 min-w-[30px] border px-2.5 font-sans text-xs font-extrabold disabled:opacity-40"
      style={
        on
          ? { background: "var(--color-accent)", borderColor: "var(--color-accent)", color: "var(--color-bg)" }
          : { background: "transparent", borderColor: "var(--color-divider)", color: "var(--color-text)" }
      }
    >
      {label}
    </button>
  );
}
