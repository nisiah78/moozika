"use client";

import { useCallback, useEffect, useState } from "react";
import { deleteScore, listScores, type ScoreListItem } from "@/lib/scoresApi";
import { ScoreSheetThumb } from "@/components/ScoreSheetThumb";

export function ScoreLibrary({
  onOpen,
  onImport,
  onDeleted,
}: {
  onOpen: (id: string) => void;
  onImport: () => void;
  onDeleted?: (id: string) => void;
}) {
  const [items, setItems] = useState<ScoreListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDeleteError(null);
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
    void load();
  }, [load]);

  const onDelete = useCallback(
    async (item: ScoreListItem) => {
      const title = item.title?.trim() || "Sans titre";
      const ok = window.confirm(`Supprimer « ${title} » ? Cette action est irréversible.`);
      if (!ok) return;
      setDeletingId(item.id);
      setDeleteError(null);
      try {
        await deleteScore(item.id);
        setItems((prev) => prev.filter((row) => row.id !== item.id));
        onDeleted?.(item.id);
      } catch (e) {
        setDeleteError(e instanceof Error ? e.message : String(e));
      } finally {
        setDeletingId(null);
      }
    },
    [onDeleted],
  );

  if (loading) {
    return <p className="text-sm text-stone-500">Chargement des partitions…</p>;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        Impossible de charger la liste : {error}
        <button type="button" className="ml-3 underline" onClick={() => void load()}>
          Réessayer
        </button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-stone-300 bg-white px-6 py-12 text-center">
        <p className="font-medium text-stone-800">Aucune partition enregistrée</p>
        <p className="mt-2 text-sm text-stone-500">
          Importez une partition puis cliquez sur Enregistrer.
        </p>
        <button
          type="button"
          onClick={onImport}
          className="mt-4 rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-800"
        >
          Importer une partition
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-stone-900">Liste des partitions</h2>
          <p className="text-sm text-stone-500">{items.length} partition{items.length > 1 ? "s" : ""}</p>
        </div>
        <button type="button" onClick={() => void load()} className="text-sm text-stone-600 underline">
          Actualiser
        </button>
      </div>
      {deleteError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          Impossible de supprimer : {deleteError}
        </div>
      )}
      <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((item) => (
          <li key={item.id} className="relative">
            <button
              type="button"
              onClick={() => onOpen(item.id)}
              className="w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-stone-500"
            >
              <ScoreSheetThumb title={item.title} />
            </button>
            <button
              type="button"
              disabled={deletingId === item.id}
              onClick={() => void onDelete(item)}
              title="Supprimer cette partition"
              aria-label={`Supprimer ${item.title?.trim() || "Sans titre"}`}
              className="absolute right-1.5 top-1.5 flex h-8 w-8 items-center justify-center rounded-full bg-white text-stone-600 shadow ring-1 ring-stone-300/90 transition hover:bg-red-50 hover:text-red-700 hover:ring-red-200 disabled:opacity-50"
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6" />
                <path d="M14 11v6" />
                <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              </svg>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
