"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { TempoControl } from "@/components/TempoControl";
import { defaultTempoSettings, formatTempoLabel, resolveQuarterBpm, type TempoSettings } from "@/lib/tempo";
import type { ScoreResult } from "@/lib/types";
import type { PlaybackPosition } from "@/lib/playback";
import { ScoreViewer, type ScoreViewerHandle } from "@/components/ScoreViewer";
import { PianoDock } from "@/components/PianoDock";
import { applyBeatHighlight } from "@/lib/playbackHighlight";
import { followPlaybackScroll, resetPlaybackScroll } from "@/lib/playbackScroll";
import { addScoreVersion, createScore, deleteScore, modelToMusicxml } from "@/lib/scoresApi";
import { ScorePropertiesDrawer } from "@/components/ScorePropertiesDrawer";
import { applyScoreProperties, regenerateFromModels } from "@/lib/scoreEdit";
import { KEY_SIGNATURE_OPTIONS } from "@/lib/keySignatures";
import { buildSolfaMarkdown } from "@/lib/solfaMarkdown";
import { useToasts } from "@/components/Toasts";
import { useScoreDraft } from "@/components/ScoreDraftProvider";
import { ROUTES, type Notation } from "@/lib/navigation";
import { ToolRail, type RailItem } from "@/components/ToolRail";
import { Segmented } from "@/components/Segmented";
import {
  IconArrowLeft,
  IconCheck,
  IconDownload,
  IconGear,
  IconPencil,
  IconPlay,
  IconSave,
  IconTrash,
} from "@/components/icons";

export type Mode = "score" | "solfa";

/** Notation de la sidebar ⇄ mode d'éditeur. */
const MODE_OF: Record<Notation, Mode> = { solfa: "solfa", solfege: "score" };
const NOTATION_OF: Record<Mode, Notation> = { solfa: "solfa", score: "solfege" };

export function ScoreWorkspace({
  initialScore,
  initialScoreId,
  initialMode = "solfa",
}: {
  initialScore: ScoreResult;
  initialScoreId: string | null;
  initialMode?: Mode;
}) {
  const router = useRouter();
  const { push } = useToasts();
  const { setDraft } = useScoreDraft();

  const [result, setResult] = useState<ScoreResult>(initialScore);
  const [scoreId, setScoreId] = useState<string | null>(initialScoreId);
  const [mode, setMode] = useState<Mode>(initialMode);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [warnings, setWarnings] = useState<string[]>(initialScore.warnings ?? []);
  const [tempo, setTempo] = useState<TempoSettings>(() => defaultTempoSettings(initialScore));
  const [propertiesOpen, setPropertiesOpen] = useState(false);
  const [pianoOpen, setPianoOpen] = useState(false);
  /**
   * Mode édition. Le design suppose deux modes ; l'app était toujours éditable.
   * En lecture, la feuille reçoit `.moo-sheet--read` qui masque les affordances
   * d'édition — donc « Enregistrer » n'a pas à exister en lecture, il n'y a rien
   * à enregistrer. Une ébauche non enregistrée s'ouvre directement en édition :
   * elle a été importée pour être corrigée puis sauvée.
   */
  const [editing, setEditing] = useState(initialScoreId === null);

  const viewerRef = useRef<ScoreViewerHandle>(null);

  const title = result.header.title?.trim() || "Sans titre";

  const fail = useCallback(
    (e: unknown) =>
      push({ kind: "err", title: "Erreur", body: e instanceof Error ? e.message : String(e) }),
    [push],
  );

  /**
   * Surlignage + défilement, en une seule passe impérative.
   *
   * `applyBeatHighlight` a déjà résolu les nœuds du temps joué (querySelectorAll
   * + test de plage `data-pbf`/`data-pbt`) : le défilement les réutilise plutôt
   * que de refaire le même ciblage. Aucun `setState` ici — c'est la doctrine de
   * playbackHighlight.ts, un rendu React par pulsation ferait décrocher Tone.
   */
  const handleBeat = useCallback((pos: PlaybackPosition | null) => {
    const targets = applyBeatHighlight(pos);
    if (!pos) {
      resetPlaybackScroll();
      return;
    }
    followPlaybackScroll(targets, pos.measure);
  }, []);

  // Efface tout surlignage résiduel au démontage / changement de partition.
  useEffect(
    () => () => {
      applyBeatHighlight(null);
      resetPlaybackScroll();
    },
    [],
  );

  // Fermer le dock arrête aussi la lecture en cours côté surlignage.
  useEffect(() => {
    if (!pianoOpen) {
      applyBeatHighlight(null);
      resetPlaybackScroll();
    }
  }, [pianoOpen]);

  const saveScore = useCallback(async () => {
    setSaving(true);
    try {
      // Commit la cellule encore focalisée + brouillons avant de lire le score
      // (sinon Enregistrer sauvegarde l'état d'avant la correction).
      const flushed = mode === "solfa" ? await viewerRef.current?.flush() : null;
      const base = flushed ?? result;

      const name = base.header.title?.trim() || "Sans titre";
      const quarterBpm = Math.max(1, Math.round(resolveQuarterBpm(tempo)));
      const header = {
        ...base.header,
        title: name,
        tempo: tempo.bpm,
        tempoBeatUnit: tempo.beatUnit,
        tempoDotted: tempo.dotted,
      };
      let voices = base.voices.map((v) => ({ ...v, model: { ...v.model, tempo: quarterBpm } }));

      // Régénère le MusicXML pour y écrire le métronome (beat-unit=quarter).
      // Important : ne PAS reprendre `converted.voices[].notation` (to_solfa
      // backend) ni perdre `triplets` / `enterMeasure` — ça découpait les
      // triolets `drm` en `d : r | m` à l'enregistrement.
      const converted = await modelToMusicxml(voices.map((v) => v.model), {
        title: name,
        composer: header.composer,
        work: header.work,
      });
      const musicxml = converted.musicxml;
      if (!musicxml) throw new Error("MusicXML manquant — impossible d'enregistrer");
      if (converted.voices?.length) {
        voices = voices.map((v, i) => {
          const cv = converted.voices[i];
          if (!cv) return { ...v, model: { ...v.model, tempo: quarterBpm } };
          return {
            name: v.name,
            notation: v.notation,
            model: {
              ...cv.model,
              tempo: quarterBpm,
              triplets: v.model.triplets,
              enterMeasure: v.model.enterMeasure,
              partName: v.model.partName || cv.model.partName,
              dohOctave: v.model.dohOctave ?? cv.model.dohOctave,
              mode: v.model.mode ?? cv.model.mode,
            },
          };
        });
      }

      // `model` est le ScoreModel COMPLET (header + voix), pas la seule liste
      // de voix : c'est le pivot rechargé par detailToScoreResult à l'ouverture.
      const model = { header, voices, source: base.source, warnings: base.warnings };

      if (scoreId) {
        const res = await addScoreVersion(scoreId, {
          title: name,
          tonic: base.header.tonic,
          origin: "edit",
          musicxml,
          model,
        });
        push({ kind: "ok", title: "Partition enregistrée", body: `Version ${res.version}.` });
        setResult({ ...base, header, voices, musicxml, uploadedFile: undefined });
      } else {
        const sourceType =
          base.source === "audiveris" ? "staff" : base.source === "solfa_pdf" ? "solfa" : "musicxml";
        const res = await createScore({
          title: name,
          tonic: base.header.tonic,
          sourceType,
          origin: base.source === "audiveris" || base.source === "solfa_pdf" ? "omr" : "import",
          musicxml,
          model,
        });
        push({ kind: "ok", title: "Partition enregistrée", body: `Version ${res.version}.` });
        // L'ébauche a maintenant une identité : on libère le provider et on
        // remplace l'URL par la vraie, pour que la page devienne partageable.
        setResult({ ...base, header, voices, musicxml, uploadedFile: undefined });
        setScoreId(res.id);
        setDraft(null);
        router.replace(ROUTES.score(res.id));
      }
    } catch (e) {
      fail(e);
    } finally {
      setSaving(false);
    }
  }, [result, scoreId, mode, tempo, push, fail, setDraft, router]);

  const applyProperties = useCallback(
    async (draft: Parameters<typeof applyScoreProperties>[1], keyId: string) => {
      try {
        const flushed = mode === "solfa" ? await viewerRef.current?.flush() : null;
        const base = flushed ?? result;
        const keyEntry = KEY_SIGNATURE_OPTIONS.find((k) => k.id === keyId);
        if (!keyEntry) throw new Error("Tonalité inconnue");
        const { score: mutated, needsRegen } = applyScoreProperties(base, draft, keyEntry);
        const next = needsRegen ? await regenerateFromModels(mutated, mutated.voices) : mutated;
        setResult(next);
        setPropertiesOpen(false);
        push({ kind: "ok", title: "Propriétés appliquées" });
      } catch (e) {
        fail(e);
      }
    },
    [result, mode, fail, push],
  );

  const switchMode = useCallback(
    async (next: Mode) => {
      if (next === mode) return;
      if (mode === "solfa" && next === "score") {
        try {
          await viewerRef.current?.flush();
        } catch (e) {
          fail(e);
          return;
        }
      }
      setMode(next);
    },
    [mode, fail],
  );

  const flushSolfaEdits = useCallback(async () => {
    if (mode !== "solfa") return;
    return viewerRef.current?.flush();
  }, [mode]);

  const printScore = useCallback(async () => {
    // 1) Committer les corrections en cours (sol-fa) avant l'impression pour que
    //    le PDF reflète l'état édité et non l'affichage d'avant la frappe.
    try {
      await flushSolfaEdits();
    } catch {
      /* impression best-effort : on imprime l'état affiché même si un temps
         reste incomplet — l'utilisateur voit les cellules en erreur */
    }
    // 2) flushSolfaEdits() déclenche un re-parse via setState, et chaque cellule
    //    resynchronise son texte dans un useEffect qui ne s'exécute qu'au
    //    re-render SUIVANT. Deux frames garantissent que tous les commits React
    //    sont appliqués au DOM avant de capturer l'impression.
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
    window.print();
  }, [flushSolfaEdits]);

  const exportMarkdown = useCallback(async () => {
    try {
      const content =
        mode === "solfa" && viewerRef.current
          ? await viewerRef.current.exportMarkdown()
          : buildSolfaMarkdown(result, tempo);
      const baseName =
        title
          .toLowerCase()
          .normalize("NFD")
          .replace(/[̀-ͯ]/g, "")
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "") || "partition";
      const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${baseName}.md`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      fail(e);
    }
  }, [mode, result, tempo, title, fail]);

  const removeScore = useCallback(async () => {
    if (!scoreId) return;
    if (!window.confirm(`Supprimer « ${title} » ? Cette action est irréversible.`)) return;
    setDeleting(true);
    try {
      await deleteScore(scoreId);
      push({ kind: "ok", title: "Partition supprimée", body: `« ${title} »` });
      router.push(ROUTES.library(NOTATION_OF[mode]));
    } catch (e) {
      fail(e);
      setDeleting(false);
    }
  }, [scoreId, title, push, router, mode, fail]);

  const rail = useMemo<RailItem[]>(() => {
    if (!editing) {
      return [
        {
          key: "play",
          label: "Lecture",
          title: "Écouter au piano",
          icon: <IconPlay size={20} />,
          active: pianoOpen,
          onClick: () => setPianoOpen((v) => !v),
        },
        {
          key: "edit",
          label: "Éditer",
          title: "Éditer la partition",
          icon: <IconPencil size={20} />,
          onClick: () => setEditing(true),
        },
        {
          key: "export",
          label: "Export",
          title: "Exporter",
          icon: <IconDownload size={20} />,
          onClick: () => undefined,
          menu: [
            {
              key: "pdf",
              badge: "PDF",
              label: mode === "solfa" ? "Sol-fa fidèle" : "Solfège fidèle",
              onClick: () => void printScore(),
            },
            { key: "md", badge: "MD", label: "Markdown (texte)", onClick: () => void exportMarkdown() },
          ],
        },
        {
          key: "delete",
          label: "Suppr.",
          // Une ébauche non enregistrée n'existe pas côté serveur : rien à supprimer.
          title: scoreId ? "Supprimer la partition" : "Partition non enregistrée : rien à supprimer",
          icon: <IconTrash size={20} />,
          danger: true,
          disabled: !scoreId || deleting,
          onClick: () => void removeScore(),
        },
      ];
    }
    return [
      {
        key: "save",
        label: saving ? "…" : "Enreg.",
        title: "Enregistrer",
        icon: <IconSave size={20} />,
        disabled: saving || !result.musicxml,
        onClick: () => void saveScore(),
      },
      {
        key: "props",
        label: "Propr.",
        title: "Propriétés (titre, tonalité, voix)",
        icon: <IconGear size={20} />,
        onClick: () => setPropertiesOpen(true),
      },
      {
        key: "listen",
        label: "Écouter",
        icon: <IconPlay size={20} />,
        active: pianoOpen,
        onClick: () => setPianoOpen((v) => !v),
      },
      {
        key: "quit",
        label: "Terminer",
        title: "Terminer l'édition",
        icon: <IconCheck size={20} />,
        onClick: () => setEditing(false),
      },
    ];
  }, [editing, pianoOpen, mode, scoreId, deleting, saving, result.musicxml, printScore, exportMarkdown, removeScore, saveScore]);

  return (
    <div className="moo-workspace relative">
      {/* Barre supérieure. Sa bordure basse passe en accent en édition — c'est
          le repère du design pour dire « vous modifiez ». */}
      <div
        className="sticky top-0 z-[15] flex flex-wrap items-center gap-3.5 border-b-2 bg-surface px-5 py-3 print:hidden"
        style={{ borderColor: editing ? "var(--color-accent)" : "var(--color-divider)" }}
      >
        <Link
          href={ROUTES.library(NOTATION_OF[mode])}
          className="moo-btn moo-btn--secondary px-3 py-2"
          title="Retour à la bibliothèque"
          aria-label="Retour à la bibliothèque"
        >
          <IconArrowLeft size={15} />
        </Link>

        <div className="mr-auto min-w-0">
          <div className="flex items-center gap-2.5">
            <span className="truncate font-sans text-base font-extrabold">{title}</span>
            {editing && (
              <span
                className="inline-flex flex-none items-center gap-1.5 px-2 py-[3px] font-sans text-[10px] font-extrabold uppercase tracking-[0.06em]"
                style={{ background: "var(--color-accent)", color: "var(--color-bg)" }}
              >
                <IconPencil size={12} />
                Édition
              </span>
            )}
          </div>
          <div className="text-[11px] opacity-60">
            Doh = {result.header.tonic} · {result.header.timeSignature.beats}/
            {result.header.timeSignature.beatType} · {formatTempoLabel(tempo)} ·{" "}
            {result.voices.length} voix
            {scoreId ? ` · id ${scoreId.slice(0, 8)}…` : " · non enregistrée"}
          </div>
        </div>

        {/* Le tempo est un réglage d'écoute et d'impression : accessible dans
            les deux modes, contrairement aux affordances d'édition. */}
        <TempoControl value={tempo} onChange={setTempo} compact />

        <Segmented
          name="notation"
          value={NOTATION_OF[mode]}
          options={[
            { value: "solfa", label: "Sol-fa" },
            { value: "solfege", label: "Solfège" },
          ]}
          onChange={(n) => void switchMode(MODE_OF[n])}
        />
      </div>

      {warnings.length > 0 && (
        /* Les avertissements de transcription ne sont PAS des toasts : ils sont
           propres à la partition affichée et doivent rester consultables tant
           qu'elle est ouverte. */
        <div className="flex items-start justify-between gap-3 border-b border-divider bg-surface px-5 py-2 print:hidden">
          <ul className="text-[13px]" style={{ color: "var(--color-accent)" }}>
            {warnings.map((w) => (
              <li key={w}>⚠ {w}</li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => setWarnings([])}
            className="flex-none text-xs opacity-60 hover:opacity-100"
          >
            Masquer
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <ToolRail items={rail} />

        <div
          className="moo-canvas"
          style={{ "--moo-canvas-pad-bottom": pianoOpen ? "210px" : "30px" } as React.CSSProperties}
        >
          <div className={`moo-sheet${editing ? "" : " moo-sheet--read"}`}>
            {/* En-tête imprimé pour la vue solfège (la vue sol-fa a déjà le sien). */}
            {mode === "score" && (
              <header className="hidden pb-4 text-center print:block">
                <h2 className="text-xl">{title}</h2>
                {(result.header.composer || result.header.work) && (
                  <p className="mt-0.5 text-sm">
                    {[result.header.composer, result.header.work].filter(Boolean).join(" · ")}
                  </p>
                )}
                <p className="mt-1 text-sm">
                  Doh = {result.header.tonic}
                  {result.header.mode === "minor" ? " (mineur)" : ""} ·{" "}
                  {result.header.timeSignature.beats}/{result.header.timeSignature.beatType} ·{" "}
                  {formatTempoLabel(tempo)}
                </p>
              </header>
            )}

            <ScoreViewer
              ref={viewerRef}
              result={result}
              mode={mode}
              tempo={tempo}
              readOnly={!editing}
              onTempoChange={setTempo}
              onChange={setResult}
            />
          </div>
        </div>
      </div>

      {pianoOpen && (
        <PianoDock
          result={result}
          tempo={tempo}
          onBeforePlay={flushSolfaEdits}
          onBeatChange={handleBeat}
          onClose={() => setPianoOpen(false)}
        />
      )}

      {propertiesOpen && (
        <ScorePropertiesDrawer
          score={result}
          onClose={() => setPropertiesOpen(false)}
          onApply={(draft, keyId) => void applyProperties(draft, keyId)}
        />
      )}
    </div>
  );
}
