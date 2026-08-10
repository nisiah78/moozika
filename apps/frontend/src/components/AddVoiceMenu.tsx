"use client";

import { useEffect, useRef } from "react";

/**
 * Petit menu : choisir la voix à dédoubler (divisi) à partir de la mesure
 * cliquée. La voix choisie devient « V1 » et une « V2 » silencieuse est ajoutée.
 */
export function AddVoiceMenu({
  x,
  y,
  voices,
  onSelect,
  onClose,
}: {
  x: number;
  y: number;
  voices: { name: string; label: string }[];
  onSelect: (voiceName: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

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
  const top = Math.min(y, typeof window !== "undefined" ? window.innerHeight - 260 : y);

  return (
    <div
      ref={ref}
      className="fixed z-[90] w-56 overflow-hidden rounded-md border border-stone-300 bg-white shadow-lg"
      style={{ left, top }}
      role="dialog"
      aria-label="Ajouter une voix (divisi)"
    >
      <p className="px-3 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
        Dédoubler une voix
      </p>
      <ul className="max-h-64 overflow-auto pb-1 text-sm">
        {voices.length === 0 && (
          <li className="px-3 py-1.5 text-stone-400">Aucune voix</li>
        )}
        {voices.map((v) => (
          <li key={v.name}>
            <button
              type="button"
              className="block w-full px-3 py-1.5 text-left hover:bg-stone-100"
              onClick={() => onSelect(v.name)}
            >
              {v.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
