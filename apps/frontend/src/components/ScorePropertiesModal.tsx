"use client";

import { useCallback, useEffect, useState } from "react";
import type { ScoreResult } from "@/lib/types";
import type { ScorePropertiesDraft } from "@/lib/scoreEdit";
import {
  KEY_SIGNATURE_OPTIONS,
  formatKeyOption,
  keySignatureFromHeader,
} from "@/lib/keySignatures";
import { editableVoiceIndices, isPercussionVoice } from "@/lib/voiceAbbr";

type Props = {
  open: boolean;
  score: ScoreResult;
  onClose: () => void;
  onApply: (draft: ScorePropertiesDraft, keyId: string) => void;
};

function draftFromScore(score: ScoreResult): ScorePropertiesDraft {
  const key = keySignatureFromHeader(score.header, score.voices[0]?.model.fifths);
  return {
    title: score.header.title || "",
    composer: score.header.composer || "",
    work: score.header.work || "",
    keyId: key.id,
    voices: score.voices
      .map((v, index) => ({ index, name: v.name, deleted: false }))
      .filter((_, index) => !isPercussionVoice(score.voices[index]!)),
  };
}

export function ScorePropertiesModal({ open, score, onClose, onApply }: Props) {
  const [draft, setDraft] = useState<ScorePropertiesDraft>(() => draftFromScore(score));

  useEffect(() => {
    if (open) setDraft(draftFromScore(score));
  }, [open, score]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, handleKeyDown]);

  if (!open) return null;

  const editableCount = draft.voices.filter((v) => !v.deleted).length;
  const canDelete = editableCount > 1;

  const requestDelete = (index: number) => {
    if (!canDelete) return;
    if (!window.confirm("Supprimer cette portée et toutes ses notes ?")) return;
    setDraft((d) => ({
      ...d,
      voices: d.voices.map((v) => (v.index === index ? { ...v, deleted: true } : v)),
    }));
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 print:hidden"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="score-properties-title"
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-stone-200 bg-[#fffcf5] shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-stone-200 px-5 py-4">
          <h2 id="score-properties-title" className="text-lg font-semibold text-stone-900">
            Propriétés de la partition
          </h2>
        </div>

        <div className="space-y-4 px-5 py-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-stone-700">
              Titre de la chanson
            </span>
            <input
              type="text"
              value={draft.title}
              onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
              className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-stone-700">Compositeur</span>
            <input
              type="text"
              value={draft.composer}
              onChange={(e) => setDraft((d) => ({ ...d, composer: e.target.value }))}
              className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-stone-700">Œuvre</span>
            <input
              type="text"
              value={draft.work}
              onChange={(e) => setDraft((d) => ({ ...d, work: e.target.value }))}
              placeholder="Op. 9, BWV 232…"
              className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-500 focus:outline-none"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-stone-700">Tonalité</span>
            <select
              value={draft.keyId}
              onChange={(e) => setDraft((d) => ({ ...d, keyId: e.target.value }))}
              className="w-full rounded-md border border-stone-300 px-3 py-2 font-mono text-sm focus:border-stone-500 focus:outline-none"
            >
              {KEY_SIGNATURE_OPTIONS.map((k) => (
                <option key={k.id} value={k.id}>
                  {formatKeyOption(k)}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-stone-500">
              Mineur la-based : le Doh reste celui de la relative majeure.
            </p>
          </label>

          <fieldset>
            <legend className="mb-2 text-sm font-medium text-stone-700">Portées</legend>
            <ul className="space-y-2">
              {draft.voices.map((row, displayIdx) => {
                if (row.deleted) return null;
                return (
                  <li key={row.index} className="flex items-center gap-2">
                    <span className="w-16 shrink-0 text-xs text-stone-500">
                      Portée {displayIdx + 1}
                    </span>
                    <input
                      type="text"
                      value={row.name}
                      onChange={(e) =>
                        setDraft((d) => ({
                          ...d,
                          voices: d.voices.map((v) =>
                            v.index === row.index ? { ...v, name: e.target.value } : v,
                          ),
                        }))
                      }
                      className="min-w-0 flex-1 rounded-md border border-stone-300 px-3 py-1.5 text-sm focus:border-stone-500 focus:outline-none"
                    />
                    <button
                      type="button"
                      disabled={!canDelete}
                      title="Supprimer la portée"
                      aria-label={`Supprimer ${row.name}`}
                      onClick={() => requestDelete(row.index)}
                      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-stone-400 hover:bg-red-50 hover:text-red-700 disabled:opacity-30"
                    >
                      <svg
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        aria-hidden
                      >
                        <path d="M3 6h18" />
                        <path d="M8 6V4h8v2" />
                        <path d="M19 6l-1 14H6L5 6" />
                        <path d="M10 11v6M14 11v6" />
                      </svg>
                    </button>
                  </li>
                );
              })}
            </ul>
            {editableVoiceIndices(score.voices).length < score.voices.length && (
              <p className="mt-2 text-xs text-stone-500">
                Les portées de percussion ne sont pas modifiables ici.
              </p>
            )}
          </fieldset>
        </div>

        <div className="flex justify-end gap-2 border-t border-stone-200 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-stone-300 px-4 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-100"
          >
            Annuler
          </button>
          <button
            type="button"
            disabled={!draft.title.trim()}
            onClick={() => onApply(draft, draft.keyId)}
            className="rounded-md bg-stone-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
          >
            Appliquer
          </button>
        </div>
      </div>
    </div>
  );
}
