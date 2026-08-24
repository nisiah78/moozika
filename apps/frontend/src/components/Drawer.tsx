"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { IconClose } from "@/components/icons";

/**
 * Panneau glissant depuis la droite (design : `min(440px,100%)`, `moo-drawer`).
 *
 * Rendu en PORTAL sur `document.body`, pour les mêmes raisons que Popover :
 *   — il est monté depuis le plan de travail du viewer ; en portal il lit
 *     toujours les tokens de `:root` et ne peut pas hériter d'une redéfinition
 *     locale (la feuille repointe les tokens vers le papier clair) ;
 *   — un panneau modal en `position: fixed` ne doit pas dépendre de son
 *     sous-arbre : un `transform`, un `filter` ou un `contain` sur un ancêtre en
 *     ferait le bloc conteneur, et le panneau serait mal placé ou rogné par
 *     l'`overflow: hidden` de `.moo-workspace`.
 *
 * Les fonds sont écrits avec une SECONDE déclaration en repli : `color-mix()`
 * n'est pas compris partout, et un fond invalide n'est pas ignoré — il rend le
 * panneau transparent. La première ligne (rgba / hex) est universelle, la
 * seconde l'améliore quand elle est supportée.
 */
export function Drawer({
  title,
  onClose,
  children,
  footer,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!mounted) return null;

  return createPortal(
    <div className="print:hidden">
      <div
        className="fixed inset-0 z-[49]"
        style={{ background: "rgba(0, 0, 0, 0.45)" }}
        role="presentation"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="moo-drawer fixed bottom-0 right-0 top-0 z-50 flex w-[min(440px,100%)] flex-col border-l-2 border-divider shadow-lg"
        style={{
          background: "var(--color-surface, #211c15)",
          color: "var(--color-text, #f2ebda)",
          animation: "moo-drawer .22s ease",
        }}
      >
        <div className="flex items-center justify-between border-b-2 border-divider px-6 py-5">
          <h3 className="m-0 text-[22px]">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="opacity-70 hover:opacity-100"
          >
            <IconClose size={20} />
          </button>
        </div>
        <div className="flex flex-1 flex-col gap-[18px] overflow-auto p-6">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2.5 border-t-2 border-divider px-6 py-4">
            {footer}
          </div>
        )}
      </aside>
    </div>,
    document.body,
  );
}
