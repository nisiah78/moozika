"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  isPathActive,
  NOTATIONS,
  NOTATION_LABEL,
  ROUTES,
  type Notation,
} from "@/lib/navigation";
import { useTranscriptions } from "@/components/TranscriptionsProvider";
import { useApiHealth } from "@/lib/apiHealth";
import {
  IconBook,
  IconChevronDown,
  IconInfo,
  IconLibrary,
  IconMail,
  IconUpload,
} from "@/components/icons";

/** Styles repris de la maquette (headBase / navBase / subBase / subActive). */
const NAV_BASE =
  "flex w-full items-center gap-3 border border-transparent px-3.5 py-3 text-left";
const HEAD_BASE = "flex w-full items-center gap-3 border-0 bg-transparent px-3.5 py-3 text-left";
const LABEL = "font-sans text-sm font-extrabold";

export function Sidebar() {
  const pathname = usePathname();
  const { jobs } = useTranscriptions();
  const health = useApiHealth();

  // Les sections s'ouvrent d'office si l'on est dedans : arriver sur
  // /bibliotheque/solfa par un lien profond doit montrer où l'on se trouve.
  const [libOpen, setLibOpen] = useState(() => isPathActive(pathname, "/bibliotheque"));
  const [learnOpen, setLearnOpen] = useState(() => isPathActive(pathname, "/apprendre"));

  const libActive = isPathActive(pathname, "/bibliotheque") || isPathActive(pathname, "/partition");

  return (
    <aside className="moo-sidebar" aria-label="Navigation principale">
      <div className="flex items-center gap-2.5 border-b-2 border-divider px-5 py-[22px]">
        <span className="grid h-[26px] w-[26px] place-items-center bg-accent font-sans font-extrabold text-bg">
          m
        </span>
        <span className="font-sans text-[22px] font-extrabold tracking-[-0.02em]">moozika</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-3 pb-1.5 pt-3">
        <Section
          label="Bibliothèque"
          icon={<IconLibrary />}
          open={libOpen}
          active={libActive}
          onToggle={() => setLibOpen((v) => !v)}
          hrefFor={ROUTES.library}
          pathname={pathname}
        />

        <Link
          href={ROUTES.import()}
          className={NAV_BASE}
          style={activeStyle(isPathActive(pathname, "/import"))}
        >
          <IconUpload />
          <b className={`${LABEL} flex-1`}>Importer</b>
          {jobs.length > 0 && (
            /* Compteur de jobs actifs : addition au design, mais la cloche de
               notifications a disparu avec l'ancien header et une transcription
               longue ne doit pas devenir invisible. */
            <span
              className="grid h-5 min-w-5 place-items-center px-1 font-sans text-[10px] font-extrabold"
              style={
                isPathActive(pathname, "/import")
                  ? { background: "var(--color-bg)", color: "var(--color-accent)" }
                  : { background: "var(--color-accent)", color: "var(--color-bg)" }
              }
              title={`${jobs.length} transcription${jobs.length > 1 ? "s" : ""} en cours`}
            >
              {jobs.length}
            </span>
          )}
        </Link>

        <Section
          label="Apprendre"
          icon={<IconBook />}
          open={learnOpen}
          active={isPathActive(pathname, "/apprendre")}
          onToggle={() => setLearnOpen((v) => !v)}
          hrefFor={ROUTES.learn}
          pathname={pathname}
        />

        <Link
          href={ROUTES.contact()}
          className={NAV_BASE}
          style={activeStyle(isPathActive(pathname, "/contact"))}
        >
          <IconMail />
          <b className={LABEL}>Me contacter</b>
        </Link>
        <Link
          href={ROUTES.about()}
          className={NAV_BASE}
          style={activeStyle(isPathActive(pathname, "/a-propos"))}
        >
          <IconInfo />
          <b className={LABEL}>À propos</b>
        </Link>
      </nav>

      <div className="border-t-2 border-divider px-5 py-4 text-[11px] opacity-55">
        <div className="flex justify-between">
          <span>API Moozika</span>
          <span style={{ color: health === "up" ? "var(--ok)" : health === "down" ? "var(--err)" : undefined }}>
            {health === "up" ? "● en ligne" : health === "down" ? "● injoignable" : "● …"}
          </span>
        </div>
        <div className="mt-1 font-mono">{apiHost()}</div>
      </div>
    </aside>
  );
}

function apiHost(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";
  return raw.replace(/^https?:\/\//, "");
}

function activeStyle(active: boolean): React.CSSProperties | undefined {
  return active ? { background: "var(--color-accent)", color: "var(--color-bg)" } : undefined;
}

/** Section dépliable (Bibliothèque, Apprendre) avec ses deux sous-items. */
function Section({
  label,
  icon,
  open,
  active,
  onToggle,
  hrefFor,
  pathname,
}: {
  label: string;
  icon: React.ReactNode;
  open: boolean;
  active: boolean;
  onToggle: () => void;
  hrefFor: (n: Notation) => string;
  pathname: string;
}) {
  return (
    <div className="border border-divider bg-surface-2">
      <button
        type="button"
        onClick={onToggle}
        className={HEAD_BASE}
        aria-expanded={open}
        style={active && !open ? { color: "var(--color-accent)" } : undefined}
      >
        {icon}
        <b className={`${LABEL} flex-1`}>{label}</b>
        <span
          className="flex transition-transform duration-200"
          style={{ transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}
        >
          <IconChevronDown size={15} />
        </span>
      </button>
      {open && (
        <div className="pb-2 pt-1">
          {NOTATIONS.map((n) => {
            const href = hrefFor(n);
            const isOn = isPathActive(pathname, href);
            return (
              <Link
                key={n}
                href={href}
                className="mx-3 block border-l-2 py-2 pl-6 pr-3.5 text-[13px]"
                style={
                  isOn
                    ? {
                        color: "var(--color-accent)",
                        fontWeight: 700,
                        borderLeftColor: "var(--color-accent)",
                        background: "color-mix(in srgb, var(--color-accent) 12%, transparent)",
                      }
                    : { borderLeftColor: "var(--color-divider)" }
                }
              >
                {NOTATION_LABEL[n]}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
