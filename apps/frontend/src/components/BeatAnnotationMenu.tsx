"use client";

import { Popover, PopoverTitle } from "@/components/Popover";
import { DYNAMIC_LEVELS, type BeatAnnotationPayload } from "@/lib/beatAnnotations";

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
  return (
    <Popover
      x={x}
      y={y}
      onClose={onClose}
      level={95}
      ariaLabel={`Annotation ${voiceName} mesure ${measureNumber} temps ${beatNumber}`}
      className="w-56"
    >
      <PopoverTitle>
        {voiceName} · m.{measureNumber} t.{beatNumber}
      </PopoverTitle>
      <div className="max-h-80 overflow-auto pb-1 text-sm">
        <PopoverTitle>Nuances</PopoverTitle>
        <div className="grid grid-cols-4 gap-0.5 px-2 py-1">
          {DYNAMIC_LEVELS.map((level) => (
            <button
              key={level}
              type="button"
              // Les nuances sont des valeurs musicales : mono + italique, comme
              // à l'impression et comme dans la maquette.
              className="border border-divider px-1 py-1.5 text-center font-mono text-xs font-semibold italic hover:border-accent hover:text-accent"
              onClick={() => onSelect({ id: "dynamics", level })}
            >
              {level}
            </button>
          ))}
        </div>
        <PopoverTitle>Soufflets</PopoverTitle>
        {(
          [
            { id: "crescendo" as const, label: "Crescendo ⟨" },
            { id: "diminuendo" as const, label: "Diminuendo ⟩" },
            { id: "wedge-stop" as const, label: "Fin de soufflet" },
          ]
        ).map((w) => (
          <button
            key={w.id}
            type="button"
            className="block w-full px-3 py-1.5 text-left hover:bg-surface"
            onClick={() => onSelect({ id: w.id })}
          >
            {w.label}
          </button>
        ))}
      </div>
    </Popover>
  );
}
