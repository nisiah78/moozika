"use client";

import { useCallback, useEffect, useState } from "react";
import { listScores, type ScoreListItem } from "@/lib/scoresApi";
import { ScoreSheetThumb } from "@/components/ScoreSheetThumb";

export function ScoreLibrary({
  onOpen,
  onImport,
}: {
  onOpen: (id: string) => void;
  onImport: () => void;
}) {
  const [items, setItems] = useState<ScoreListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
    void load();
  }, [load]);

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
      <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onOpen(item.id)}
              className="w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-stone-500"
            >
              <ScoreSheetThumb title={item.title} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
