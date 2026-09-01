"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Drawer } from "@/components/Drawer";
import { useScoreDraft } from "@/components/ScoreDraftProvider";
import { useToasts } from "@/components/Toasts";
import { createBlankScore } from "@/lib/blankScore";
import { KEY_SIGNATURE_OPTIONS, formatKeyOption } from "@/lib/keySignatures";
import { ROUTES } from "@/lib/navigation";
import { IconTrash } from "@/components/icons";

const SATB_VOICES = ["Soprano", "Alto", "Tenor", "Bass"] as const;

/**
 * Métriques réellement acceptées par le parseur (`classify_meter`,
 * `apps/omr-service/app/solfa/rhythm.py`) : dénominateur 1 ou 2 n'existe dans
 * AUCUNE branche (toujours une `MeterError`), donc absents ici. Les listes de
 * temps par unité reprennent exactement les branches de cette fonction — pas
 * une plage arbitraire — pour garantir qu'une partition vierge se crée
 * toujours sans erreur de mètre.
 */
const BEAT_TYPES = [4, 8, 16] as const;

function beatsOptionsFor(beatType: number): number[] {
  if (beatType === 4) return [2, 3, 4, 5];
  if (beatType === 8) return [5, 6, 9, 10, 12, 15, 18, 21, 24];
  if (beatType === 16) return Array.from({ length: 24 }, (_, i) => i + 1);
  return [];
}

/**
 * Formulaire « Créer une partition » : construit une partition vierge (voir
 * `createBlankScore`) puis la dépose dans `ScoreDraftProvider`, exactement
 * comme le fait l'import MusicXML (`ImportScreen.uploadMusicXml`).
 */
export function CreateScoreDrawer({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { setDraft } = useScoreDraft();
  const { push } = useToasts();

  const [title, setTitle] = useState("");
  const [composer, setComposer] = useState("");
  const [keyId, setKeyId] = useState(KEY_SIGNATURE_OPTIONS[0]!.id);
  const [beatType, setBeatType] = useState<number>(4);
  const [beats, setBeats] = useState<number>(4);
  const [totalMeasures, setTotalMeasures] = useState("8");
  const [satb, setSatb] = useState<Record<(typeof SATB_VOICES)[number], boolean>>({
    Soprano: true,
    Alto: true,
    Tenor: true,
    Bass: true,
  });
  const [customVoices, setCustomVoices] = useState<string[]>([]);
  const [customVoiceInput, setCustomVoiceInput] = useState("");
  const [creating, setCreating] = useState(false);

  const voiceNames = [...SATB_VOICES.filter((v) => satb[v]), ...customVoices];
  const beatsOptions = beatsOptionsFor(beatType);
  const measuresN = Number(totalMeasures);
  const valid =
    title.trim().length > 0 &&
    voiceNames.length > 0 &&
    beatsOptions.includes(beats) &&
    Number.isFinite(measuresN) &&
    measuresN >= 1 &&
    measuresN <= 200;

  const changeBeatType = (next: number) => {
    setBeatType(next);
    const options = beatsOptionsFor(next);
    if (!options.includes(beats)) setBeats(options[0] ?? beats);
  };

  const addCustomVoice = () => {
    const name = customVoiceInput.trim();
    if (!name) return;
    if (voiceNames.some((v) => v.toLowerCase() === name.toLowerCase())) return;
    setCustomVoices((v) => [...v, name]);
    setCustomVoiceInput("");
  };

  const removeCustomVoice = (name: string) => {
    setCustomVoices((v) => v.filter((n) => n !== name));
  };

  const create = async () => {
    if (!valid) return;
    const keyEntry = KEY_SIGNATURE_OPTIONS.find((k) => k.id === keyId) ?? KEY_SIGNATURE_OPTIONS[0]!;
    setCreating(true);
    try {
      const result = await createBlankScore({
        title: title.trim(),
        composer: composer.trim(),
        keyEntry,
        beats,
        beatType,
        totalMeasures: measuresN,
        voiceNames,
      });
      setDraft(result);
      router.push(ROUTES.draft());
      onClose();
    } catch (e) {
      push({
        kind: "err",
        title: "Création impossible",
        body: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setCreating(false);
    }
  };

  return (
    <Drawer
      title="Créer une partition"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className="moo-btn moo-btn--secondary">
            Annuler
          </button>
          <button
            type="button"
            disabled={!valid || creating}
            onClick={() => void create()}
            className="moo-btn moo-btn--primary"
          >
            {creating ? "Création…" : "Créer"}
          </button>
        </>
      }
    >
      <div className="moo-field">
        <label htmlFor="new-title">Titre de la chanson</label>
        <input
          id="new-title"
          className="moo-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          autoFocus
        />
      </div>

      <div className="moo-field">
        <label htmlFor="new-composer">Compositeur</label>
        <input
          id="new-composer"
          className="moo-input"
          placeholder="Nom du compositeur"
          value={composer}
          onChange={(e) => setComposer(e.target.value)}
        />
      </div>

      <div className="moo-field">
        <label htmlFor="new-key">Tonalité</label>
        <select
          id="new-key"
          className="moo-input font-mono"
          value={keyId}
          onChange={(e) => setKeyId(e.target.value)}
        >
          {KEY_SIGNATURE_OPTIONS.map((k) => (
            <option key={k.id} value={k.id}>
              {formatKeyOption(k)}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-end gap-2">
        <label className="moo-field flex-1">
          <span className="text-xs opacity-70">Temps</span>
          <select
            className="moo-input mt-0.5"
            value={beats}
            onChange={(e) => setBeats(Number(e.target.value))}
          >
            {beatsOptions.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <span className="pb-2 opacity-50">/</span>
        <label className="moo-field flex-1">
          <span className="text-xs opacity-70">Unité</span>
          <select
            className="moo-input mt-0.5"
            value={beatType}
            onChange={(e) => changeBeatType(Number(e.target.value))}
          >
            {BEAT_TYPES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="moo-field">
        <label htmlFor="new-measures">Nombre de mesures</label>
        <input
          id="new-measures"
          type="number"
          min={1}
          max={200}
          className="moo-input"
          value={totalMeasures}
          onChange={(e) => setTotalMeasures(e.target.value)}
        />
      </div>

      <div>
        <div className="mb-2 text-xs opacity-80">Voix</div>
        <div className="flex flex-col gap-1.5">
          {SATB_VOICES.map((v) => (
            <label
              key={v}
              className="flex items-center gap-2.5 border border-divider bg-surface-2 p-1.5 text-sm"
            >
              <input
                type="checkbox"
                checked={satb[v]}
                onChange={(e) => setSatb((s) => ({ ...s, [v]: e.target.checked }))}
              />
              {v}
            </label>
          ))}
          {customVoices.map((name) => (
            <div
              key={name}
              className="flex items-center gap-2.5 border border-divider bg-surface-2 p-1.5 text-sm"
            >
              <span className="flex-1">{name}</span>
              <button
                type="button"
                aria-label={`Retirer ${name}`}
                onClick={() => removeCustomVoice(name)}
                className="grid h-[28px] w-[28px] flex-none place-items-center border border-divider hover:border-[var(--err)] hover:text-[var(--err)]"
              >
                <IconTrash size={13} />
              </button>
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center gap-2">
          <input
            className="moo-input flex-1"
            placeholder="Nom de voix (ex. Unisson)"
            value={customVoiceInput}
            onChange={(e) => setCustomVoiceInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCustomVoice();
              }
            }}
          />
          <button type="button" onClick={addCustomVoice} className="moo-btn moo-btn--secondary">
            Ajouter
          </button>
        </div>
        {voiceNames.length === 0 && (
          <p className="mt-2 text-xs opacity-60">Sélectionnez au moins une voix.</p>
        )}
      </div>
    </Drawer>
  );
}
