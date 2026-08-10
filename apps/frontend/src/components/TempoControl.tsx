"use client";

import {
  TEMPO_BEAT_OPTIONS,
  tempoFromOptionId,
  tempoOptionId,
  type TempoSettings,
} from "@/lib/tempo";

export function TempoControl({
  value,
  onChange,
  className = "",
  compact = false,
}: {
  value: TempoSettings;
  onChange: (next: TempoSettings) => void;
  className?: string;
  /** Variante compacte pour la barre d'outils (mode portée). */
  compact?: boolean;
}) {
  const optionId = tempoOptionId(value);

  const setBpm = (raw: string) => {
    const n = parseInt(raw, 10);
    if (!Number.isFinite(n)) return;
    onChange({ ...value, bpm: Math.min(300, Math.max(1, n)) });
  };

  return (
    <div
      className={`tempo-control ${compact ? "tempo-control--compact" : ""} ${className}`.trim()}
      role="group"
      aria-label="Tempo"
    >
      <label className="tempo-control__note">
        <span className="sr-only">Note de repère</span>
        <select
          className="tempo-control__select"
          value={optionId}
          onChange={(e) => onChange(tempoFromOptionId(e.target.value, value.bpm))}
          aria-label="Note de repère du tempo"
        >
          {TEMPO_BEAT_OPTIONS.map((o) => (
            <option key={o.id} value={o.id}>
              {o.symbol} {o.label}
            </option>
          ))}
        </select>
        <span className="tempo-control__symbol" aria-hidden>
          {TEMPO_BEAT_OPTIONS.find((o) => o.id === optionId)?.symbol ?? "♩"}
        </span>
      </label>

      <span className="tempo-control__eq" aria-hidden>
        =
      </span>

      <label className="tempo-control__bpm">
        <span className="sr-only">Tempo en battements par minute</span>
        <input
          type="number"
          className="tempo-control__input"
          min={20}
          max={300}
          step={1}
          value={value.bpm}
          onChange={(e) => setBpm(e.target.value)}
          aria-label="Battements par minute"
        />
      </label>
    </div>
  );
}
