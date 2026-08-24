"use client";

import { useState } from "react";
import { Popover, PopoverTitle } from "@/components/Popover";
import { DIRECTIVE_MENU, type DirectiveMenuId, type DirectivePayload } from "@/lib/measureDirectives";
import { TONIC_OPTIONS } from "@/lib/movableDo";

const GROUP_TITLES = {
  nav: "Navigation",
  tempo: "Tempo",
  meter: "Métrique",
  key: "Tonalité",
} as const;

export function MeasureDirectiveMenu({
  x,
  y,
  defaultBpm = 120,
  defaultBeats = 4,
  defaultBeatType = 4,
  defaultTonic = "C",
  onSelect,
  onClose,
}: {
  x: number;
  y: number;
  defaultBpm?: number;
  defaultBeats?: number;
  defaultBeatType?: number;
  defaultTonic?: string;
  onSelect: (payload: DirectivePayload) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<DirectiveMenuId | null>(null);
  const [bpm, setBpm] = useState(String(defaultBpm));
  const [beats, setBeats] = useState(String(defaultBeats));
  const [beatType, setBeatType] = useState(String(defaultBeatType));
  const [tonic, setTonic] = useState(defaultTonic);

  const submitForm = () => {
    if (form === "metronome") {
      const n = Number(bpm);
      if (!Number.isFinite(n) || n < 1) return;
      onSelect({ id: "metronome", bpm: n });
      return;
    }
    if (form === "time") {
      const b = Number(beats);
      const bt = Number(beatType);
      if (!Number.isFinite(b) || !Number.isFinite(bt) || b < 1 || bt < 1) return;
      onSelect({ id: "time", beats: b, beatType: bt });
      return;
    }
    if (form === "key") {
      onSelect({ id: "key", tonic });
    }
  };

  return (
    <Popover
      x={x}
      y={y}
      onClose={onClose}
      level={90}
      ariaLabel="Ajouter une directive de mesure"
      className="w-52"
    >
      {!form ? (
        <div className="max-h-72 overflow-auto pb-1 text-sm">
          {(["nav", "tempo", "meter", "key"] as const).map((group) => {
            const items = DIRECTIVE_MENU.filter((m) => m.group === group);
            if (!items.length) return null;
            return (
              <div key={group}>
                <PopoverTitle>{GROUP_TITLES[group]}</PopoverTitle>
                {items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="block w-full px-3 py-1.5 text-left hover:bg-surface"
                    onClick={() => {
                      if (item.needsForm) setForm(item.id);
                      else onSelect({ id: item.id } as DirectivePayload);
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-2 p-3 text-sm">
          <button
            type="button"
            className="text-xs opacity-60 hover:opacity-100"
            onClick={() => setForm(null)}
          >
            ← Retour
          </button>
          {form === "metronome" && (
            <label className="moo-field block">
              <span className="text-xs opacity-70">BPM (noire)</span>
              <input
                type="number"
                min={1}
                max={300}
                value={bpm}
                onChange={(e) => setBpm(e.target.value)}
                className="moo-input mt-0.5"
                autoFocus
              />
            </label>
          )}
          {form === "time" && (
            <div className="flex items-end gap-2">
              <label className="moo-field flex-1">
                <span className="text-xs opacity-70">Temps</span>
                <input
                  type="number"
                  min={1}
                  max={16}
                  value={beats}
                  onChange={(e) => setBeats(e.target.value)}
                  className="moo-input mt-0.5"
                  autoFocus
                />
              </label>
              <span className="pb-2 opacity-50">/</span>
              <label className="moo-field flex-1">
                <span className="text-xs opacity-70">Unité</span>
                <select
                  value={beatType}
                  onChange={(e) => setBeatType(e.target.value)}
                  className="moo-input mt-0.5"
                >
                  {[1, 2, 4, 8, 16].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}
          {form === "key" && (
            <label className="moo-field block">
              <span className="text-xs opacity-70">Doh =</span>
              <select
                value={tonic}
                onChange={(e) => setTonic(e.target.value)}
                className="moo-input mt-0.5"
                autoFocus
              >
                {TONIC_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button type="button" className="moo-btn moo-btn--primary w-full" onClick={submitForm}>
            Appliquer
          </button>
        </div>
      )}
    </Popover>
  );
}
