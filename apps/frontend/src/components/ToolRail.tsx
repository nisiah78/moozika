"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Rail d'outils vertical du viewer (84px), icône au-dessus du libellé.
 * Largeur pilotée par --moo-rail-w : le dock piano se positionne par calc()
 * sur cette variable, un nombre en dur ici les désynchroniserait.
 */

export interface RailItem {
  key: string;
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title?: string;
  /** Action destructrice : passe en rouge au survol. */
  danger?: boolean;
  /** Sous-menu ouvert au clic, à droite du rail (cf. Export). */
  menu?: { key: string; badge: string; label: string; onClick: () => void }[];
}

export function ToolRail({ items }: { items: RailItem[] }) {
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!openMenu) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpenMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenMenu(null);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [openMenu]);

  return (
    <nav ref={ref} className="moo-rail print:hidden" aria-label="Outils de la partition">
      {items.map((it) => (
        <div key={it.key} className="relative">
          <button
            type="button"
            title={it.title ?? it.label}
            disabled={it.disabled}
            aria-expanded={it.menu ? openMenu === it.key : undefined}
            onClick={() => {
              if (it.menu) {
                setOpenMenu((cur) => (cur === it.key ? null : it.key));
                return;
              }
              setOpenMenu(null);
              it.onClick();
            }}
            className={`flex w-full flex-col items-center gap-[5px] border-b border-divider px-1 py-3.5 font-sans text-[10px] font-extrabold tracking-[0.02em] disabled:opacity-35 ${
              it.danger ? "hover:text-[var(--err)]" : ""
            }`}
            style={
              it.active || openMenu === it.key
                ? { background: "var(--color-accent)", color: "var(--color-bg)" }
                : undefined
            }
          >
            {it.icon}
            {it.label}
          </button>

          {it.menu && openMenu === it.key && (
            <div
              className="absolute left-full top-0 z-40 ml-0.5 min-w-[220px] border border-divider bg-surface-2 shadow-lg"
              style={{ animation: "moo-pop .12s ease" }}
            >
              {it.menu.map((m) => (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => {
                    setOpenMenu(null);
                    m.onClick();
                  }}
                  className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-[13px] hover:bg-surface"
                >
                  <b className="w-[34px] flex-none font-sans text-accent">{m.badge}</b>
                  {m.label}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </nav>
  );
}
