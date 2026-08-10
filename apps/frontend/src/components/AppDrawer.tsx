"use client";

export type AppView = "import" | "library" | "viewer";

const ITEMS: { id: AppView; label: string; hint: string }[] = [
  { id: "import", label: "Importer une partition", hint: "PDF ou MusicXML" },
  { id: "library", label: "Liste des partitions", hint: "Partitions enregistrées" },
];

export function AppDrawer({
  open,
  onClose,
  view,
  onNavigate,
}: {
  open: boolean;
  onClose: () => void;
  view: AppView;
  onNavigate: (view: AppView) => void;
}) {
  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity print:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-stone-200 bg-[#f7f4ef] shadow-xl transition-transform duration-200 print:hidden ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Navigation"
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-4 py-4">
          <span className="font-serif text-xl font-semibold tracking-tight text-stone-900">
            moozika
          </span>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-2 text-stone-600 hover:bg-stone-200/70"
            aria-label="Fermer le menu"
          >
            ✕
          </button>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3">
          {ITEMS.map((item) => {
            const active = view === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  onNavigate(item.id);
                  onClose();
                }}
                className={`rounded-md px-3 py-3 text-left transition ${
                  active
                    ? "bg-stone-900 text-white"
                    : "text-stone-800 hover:bg-stone-200/80"
                }`}
              >
                <div className="text-sm font-semibold">{item.label}</div>
                <div className={`mt-0.5 text-xs ${active ? "text-stone-300" : "text-stone-500"}`}>
                  {item.hint}
                </div>
              </button>
            );
          })}
          {view === "viewer" && (
            <button
              type="button"
              onClick={() => {
                onNavigate("viewer");
                onClose();
              }}
              className="rounded-md bg-amber-100 px-3 py-3 text-left text-sm font-semibold text-amber-950"
            >
              Partition ouverte
            </button>
          )}
        </nav>
      </aside>
    </>
  );
}
