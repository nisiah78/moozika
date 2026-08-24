"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

/**
 * Pile de toasts, en bas à droite comme dans le design.
 *
 * ÉCART ASSUMÉ vs la maquette : elle efface tous ses toasts au bout de 4,2 s.
 * C'est bon pour une confirmation (« enregistré »), mais faux pour la fin d'une
 * transcription OMR qui dure 15-30 min : le toast s'évaporerait pendant que
 * l'utilisateur regarde ailleurs, et l'information serait perdue puisque la
 * cloche de notifications de l'ancien header a disparu. Les toasts porteurs
 * d'un RÉSULTAT sont donc persistants (`sticky`) jusqu'au clic.
 */

export type ToastKind = "ok" | "err" | "info";

export interface Toast {
  id: string;
  kind: ToastKind;
  title: string;
  body?: string;
  /** Reste affiché jusqu'à fermeture explicite. */
  sticky?: boolean;
  action?: { label: string; run: () => void };
}

const AUTO_DISMISS_MS = 4200;

interface ToastsValue {
  push: (t: Omit<Toast, "id">) => void;
  dismiss: (id: string) => void;
}

const Ctx = createContext<ToastsValue | null>(null);

export function useToasts(): ToastsValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useToasts hors ToastProvider");
  return v;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (t: Omit<Toast, "id">) => {
      seq.current += 1;
      const id = `t${seq.current}`;
      setToasts((prev) => [...prev, { ...t, id }]);
      if (!t.sticky) {
        window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
      }
    },
    [dismiss],
  );

  const value = useMemo(() => ({ push, dismiss }), [push, dismiss]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </Ctx.Provider>
  );
}

const TONE: Record<ToastKind, { bg: string; fg: string }> = {
  ok: { bg: "var(--ok)", fg: "#fff" },
  err: { bg: "var(--err)", fg: "#fff" },
  info: { bg: "var(--color-accent)", fg: "var(--color-bg)" },
};

function ToastStack({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;
  return (
    <div className="moo-toasts" role="status" aria-live="polite">
      {toasts.map((t) => {
        const tone = TONE[t.kind];
        return (
          <div
            key={t.id}
            className="flex items-start gap-3 px-4 py-3.5 shadow-lg"
            style={{ background: tone.bg, color: tone.fg, animation: "moo-toast-in .25s ease" }}
          >
            <div className="min-w-0 flex-1">
              <div className="font-sans text-[13px] font-extrabold">{t.title}</div>
              {t.body && <div className="mt-0.5 text-xs opacity-80">{t.body}</div>}
              {t.action && (
                <button
                  type="button"
                  onClick={() => {
                    t.action?.run();
                    onDismiss(t.id);
                  }}
                  className="mt-1.5 font-sans text-xs font-extrabold underline underline-offset-2"
                >
                  {t.action.label}
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={() => onDismiss(t.id)}
              aria-label="Fermer"
              className="shrink-0 opacity-70 hover:opacity-100"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
        );
      })}
    </div>
  );
}
