"use client";

import { useEffect, useState } from "react";
import type { ScoreResult } from "@/lib/types";
import type { ScorePropertiesDraft } from "@/lib/scoreEdit";
import { KEY_SIGNATURE_OPTIONS, formatKeyOption, keySignatureFromHeader } from "@/lib/keySignatures";
import { editableVoiceIndices, isPercussionVoice } from "@/lib/voiceAbbr";
import { Drawer } from "@/components/Drawer";
import { IconTrash } from "@/components/icons";

/**
 * Propriétés de la partition, en drawer droit (le design remplace la modale
 * centrée par un panneau glissant). La logique de brouillon est inchangée :
 * seul le contenant et le style bougent.
 *
 * « Portées » est conservé pour désigner les portées elles-mêmes — la maquette
 * fait la même distinction (« Portées / voix » ici, « Solfège » pour la notation).
 */
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

export function ScorePropertiesDrawer({
  score,
  onClose,
  onApply,
}: {
  score: ScoreResult;
  onClose: () => void;
  onApply: (draft: ScorePropertiesDraft, keyId: string) => void;
}) {
  const [draft, setDraft] = useState<ScorePropertiesDraft>(() => draftFromScore(score));

  useEffect(() => setDraft(draftFromScore(score)), [score]);

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
    <Drawer
      title="Propriétés de la partition"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="moo-btn moo-btn--secondary">
            Annuler
          </button>
          <button
            type="button"
            disabled={!draft.title.trim()}
            onClick={() => onApply(draft, draft.keyId)}
            className="moo-btn moo-btn--primary"
          >
            Appliquer
          </button>
        </>
      }
    >
      <div className="moo-field">
        <label htmlFor="prop-title">Titre de la chanson</label>
        <input
          id="prop-title"
          className="moo-input"
          value={draft.title}
          onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
        />
      </div>

      <div className="moo-field">
        <label htmlFor="prop-composer">Compositeur</label>
        <input
          id="prop-composer"
          className="moo-input"
          placeholder="Nom du compositeur"
          value={draft.composer}
          onChange={(e) => setDraft((d) => ({ ...d, composer: e.target.value }))}
        />
      </div>

      <div className="moo-field">
        <label htmlFor="prop-work">Œuvre</label>
        <input
          id="prop-work"
          className="moo-input"
          placeholder="Op. 9, BWV 232…"
          value={draft.work}
          onChange={(e) => setDraft((d) => ({ ...d, work: e.target.value }))}
        />
      </div>

      <div className="moo-field">
        <label htmlFor="prop-key">Tonalité</label>
        <select
          id="prop-key"
          className="moo-input font-mono"
          value={draft.keyId}
          onChange={(e) => setDraft((d) => ({ ...d, keyId: e.target.value }))}
        >
          {KEY_SIGNATURE_OPTIONS.map((k) => (
            <option key={k.id} value={k.id}>
              {formatKeyOption(k)}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs opacity-60">
          Mineur la-based : le Doh reste celui de la relative majeure.
        </p>
      </div>

      <div>
        <div className="mb-2 text-xs opacity-80">Portées / voix</div>
        <div className="flex flex-col gap-1.5">
          {draft.voices.map((row, displayIdx) => {
            if (row.deleted) return null;
            return (
              <div
                key={row.index}
                className="flex items-center gap-2.5 border border-divider bg-surface-2 p-1.5"
              >
                <span className="w-5 flex-none font-mono text-[11px] opacity-55">
                  {displayIdx + 1}
                </span>
                <input
                  className="moo-input min-h-8 flex-1"
                  value={row.name}
                  aria-label={`Nom de la portée ${displayIdx + 1}`}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      voices: d.voices.map((v) =>
                        v.index === row.index ? { ...v, name: e.target.value } : v,
                      ),
                    }))
                  }
                />
                <button
                  type="button"
                  disabled={!canDelete}
                  title={canDelete ? "Supprimer la portée" : "Au moins une portée doit rester"}
                  aria-label={`Supprimer ${row.name}`}
                  onClick={() => requestDelete(row.index)}
                  className="grid h-[34px] w-[34px] flex-none place-items-center border border-divider hover:border-[var(--err)] hover:text-[var(--err)] disabled:opacity-30"
                >
                  <IconTrash size={15} />
                </button>
              </div>
            );
          })}
        </div>
        {editableVoiceIndices(score.voices).length < score.voices.length && (
          <p className="mt-2 text-xs opacity-60">
            Les portées de percussion ne sont pas modifiables ici.
          </p>
        )}
      </div>
    </Drawer>
  );
}
