"use client";

import { useEffect, useRef } from "react";
import { SOLFEGE_OPTIONS, type SolfegeOptionId } from "@/lib/staffPitch";
import {
  NOTE_VALUE_OPTIONS,
  noteValueLabel,
  type NoteValueType,
} from "@/lib/staffGlyphs";

export type NotePickerChoice =
  | { kind: "pitch"; id: SolfegeOptionId }
  | { kind: "duration"; type: NoteValueType; dots: number };

export function NotePicker({
  x,
  y,
  currentType,
  currentDots = 0,
  onSelect,
  onClose,
}: {
  x: number;
  y: number;
  currentType?: string;
  currentDots?: number;
  onSelect: (choice: NotePickerChoice) => void;
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

  const left = Math.min(x, typeof window !== "undefined" ? window.innerWidth - 200 : x);
  const top = Math.min(y, typeof window !== "undefined" ? window.innerHeight - 420 : y);

  return (
    <div
      ref={ref}
      className="fixed z-[80] max-h-[28rem] w-44 overflow-auto rounded-md border border-stone-300 bg-white py-1 shadow-lg"
      style={{ left, top }}
      role="listbox"
      aria-label="Choisir hauteur ou valeur"
    >
      <p className="px-3 pt-1.5 pb-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
        Hauteur
      </p>
      {SOLFEGE_OPTIONS.map((opt) => (
        <button
          key={opt.id}
          type="button"
          role="option"
          className="block w-full px-3 py-1.5 text-left text-sm hover:bg-stone-100"
          onClick={() => onSelect({ kind: "pitch", id: opt.id })}
        >
          {opt.label}
        </button>
      ))}
      <p className="mt-1 border-t border-stone-100 px-3 pt-1.5 pb-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
        Valeur
      </p>
      {NOTE_VALUE_OPTIONS.map((opt) => {
        const active =
          currentType === opt.type && (currentDots || 0) === opt.dots;
        return (
          <button
            key={`${opt.type}-${opt.dots}`}
            type="button"
            role="option"
            aria-selected={active}
            className={`block w-full px-3 py-1.5 text-left text-sm hover:bg-stone-100${
              active ? " bg-amber-50 font-medium text-stone-900" : ""
            }`}
            onClick={() =>
              onSelect({ kind: "duration", type: opt.type, dots: opt.dots })
            }
          >
            {noteValueLabel(opt.type, opt.dots)}
          </button>
        );
      })}
    </div>
  );
}
