"use client";

/** Vignette feuille A4 stylisée (pas de rendu OSMD). */
export function ScoreSheetThumb({ title }: { title: string }) {
  return (
    <div className="group flex flex-col items-center">
      <div
        className="relative w-full overflow-hidden rounded-sm bg-[#fffcf5] shadow-[0_2px_10px_rgba(0,0,0,0.12)] ring-1 ring-stone-300/80 transition group-hover:shadow-[0_4px_16px_rgba(0,0,0,0.16)]"
        style={{ aspectRatio: "1 / 1.414" }}
      >
        <div className="absolute inset-x-[12%] top-[14%] space-y-3">
          <div className="mx-auto h-1.5 w-2/3 rounded-full bg-stone-300/90" />
          {[0, 1, 2].map((block) => (
            <div key={block} className="space-y-[3px] pt-2">
              {[0, 1, 2, 3, 4].map((line) => (
                <div key={line} className="h-px w-full bg-stone-400/70" />
              ))}
            </div>
          ))}
        </div>
        <div className="absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-[#fffcf5] to-transparent" />
      </div>
      <p className="mt-2 w-full truncate text-center text-sm font-medium text-stone-800">
        {title?.trim() || "Sans titre"}
      </p>
    </div>
  );
}
