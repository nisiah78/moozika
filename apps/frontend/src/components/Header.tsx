"use client";

export function Header({ onMenuClick }: { onMenuClick?: () => void }) {
  return (
    <header className="border-b border-stone-200 bg-[#fffcf5] print:hidden">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="Ouvrir le menu"
            onClick={onMenuClick}
            className="rounded p-2 text-stone-700 hover:bg-stone-200/70"
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <h1 className="font-serif text-2xl font-bold tracking-tight text-stone-900">moozika</h1>
        </div>
      </div>
    </header>
  );
}
