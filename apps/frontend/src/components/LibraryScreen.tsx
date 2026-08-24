"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { deleteScore, listScores, type ScoreListItem } from "@/lib/scoresApi";
import { ScoreSheetThumb } from "@/components/ScoreSheetThumb";
import { filterByNotation, formatUpdated, searchScores, sourceLabel } from "@/lib/libraryFilter";
import { useTranscriptions } from "@/components/TranscriptionsProvider";
import { useToasts } from "@/components/Toasts";
import { NOTATION_LABEL, ROUTES, type Notation } from "@/lib/navigation";
import { IconPlus, IconRefresh, IconSearch, IconTrash } from "@/components/icons";

/**
 * Écran bibliothèque.
 *
 * `notation` REGROUPE la liste : l'entrée « Sol-fa » de la sidebar montre les
 * partitions sol-fa, « Solfège » celles de solfège (cf. notationsOf). Elle
 * décide aussi de la vue d'ouverture. Un import MusicXML apparaît dans les deux
 * listes — il n'est ni l'un ni l'autre à la source.
 *
 * Les cartes de transcription en cours ne sont plus ici mais sur l'écran
 * d'import (comme dans la maquette) ; un lien compté y renvoie.
 */
export function LibraryScreen({ notation }: { notation: Notation }) {
  const router = useRouter();
  const { jobs, libraryReloadKey } = useTranscriptions();
  const { push } = useToasts();

  const [items, setItems] = useState<ScoreListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listScores();
      setItems(data.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // libraryReloadKey : une transcription qui aboutit ajoute une partition.
    void load();
  }, [load, libraryReloadKey]);

  // Notation d'abord, recherche ensuite : les compteurs parlent alors de la
  // liste courante (« 8 partitions ») et non du total toutes notations.
  const inNotation = useMemo(() => filterByNotation(items, notation), [items, notation]);
  const shown = useMemo(() => searchScores(inNotation, query), [inNotation, query]);

  const onDelete = useCallback(
    async (item: ScoreListItem) => {
      const title = item.title?.trim() || "Sans titre";
      if (!window.confirm(`Supprimer « ${title} » ? Cette action est irréversible.`)) return;
      setDeletingId(item.id);
      try {
        await deleteScore(item.id);
        setItems((prev) => prev.filter((row) => row.id !== item.id));
        push({ kind: "ok", title: "Partition supprimée", body: `« ${title} »` });
      } catch (e) {
        push({
          kind: "err",
          title: "Suppression impossible",
          body: e instanceof Error ? e.message : String(e),
        });
      } finally {
        setDeletingId(null);
      }
    },
    [push],
  );

  return (
    <div>
      <header className="flex items-end justify-between gap-5 border-b-2 border-divider px-[34px] pb-[18px] pt-[26px]">
        <div>
          <div className="moo-kicker mb-1.5">Bibliothèque · {NOTATION_LABEL[notation]}</div>
          <h1 className="m-0 text-[34px]">
            {notation === "solfa" ? "Partitions sol-fa" : "Partitions solfège"}
          </h1>
          <div className="mt-1 text-[13px] opacity-60">
            {loading
              ? "Chargement…"
              : `${inNotation.length} partition${inNotation.length > 1 ? "s" : ""}`}
            {query && !loading && ` · ${shown.length} affichée${shown.length > 1 ? "s" : ""}`}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="moo-seg">
            <label className="moo-seg-opt">
              <input type="radio" name="libview" defaultChecked />
              Partitions
            </label>
            {/* « Œuvres » est dessiné dans la maquette mais l'API n'expose
                aucune clé de regroupement (ni recueil, ni compositeur sur la
                liste) : désactivé et annoncé, plutôt que masqué ou simulé. */}
            <label className="moo-seg-opt" title="Bientôt disponible : le regroupement en œuvres demande un champ recueil côté API">
              <input type="radio" name="libview" disabled />
              Œuvres
            </label>
          </div>
          <Link href={ROUTES.import()} className="moo-btn moo-btn--primary gap-2">
            <IconPlus size={16} />
            Importer
          </Link>
        </div>
      </header>

      <div className="flex items-center gap-3.5 border-b-2 border-divider px-[34px] pb-3 pt-[18px]">
        <div className="flex flex-1 items-center gap-2 border border-divider bg-surface px-3 py-2">
          <span className="opacity-50">
            <IconSearch size={16} />
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Rechercher un titre…"
            aria-label="Rechercher un titre"
            className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} aria-label="Effacer" className="opacity-50 hover:opacity-100">
              ✕
            </button>
          )}
        </div>
        {jobs.length > 0 && (
          <Link href={ROUTES.import()} className="moo-btn moo-btn--ghost">
            {jobs.length} transcription{jobs.length > 1 ? "s" : ""} en cours →
          </Link>
        )}
        <button type="button" onClick={() => void load()} className="moo-btn moo-btn--secondary gap-2">
          <IconRefresh size={15} />
          Actualiser
        </button>
      </div>

      {error ? (
        <div className="px-[34px] py-8">
          <p className="text-sm" style={{ color: "var(--err)" }}>
            Impossible de charger la liste : {error}
          </p>
          <button type="button" onClick={() => void load()} className="moo-btn moo-btn--secondary mt-3">
            Réessayer
          </button>
        </div>
      ) : !loading && inNotation.length === 0 ? (
        <div className="px-[34px] py-16 text-center">
          <p className="font-sans text-lg font-extrabold">
            {items.length === 0
              ? "Aucune partition enregistrée"
              : `Aucune partition en ${NOTATION_LABEL[notation].toLowerCase()}`}
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm opacity-65">
            {items.length === 0
              ? "Importez un PDF sol-fa, un PDF de solfège ou un MusicXML, puis enregistrez la partition pour la retrouver ici."
              : /* Ne pas laisser croire que la bibliothèque est vide : les
                   partitions de l'autre notation existent bien. */
                `Vos ${items.length} partitions sont rangées dans l'autre notation.`}
          </p>
          <Link
            href={items.length === 0 ? ROUTES.import() : ROUTES.library(otherNotation(notation))}
            className="moo-btn moo-btn--primary mt-5 gap-2"
          >
            {items.length === 0 ? (
              <>
                <IconPlus size={16} />
                Importer une partition
              </>
            ) : (
              `Voir les partitions ${NOTATION_LABEL[otherNotation(notation)].toLowerCase()}`
            )}
          </Link>
        </div>
      ) : !loading && shown.length === 0 ? (
        <div className="px-[34px] py-16 text-center">
          <p className="font-sans text-lg font-extrabold">Aucun résultat</p>
          <p className="mt-2 text-sm opacity-65">
            Aucune partition ne correspond à « {query} ».
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-[22px] px-[34px] py-[26px]">
          {shown.map((item, i) => (
            <ScoreCard
              key={item.id}
              item={item}
              seed={i}
              deleting={deletingId === item.id}
              onOpen={() => router.push(`${ROUTES.score(item.id)}?vue=${notation}`)}
              onDelete={() => void onDelete(item)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ScoreCard({
  item,
  seed,
  deleting,
  onOpen,
  onDelete,
}: {
  item: ScoreListItem;
  seed: number;
  deleting: boolean;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const title = item.title?.trim() || "Sans titre";
  const updated = formatUpdated(item.updatedAt);

  return (
    <div className="flex flex-col border border-divider bg-surface">
      <div className="relative border-b border-divider bg-paper" style={{ aspectRatio: "3 / 3.9" }}>
        {/* Le bouton d'ouverture couvre l'aperçu : une carte entièrement
            cliquable engloberait le bouton supprimer. */}
        <button
          type="button"
          onClick={onOpen}
          className="absolute inset-0 block w-full"
          aria-label={`Ouvrir ${title}`}
        >
          <ScoreSheetThumb seed={seed} />
        </button>

        {/* Le design place ici un badge de statut, mais une partition
            ENREGISTRÉE vaut toujours « ready » (seul ScoreService l'écrit) :
            le badge dirait la même chose sur chaque carte. On y met la version,
            qui est une information réelle et utile dans une app d'édition. */}
        <span
          className="pointer-events-none absolute left-2 top-2 px-2 py-[3px] font-sans text-[10px] font-extrabold uppercase tracking-[0.04em]"
          style={{ background: "var(--color-accent)", color: "var(--color-bg)" }}
        >
          v{item.version}
        </span>

        <span
          className="pointer-events-none absolute bottom-2 left-2 px-[7px] py-[2px] font-sans text-[9px] font-extrabold uppercase tracking-[0.06em]"
          style={{
            background: "color-mix(in srgb, var(--paper-ink) 82%, transparent)",
            color: "var(--paper)",
          }}
        >
          {sourceLabel(item.sourceType)}
        </span>

        <button
          type="button"
          disabled={deleting}
          onClick={onDelete}
          title="Supprimer cette partition"
          aria-label={`Supprimer ${title}`}
          className="absolute right-2 top-2 grid h-[30px] w-[30px] place-items-center border disabled:opacity-40"
          style={{
            background: "color-mix(in srgb, var(--paper-ink) 8%, transparent)",
            borderColor: "color-mix(in srgb, var(--paper-ink) 20%, transparent)",
            color: "var(--paper-ink)",
          }}
        >
          <IconTrash size={15} />
        </button>
      </div>

      <div className="flex flex-col gap-1.5 px-3.5 py-3">
        <div className="font-sans text-sm font-extrabold uppercase leading-[1.2]">{title}</div>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] opacity-60">
          <span className="font-mono">Doh = {item.tonic}</span>
          {updated && (
            <>
              <span>·</span>
              <span>maj. {updated}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function otherNotation(n: Notation): Notation {
  return n === "solfa" ? "solfege" : "solfa";
}
