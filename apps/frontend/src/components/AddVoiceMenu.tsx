"use client";

import { Popover, PopoverTitle } from "@/components/Popover";

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
  return (
    <Popover x={x} y={y} onClose={onClose} level={90} ariaLabel="Ajouter une voix (divisi)" className="w-56">
      <PopoverTitle>Dédoubler une voix</PopoverTitle>
      <div className="max-h-64 overflow-auto py-1 text-sm">
        {voices.length === 0 ? (
          <p className="px-3 py-1.5 opacity-50">Aucune voix</p>
        ) : (
          voices.map((v) => (
            <button
              key={v.name}
              type="button"
              className="block w-full px-3 py-1.5 text-left hover:bg-surface"
              onClick={() => onSelect(v.name)}
            >
              {v.label}
            </button>
          ))
        )}
      </div>
    </Popover>
  );
}
