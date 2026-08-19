"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TempoControl } from "@/components/TempoControl";
import { defaultTempoSettings, formatTempoLabel, resolveQuarterBpm, type TempoSettings } from "@/lib/tempo";
import type { MusicXmlParseResponse, ScoreResult, Voice } from "@/lib/types";
import { parsePdfStream } from "@/lib/omrStream";
import {
  isMusicXmlFile,
  isPdfFile,
  musicXmlResponseToScoreResult,
  readMusicXmlContent,
} from "@/lib/scoreImport";
import { ScoreViewer, type ScoreViewerHandle } from "@/components/ScoreViewer";
import { PlaybackControls } from "@/components/PlaybackControls";
import { applyBeatHighlight } from "@/lib/playbackHighlight";
import { Header } from "@/components/Header";
import { AppDrawer, type AppView } from "@/components/AppDrawer";
import { ScoreLibrary } from "@/components/ScoreLibrary";
import {
  addScoreVersion,
  createScore,
  detailToScoreResult,
  getScore,
  modelToMusicxml,
} from "@/lib/scoresApi";
import { ScorePropertiesModal } from "@/components/ScorePropertiesModal";
import {
  applyScoreProperties,
  regenerateFromModels,
} from "@/lib/scoreEdit";
import { KEY_SIGNATURE_OPTIONS } from "@/lib/keySignatures";
import { buildSolfaMarkdown } from "@/lib/solfaMarkdown";

type Mode = "score" | "solfa";

export default function Home() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [view, setView] = useState<AppView>("import");
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [scoreId, setScoreId] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("score");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [progressPct, setProgressPct] = useState(0);
  const [progressMsg, setProgressMsg] = useState("");
  const [partialVoices, setPartialVoices] = useState<Voice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const [tempo, setTempo] = useState<TempoSettings | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [propertiesOpen, setPropertiesOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const viewerRef = useRef<ScoreViewerHandle>(null);
  const exportMenuRef = useRef<HTMLDetailsElement>(null);

  // Tempo / titre : initialisés à l'ouverture (openViewer), pas à chaque
  // onChange d'édition — sinon le tempo choisi est écrasé avant Enregistrer.
  useEffect(() => {
    if (!result) setTempo(null);
    applyBeatHighlight(null); // efface tout surlignage résiduel
  }, [result]);

  const openViewer = useCallback((score: ScoreResult, id: string | null = null) => {
    setResult(score);
    setScoreId(id);
    setWarnings(score.warnings ?? []);
    setTempo(defaultTempoSettings(score));
    setTitleDraft(score.header.title || "");
    setView("viewer");
  }, []);

  const uploadPdf = useCallback(
    async (file: File) => {
      setLoading(true);
      setError(null);
      setWarnings([]);
      setProgressPct(0);
      setProgressMsg("Envoi du fichier…");
      setPartialVoices([]);
      setResult(null);
      setScoreId(null);
      setSaveMsg(null);
      try {
        const score = await parsePdfStream(file, {
          onProgress: (_phase, pct, message) => {
            setProgressPct(Math.round(pct));
            setProgressMsg(message);
          },
          onVoice: (_index, _total, voice) => {
            setPartialVoices((prev) => {
              const next = prev.filter((v) => v.name !== voice.name);
              return [...next, voice];
            });
          },
        });
        openViewer(score);
        setMode(score.source === "audiveris" ? "solfa" : "score");
        setPartialVoices([]);
        setProgressMsg("");
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [openViewer],
  );

  const uploadMusicXml = useCallback(
    async (file: File) => {
      if (isPdfFile(file)) {
        setError(
          "Ce fichier est un PDF, pas du MusicXML. Utilisez la zone d'import principale " +
            "pour les PDF (sol-fa malgache ou portée / solfège via Audiveris).",
        );
        return;
      }
      setLoading(true);
      setError(null);
      setWarnings([]);
      setScoreId(null);
      setSaveMsg(null);
      try {
        const form = new FormData();
        form.append("file", file);
        const [musicxml, res] = await Promise.all([
          readMusicXmlContent(file),
          fetch("/api/musicxml/parse", { method: "POST", body: form }),
        ]);
        const data = (await res.json()) as MusicXmlParseResponse & { detail?: string };
        if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
        openViewer(musicXmlResponseToScoreResult(data, file, musicxml));
        setMode("solfa");
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setResult(null);
      } finally {
        setLoading(false);
      }
    },
    [openViewer],
  );

  const onFile = useCallback(
    (file: File) => {
      if (isPdfFile(file)) return uploadPdf(file);
      if (isMusicXmlFile(file)) return uploadMusicXml(file);
      setError(
        "Format non supporté. PDF sol-fa malgache, ou MusicXML (.xml, .musicxml, .mxl) " +
          "exporté depuis un logiciel de notation.",
      );
      setResult(null);
    },
    [uploadPdf, uploadMusicXml],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) onFile(file);
    },
    [onFile],
  );

  const loadSaved = useCallback(
    async (id: string) => {
      setLoading(true);
      setError(null);
      try {
        const detail = await getScore(id);
        const score = detailToScoreResult(detail);
        openViewer(score, detail.id);
        setMode("solfa");
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [openViewer],
  );

  const saveScore = useCallback(async () => {
    if (!result) return;
    if (!tempo) {
      setError("Tempo manquant — impossible d'enregistrer");
      return;
    }
    setSaving(true);
    setSaveMsg(null);
    setError(null);
    try {
      // Commit la cellule encore focalisée + brouillons avant de lire le score
      // (sinon Enregistrer sauvegarde / réaffiche l'état d'avant la correction).
      const flushed =
        mode === "solfa"
          ? await viewerRef.current?.flush()
          : null;
      const base = flushed ?? result;

      const title = titleDraft.trim() || base.header.title || "Sans titre";
      const quarterBpm = Math.max(1, Math.round(resolveQuarterBpm(tempo)));
      const header = {
        ...base.header,
        title,
        tempo: tempo.bpm,
        tempoBeatUnit: tempo.beatUnit,
        tempoDotted: tempo.dotted,
      };
      let voices = base.voices.map((v) => ({
        ...v,
        model: { ...v.model, tempo: quarterBpm },
      }));

      // Régénère le MusicXML pour y écrire le métronome (beat-unit=quarter).
      // Important : ne PAS reprendre `converted.voices[].notation` (to_solfa
      // backend) ni perdre `triplets` / `enterMeasure` — ça découpait les
      // triolets `drm` en `d : r | m` à l'enregistrement.
      const converted = await modelToMusicxml(voices.map((v) => v.model), {
        title,
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

      const model = {
        header,
        voices,
        source: base.source,
        warnings: base.warnings,
      };
      const sourceType =
        base.source === "audiveris"
          ? "staff"
          : base.source === "solfa_pdf"
            ? "solfa"
            : "musicxml";

      if (scoreId) {
        const res = await addScoreVersion(scoreId, {
          title,
          tonic: base.header.tonic,
          origin: "edit",
          musicxml,
          model,
        });
        setSaveMsg(`Version ${res.version} enregistrée`);
      } else {
        const res = await createScore({
          title,
          tonic: base.header.tonic,
          sourceType,
          origin: base.source === "audiveris" || base.source === "solfa_pdf" ? "omr" : "import",
          musicxml,
          model,
        });
        setScoreId(res.id);
        setSaveMsg(`Partition enregistrée (v${res.version})`);
      }
      setResult({ ...base, header, voices, musicxml, uploadedFile: undefined });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [result, scoreId, titleDraft, mode, tempo]);

  const applyProperties = useCallback(
    async (draft: Parameters<typeof applyScoreProperties>[1], keyId: string) => {
      if (!result) return;
      setError(null);
      try {
        const flushed = mode === "solfa" ? await viewerRef.current?.flush() : null;
        const base = flushed ?? result;
        const keyEntry = KEY_SIGNATURE_OPTIONS.find((k) => k.id === keyId);
        if (!keyEntry) throw new Error("Tonalité inconnue");
        const { score: mutated, needsRegen } = applyScoreProperties(base, draft, keyEntry);
        const next = needsRegen ? await regenerateFromModels(mutated, mutated.voices) : mutated;
        setResult(next);
        setTitleDraft(next.header.title || "");
        setPropertiesOpen(false);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [result, mode],
  );

  const navigate = (next: AppView) => {
    setView(next);
    if (next !== "viewer") setSaveMsg(null);
  };

  const switchMode = useCallback(
    async (next: Mode) => {
      if (next === mode) return;
      if (mode === "solfa" && next === "score") {
        try {
          await viewerRef.current?.flush();
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
          return;
        }
      }
      setMode(next);
    },
    [mode],
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
    //    resynchronise son texte affiché dans un useEffect (committedValue →
    //    draft) qui ne s'exécute qu'au re-render SUIVANT. Sans attendre, window
    //    .print() figerait le DOM d'avant cette mise à jour (décalage d'un cran).
    //    Deux frames garantissent que tous les commits React (parent + cellules)
    //    sont appliqués au DOM avant de capturer l'impression.
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
    window.print();
  }, [flushSolfaEdits]);

  const closeExportMenu = useCallback(() => {
    if (exportMenuRef.current) exportMenuRef.current.open = false;
  }, []);

  const downloadTextFile = useCallback((filename: string, content: string) => {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, []);

  const exportMarkdown = useCallback(async () => {
    if (!result || !tempo) return;
    try {
      const content =
        mode === "solfa" && viewerRef.current
          ? await viewerRef.current.exportMarkdown()
          : buildSolfaMarkdown(result, tempo);
      const baseName =
        (titleDraft || result.header.title || "partition")
          .toLowerCase()
          .normalize("NFD")
          .replace(/[\u0300-\u036f]/g, "")
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "") || "partition";
      downloadTextFile(`${baseName}.md`, content);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      closeExportMenu();
    }
  }, [closeExportMenu, downloadTextFile, mode, result, tempo, titleDraft]);

  return (
    <>
      <Header onMenuClick={() => setDrawerOpen(true)} />
      <AppDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        view={view}
        onNavigate={navigate}
      />

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        {view === "library" && (
          <ScoreLibrary
            onOpen={(id) => void loadSaved(id)}
            onImport={() => navigate("import")}
            onDeleted={(id) => {
              if (scoreId === id) {
                setScoreId(null);
                setResult(null);
              }
            }}
          />
        )}

        {view === "import" && (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition ${
              dragging
                ? "border-stone-800 bg-stone-100"
                : "border-stone-300 bg-[#fffcf5] hover:bg-white"
            }`}
          >
            <p className="font-medium">Importer une partition</p>
            <p className="mt-2 max-w-lg text-sm text-stone-600">
              <strong>PDF sol-fa malgache</strong> · <strong>PDF portée / solfège</strong> ·{" "}
              <strong>MusicXML</strong> (.xml / .mxl)
            </p>
            <p className="mt-2 text-xs text-stone-500">
              Stack Docker : <code className="text-xs">make docker-up</code>
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf,.xml,.musicxml,.mxl"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onFile(file);
              }}
            />
          </div>
        )}

        {loading && (
          <div className="space-y-2 rounded-lg border bg-white p-4">
            <div className="flex items-center justify-between text-sm text-stone-600">
              <span>{progressMsg || "Chargement…"}</span>
              {progressPct > 0 && <span className="tabular-nums">{progressPct}%</span>}
            </div>
            {progressPct > 0 && (
              <div className="h-2 overflow-hidden rounded bg-stone-100">
                <div
                  className="h-full bg-stone-900 transition-[width] duration-300"
                  style={{ width: `${Math.min(100, Math.max(0, progressPct))}%` }}
                />
              </div>
            )}
            {partialVoices.length > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-stone-500">
                {partialVoices.map((v) => (
                  <li key={v.name}>
                    {v.name} — {v.notation.slice(0, 80)}
                    {v.notation.length > 80 ? "…" : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {error && (
          <p className="whitespace-pre-wrap rounded bg-red-50 p-3 text-sm text-red-700 print:hidden">
            Erreur : {error}
          </p>
        )}
        {warnings.length > 0 && view === "viewer" && (
          <ul className="rounded bg-amber-50 p-3 text-sm text-amber-900 print:hidden">
            {warnings.map((w) => (
              <li key={w}>⚠ {w}</li>
            ))}
          </ul>
        )}

        {view === "viewer" && result && tempo && (
          <section className="rounded-lg border border-stone-200 bg-[#fffcf5] print:border-0 print:bg-white">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-200 px-4 py-3 print:hidden">
              <div className="min-w-0 flex-1">
                <input
                  value={titleDraft}
                  onChange={(e) => setTitleDraft(e.target.value)}
                  className="w-full max-w-md rounded border border-transparent bg-transparent px-1 text-lg font-semibold hover:border-stone-300 focus:border-stone-400 focus:outline-none"
                  aria-label="Titre"
                />
                <p className="text-sm text-stone-500">
                  Doh = {result.header.tonic} · {result.header.timeSignature.beats}/
                  {result.header.timeSignature.beatType} · {formatTempoLabel(tempo)} ·{" "}
                  {result.voices.length} voix
                  {scoreId ? ` · id ${scoreId.slice(0, 8)}…` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => setPropertiesOpen(true)}
                  className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-100"
                >
                  Éditer
                </button>
                <button
                  type="button"
                  disabled={saving || !result.musicxml}
                  onMouseDown={(e) => {
                    // Empêche le blur de la cellule avant qu'on puisse lire sa valeur
                    e.preventDefault();
                  }}
                  onClick={() => void saveScore()}
                  className="rounded-md bg-stone-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-stone-800 disabled:opacity-50"
                >
                  {saving ? "Enregistrement…" : "Enregistrer"}
                </button>
                {mode === "score" && <TempoControl value={tempo} onChange={setTempo} compact />}
                <PlaybackControls
                  result={result}
                  tempo={tempo}
                  onBeforePlay={flushSolfaEdits}
                  onBeatChange={applyBeatHighlight}
                />
                <details ref={exportMenuRef} className="relative">
                  <summary
                    className="inline-flex list-none items-center gap-1.5 rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm font-medium text-stone-700 hover:bg-stone-100 [&::-webkit-details-marker]:hidden"
                    title="Exporter la partition"
                  >
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden
                    >
                      <path d="M12 3v12" />
                      <path d="m7 10 5 5 5-5" />
                      <path d="M5 21h14" />
                    </svg>
                    Export
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden
                    >
                      <path d="m6 9 6 6 6-6" />
                    </svg>
                  </summary>
                  <div className="absolute right-0 z-20 mt-2 min-w-32 rounded-md border border-stone-200 bg-white p-1 shadow-lg">
                    <button
                      type="button"
                      onClick={() => {
                        closeExportMenu();
                        void printScore();
                      }}
                      className="block w-full rounded px-3 py-2 text-left text-sm text-stone-700 hover:bg-stone-100"
                      title={`Imprimer / exporter en PDF la vue ${mode === "solfa" ? "sol-fa" : "portée"}`}
                    >
                      PDF
                    </button>
                    <button
                      type="button"
                      onClick={() => void exportMarkdown()}
                      className="block w-full rounded px-3 py-2 text-left text-sm text-stone-700 hover:bg-stone-100"
                      title="Exporter la partition sol-fa en Markdown"
                    >
                      .md
                    </button>
                  </div>
                </details>
                <div className="inline-flex overflow-hidden rounded-md border border-stone-300">
                  <ToggleButton active={mode === "score"} onClick={() => void switchMode("score")}>
                    Portée
                  </ToggleButton>
                  <ToggleButton active={mode === "solfa"} onClick={() => void switchMode("solfa")}>
                    Sol-fa
                  </ToggleButton>
                </div>
              </div>
            </div>

            {saveMsg && (
              <p className="border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800 print:hidden">
                {saveMsg}
              </p>
            )}

            {/* En-tête visible seulement à l'impression pour la vue Portée
                (la vue Sol-fa possède déjà son propre en-tête recueil). */}
            {mode === "score" && (
              <header className="hidden px-4 pt-4 text-center print:block">
                <h2 className="text-xl font-bold text-stone-900">
                  {titleDraft.trim() || result.header.title || "Sans titre"}
                </h2>
                {(result.header.composer || result.header.work) && (
                  <p className="mt-0.5 text-sm text-stone-600">
                    {[result.header.composer, result.header.work].filter(Boolean).join(" · ")}
                  </p>
                )}
                <p className="mt-1 text-sm text-stone-600">
                  Doh = {result.header.tonic}
                  {result.header.mode === "minor" ? " (mineur)" : ""} ·{" "}
                  {result.header.timeSignature.beats}/{result.header.timeSignature.beatType} ·{" "}
                  {formatTempoLabel(tempo)}
                </p>
              </header>
            )}

            {propertiesOpen && result && (
              <ScorePropertiesModal
                open={propertiesOpen}
                score={result}
                onClose={() => setPropertiesOpen(false)}
                onApply={(draft, keyId) => void applyProperties(draft, keyId)}
              />
            )}

            <div className={mode === "solfa" ? "p-2 sm:p-3" : "p-4"}>
              <ScoreViewer
                ref={viewerRef}
                result={result}
                mode={mode}
                tempo={tempo}
                onTempoChange={setTempo}
                onChange={setResult}
              />
            </div>
          </section>
        )}
      </main>
    </>
  );
}

function ToggleButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-1.5 text-sm font-medium ${
        active ? "bg-stone-900 text-white" : "bg-white text-stone-700 hover:bg-stone-100"
      }`}
    >
      {children}
    </button>
  );
}
