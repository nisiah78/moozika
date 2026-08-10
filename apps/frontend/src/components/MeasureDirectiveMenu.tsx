"use client";

import { useEffect, useRef, useState } from "react";
import {
  DIRECTIVE_MENU,
  type DirectiveMenuId,
  type DirectivePayload,
} from "@/lib/measureDirectives";
import { TONIC_OPTIONS } from "@/lib/movableDo";

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
  const ref = useRef<HTMLDivElement>(null);
  const [form, setForm] = useState<DirectiveMenuId | null>(null);
  const [bpm, setBpm] = useState(String(defaultBpm));
  const [beats, setBeats] = useState(String(defaultBeats));
  const [beatType, setBeatType] = useState(String(defaultBeatType));
  const [tonic, setTonic] = useState(defaultTonic);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const left = Math.min(x, typeof window !== "undefined" ? window.innerWidth - 220 : x);
  const top = Math.min(y, typeof window !== "undefined" ? window.innerHeight - 320 : y);

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
    <div
      ref={ref}
      className="fixed z-[90] w-52 overflow-hidden rounded-md border border-stone-300 bg-white shadow-lg"
      style={{ left, top }}
      role="dialog"
      aria-label="Ajouter une directive de mesure"
    >
      {!form ? (
        <ul className="max-h-72 overflow-auto py-1 text-sm">
          {(["nav", "tempo", "meter", "key"] as const).map((group) => {
            const items = DIRECTIVE_MENU.filter((m) => m.group === group);
            if (!items.length) return null;
            const titles = {
              nav: "Navigation",
              tempo: "Tempo",
              meter: "Métrique",
              key: "Tonalité",
            };
            return (
              <li key={group}>
                <p className="px-3 pt-2 pb-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
                  {titles[group]}
                </p>
                {items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="block w-full px-3 py-1.5 text-left hover:bg-stone-100"
                    onClick={() => {
                      if (item.needsForm) setForm(item.id);
                      else onSelect({ id: item.id } as DirectivePayload);
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="space-y-2 p-3 text-sm">
          <button
            type="button"
            className="text-xs text-stone-500 hover:text-stone-800"
            onClick={() => setForm(null)}
          >
            ← Retour
          </button>
          {form === "metronome" && (
            <label className="block">
              <span className="text-xs text-stone-500">BPM (noire)</span>
              <input
                type="number"
                min={1}
                max={300}
                value={bpm}
                onChange={(e) => setBpm(e.target.value)}
                className="mt-0.5 w-full rounded border border-stone-300 px-2 py-1"
                autoFocus
              />
            </label>
          )}
          {form === "time" && (
            <div className="flex items-end gap-2">
              <label className="flex-1">
                <span className="text-xs text-stone-500">Temps</span>
                <input
                  type="number"
                  min={1}
                  max={16}
                  value={beats}
                  onChange={(e) => setBeats(e.target.value)}
                  className="mt-0.5 w-full rounded border border-stone-300 px-2 py-1"
                  autoFocus
                />
              </label>
              <span className="pb-1.5 text-stone-400">/</span>
              <label className="flex-1">
                <span className="text-xs text-stone-500">Unité</span>
                <select
                  value={beatType}
                  onChange={(e) => setBeatType(e.target.value)}
                  className="mt-0.5 w-full rounded border border-stone-300 px-2 py-1"
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
            <label className="block">
              <span className="text-xs text-stone-500">Doh =</span>
              <select
                value={tonic}
                onChange={(e) => setTonic(e.target.value)}
                className="mt-0.5 w-full rounded border border-stone-300 px-2 py-1"
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
          <button
            type="button"
            className="w-full rounded-md bg-stone-900 px-2 py-1.5 text-xs font-medium text-white hover:bg-stone-800"
            onClick={submitForm}
          >
            Appliquer
          </button>
        </div>
      )}
    </div>
  );
}
