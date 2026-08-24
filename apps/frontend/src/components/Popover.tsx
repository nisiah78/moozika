"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * Flottant positionné à un point de l'écran (menus contextuels de la partition).
 *
 * Factorise ce que les cinq menus dupliquaient : positionnement `fixed`,
 * fermeture au clic extérieur et à Escape, et le chrome du design.
 *
 * Rendu en PORTAL sur `document.body`, pour deux raisons :
 *   — ces menus sont montés depuis l'intérieur de `.moo-sheet`, qui repointe les
 *     tokens vers le papier CLAIR pour son sous-arbre. Sans portal, un
 *     `bg-surface-2` deviendrait blanc au lieu du panneau sombre du design ;
 *   — `position: fixed` est résolu par rapport au premier ancêtre transformé ou
 *     filtré, pas par rapport au viewport. Sortir du sous-arbre supprime cette
 *     classe de bugs de placement d'un coup.
 *
 * Le placement est MESURÉ, pas devine. Chaque menu codait auparavant sa taille
 * en dur (`Math.min(x, innerWidth - 200)`, `- 240`, `- 220`…), avec deux
 * défauts : la valeur devait suivre le contenu à la main, et surtout seul le
 * maximum était borné — sur une fenêtre étroite, `innerWidth - 200` devient
 * négatif et le menu sortait par la gauche. Ici on lit la taille réelle après
 * montage et on borne des DEUX côtés.
 */

const MARGIN = 8;

export function Popover({
  x,
  y,
  onClose,
  children,
  className = "",
  level = 90,
  role = "dialog",
  ariaLabel,
}: {
  x: number;
  y: number;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
  /** Échelle du design : 35 palette · 40 export · 45 nuances · 90/95 menus. */
  level?: number;
  role?: "dialog" | "listbox" | "menu";
  ariaLabel?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // `null` = pas encore mesuré : on rend invisible pour éviter le saut visible
  // entre la position demandée et la position corrigée.
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  // Le portal n'existe qu'après montage côté navigateur. Déclaré ICI, avant
  // l'effet de placement, qui doit se rejouer une fois le nœud réellement dans
  // le DOM — sinon la mesure échoue et le menu reste invisible.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const place = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    const maxLeft = window.innerWidth - width - MARGIN;
    const maxTop = window.innerHeight - height - MARGIN;
    setPos({
      left: Math.max(MARGIN, Math.min(x, maxLeft)),
      top: Math.max(MARGIN, Math.min(y, maxTop)),
    });
  }, [x, y]);

  useLayoutEffect(place, [place, mounted]);

  useEffect(() => {
    // Un redimensionnement pendant qu'un menu est ouvert le laisserait dehors.
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [place]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  if (!mounted) return null;

  return createPortal(
    <div
      ref={ref}
      role={role}
      aria-label={ariaLabel}
      className={`fixed border border-divider bg-surface-2 text-ink shadow-lg print:hidden ${className}`}
      style={{
        left: pos?.left ?? x,
        top: pos?.top ?? y,
        zIndex: level,
        visibility: pos ? "visible" : "hidden",
        animation: "moo-pop .14s ease",
      }}
    >
      {children}
    </div>,
    document.body,
  );
}

/** Sur-titre des flottants (« Hauteur », « S · m.3 t.2 »…). */
export function PopoverTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="border-b border-divider px-3 py-2 font-sans text-[10px] font-extrabold uppercase tracking-[0.08em] opacity-55">
      {children}
    </p>
  );
}

/** Élément de liste d'un flottant. */
export function PopoverItem({
  onClick,
  active,
  children,
  title,
  role: itemRole,
}: {
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
  title?: string;
  role?: "option" | "menuitem";
}) {
  return (
    <button
      type="button"
      role={itemRole}
      aria-selected={itemRole === "option" ? Boolean(active) : undefined}
      title={title}
      onClick={onClick}
      className="block w-full px-3 py-1.5 text-left text-sm hover:bg-surface"
      style={active ? { color: "var(--color-accent)", fontWeight: 700 } : undefined}
    >
      {children}
    </button>
  );
}
