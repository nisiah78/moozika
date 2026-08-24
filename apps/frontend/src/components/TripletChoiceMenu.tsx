"use client";

import { Popover, PopoverTitle } from "@/components/Popover";

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
  return (
    <Popover
      x={x}
      y={y}
      onClose={onClose}
      level={95}
      ariaLabel={`Triolet ${voiceName} mesure ${measureNumber} temps ${beatNumber}`}
      className="w-60"
    >
      <PopoverTitle>
        {voiceName} · m.{measureNumber} t.{beatNumber}
      </PopoverTitle>
      <div className="py-1 text-sm">
        {(
          [
            { span: 1 as const, label: "1 temps", hint: "3 notes collées (ex. drm)" },
            {
              span: 2 as const,
              label: "2 temps",
              hint: "3 notes collées sur deux temps (ex. drm, sans « : »)",
            },
          ]
        ).map((o) => (
          <button
            key={o.span}
            type="button"
            className="block w-full px-3 py-2 text-left hover:bg-surface"
            onClick={() => onSelect(o.span)}
          >
            Triolet sur <strong>{o.label}</strong>
            <span className="mt-0.5 block text-xs opacity-60">{o.hint}</span>
          </button>
        ))}
      </div>
    </Popover>
  );
}
