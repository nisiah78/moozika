"use client";

import { useEffect, useRef } from "react";

export function TripletChoiceMenu({
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
  onSelect: (spanBeats: 1 | 2) => void;
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

  const left = Math.min(x, typeof window !== "undefined" ? window.innerWidth - 260 : x);
  const top = Math.min(y, typeof window !== "undefined" ? window.innerHeight - 200 : y);

  return (
    <div
      ref={ref}
      className="fixed z-[95] w-60 overflow-hidden rounded-md border border-stone-300 bg-white shadow-lg"
      style={{ left, top }}
      role="dialog"
      aria-label={`Triolet ${voiceName} mesure ${measureNumber} temps ${beatNumber}`}
    >
      <p className="border-b border-stone-100 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
        {voiceName} · m.{measureNumber} t.{beatNumber}
      </p>
      <ul className="py-1 text-sm">
        <li>
          <button
            type="button"
            className="block w-full px-3 py-2 text-left hover:bg-stone-100"
            onClick={() => onSelect(1)}
          >
            Triolet sur <strong>1 temps</strong>
            <span className="mt-0.5 block text-xs font-normal text-stone-500">
              3 notes collées (ex. drm)
            </span>
          </button>
        </li>
        <li>
          <button
            type="button"
            className="block w-full px-3 py-2 text-left hover:bg-stone-100"
            onClick={() => onSelect(2)}
          >
            Triolet sur <strong>2 temps</strong>
            <span className="mt-0.5 block text-xs font-normal text-stone-500">
              3 notes collées sur deux temps (ex. drm, sans « : »)
            </span>
          </button>
        </li>
      </ul>
    </div>
  );
}
