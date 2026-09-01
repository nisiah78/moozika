"use client";

import { Popover, PopoverItem } from "@/components/Popover";
import { IconPlus, IconUpload } from "@/components/icons";

/** Dropdown du bouton « Nouvelle partition » : importer un fichier ou composer une partition vierge. */
export function NewScoreMenu({
  x,
  y,
  onImport,
  onCreate,
  onClose,
}: {
  x: number;
  y: number;
  onImport: () => void;
  onCreate: () => void;
  onClose: () => void;
}) {
  return (
    <Popover x={x} y={y} onClose={onClose} level={90} ariaLabel="Nouvelle partition" className="w-60">
      <div className="py-1 text-sm">
        <PopoverItem
          onClick={() => {
            onClose();
            onImport();
          }}
        >
          <span className="flex items-center gap-2">
            <IconUpload size={15} />
            Importer un fichier
          </span>
        </PopoverItem>
        <PopoverItem
          onClick={() => {
            onClose();
            onCreate();
          }}
        >
          <span className="flex items-center gap-2">
            <IconPlus size={15} />
            Créer une partition vierge
          </span>
        </PopoverItem>
      </div>
    </Popover>
  );
}
