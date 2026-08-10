"use client";

import { useEffect, useRef } from "react";
import {
  DYNAMIC_LEVELS,
  type BeatAnnotationPayload,
} from "@/lib/beatAnnotations";

export function BeatAnnotationMenu({
  x,
  y,
  voiceName,
  measureNumber,
  beatNumber,
  onSelect,
  onClose,
}: {
  x: number;
  y: number;
  voiceName: string;
  measureNumber: number;
  beatNumber: number;
  onSelect: (payload: BeatAnnotationPayload) => void;
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

  const left = Math.min(x, typeof window !== "undefined" ? window.innerWidth - 240 : x);
  const top = Math.min(y, typeof window !== "undefined" ? window.innerHeight - 360 : y);

  return (
    <div
      ref={ref}
      className="fixed z-[95] w-56 overflow-hidden rounded-md border border-stone-300 bg-white shadow-lg"
      style={{ left, top }}
      role="dialog"
      aria-label={`Annotation ${voiceName} mesure ${measureNumber} temps ${beatNumber}`}
    >
      <p className="border-b border-stone-100 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
        {voiceName} · m.{measureNumber} t.{beatNumber}
      </p>
      <ul className="max-h-80 overflow-auto py-1 text-sm">
        <li>
          <p className="px-3 pt-2 pb-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
            Nuances
          </p>
          <div className="grid grid-cols-4 gap-0.5 px-2 pb-1">
            {DYNAMIC_LEVELS.map((level) => (
              <button
                key={level}
                type="button"
                className="rounded px-1 py-1.5 text-center text-xs font-semibold hover:bg-stone-100"
                onClick={() => onSelect({ id: "dynamics", level })}
              >
                {level}
              </button>
            ))}
          </div>
        </li>
        <li>
          <p className="px-3 pt-2 pb-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
            Soufflets
          </p>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-stone-100"
            onClick={() => onSelect({ id: "crescendo" })}
          >
            Crescendo ⟨
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-stone-100"
            onClick={() => onSelect({ id: "diminuendo" })}
          >
            Diminuendo ⟩
          </button>
          <button
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-stone-100"
            onClick={() => onSelect({ id: "wedge-stop" })}
          >
            Fin de soufflet
          </button>
        </li>
      </ul>
    </div>
  );
}
