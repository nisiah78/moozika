"use client";

import { Popover, PopoverItem, PopoverTitle } from "@/components/Popover";
import { SOLFEGE_OPTIONS, type SolfegeOptionId } from "@/lib/staffPitch";
import { NOTE_VALUE_OPTIONS, noteValueLabel, type NoteValueType } from "@/lib/staffGlyphs";

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
  return (
    <Popover
      x={x}
      y={y}
      onClose={onClose}
      level={95}
      role="listbox"
      ariaLabel="Choisir hauteur ou valeur"
      className="max-h-[28rem] w-44 overflow-auto py-1"
    >
      <PopoverTitle>Hauteur</PopoverTitle>
      {SOLFEGE_OPTIONS.map((opt) => (
        /* Aucune hauteur n'est « courante » : le picker ne reçoit que le type
           et les points de la note, pas sa hauteur. */
        <PopoverItem key={opt.id} role="option" onClick={() => onSelect({ kind: "pitch", id: opt.id })}>
          {opt.label}
        </PopoverItem>
      ))}
      <PopoverTitle>Valeur</PopoverTitle>
      {NOTE_VALUE_OPTIONS.map((opt) => (
        <PopoverItem
          key={`${opt.type}-${opt.dots}`}
          role="option"
          active={currentType === opt.type && (currentDots || 0) === opt.dots}
          onClick={() => onSelect({ kind: "duration", type: opt.type, dots: opt.dots })}
        >
          {noteValueLabel(opt.type, opt.dots)}
        </PopoverItem>
      ))}
    </Popover>
  );
}
