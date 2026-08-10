/**
 * Glyphes SVG pour la portée custom (StaffEditor).
 * Lit note.type / dots / isRest — pas seulement une noire/soupir générique.
 */

import type { ReactNode } from "react";

export type NoteValueType = "whole" | "half" | "quarter" | "eighth" | "16th";

export const NOTE_VALUE_OPTIONS: {
  type: NoteValueType;
  dots: number;
}[] = [
  { type: "whole", dots: 0 },
  { type: "half", dots: 0 },
  { type: "quarter", dots: 0 },
  { type: "eighth", dots: 0 },
  { type: "16th", dots: 0 },
  { type: "quarter", dots: 1 },
  { type: "eighth", dots: 1 },
];

/** Libellés UI avec symboles musicaux (séparés pour éviter les soucis d'encodage fichier). */
export function noteValueLabel(type: NoteValueType, dots: number): string {
  const base: Record<NoteValueType, string> = {
    whole: "Ronde",
    half: "Blanche",
    quarter: "Noire",
    eighth: "Croche",
    "16th": "Double-croche",
  };
  const sym: Record<NoteValueType, string> = {
    whole: "\uD834\uDD5D",
    half: "\uD834\uDD5E",
    quarter: "\u2669",
    eighth: "\u266A",
    "16th": "\uD834\uDD61",
  };
  const dot = dots > 0 ? ".".repeat(dots) : "";
  return `${sym[type]}${dot} ${base[type]}${dots ? " pointée" : ""}`;
}

function restGlyph(type: string): string {
  switch (type) {
    case "whole":
      return "\uD834\uDD3C"; // musical symbol whole rest
    case "half":
      return "\uD834\uDD3D";
    case "eighth":
      return "\uD834\uDD3F";
    case "16th":
      return "\uD834\uDD40";
    default:
      return "\uD834\uDD3E"; // quarter rest
  }
}

function normalizeType(type: string | undefined): NoteValueType {
  if (type === "whole" || type === "half" || type === "eighth" || type === "16th") {
    return type;
  }
  return "quarter";
}

/** Préfère `type` ; si absent/générique, déduit depuis `duration`. */
export function resolveNoteValue(
  type: string | undefined,
  duration: number | undefined,
  divisions: number,
  dots = 0,
): { type: NoteValueType; dots: number } {
  const d = divisions || 1;
  if (type && type !== "quarter") {
    return { type: normalizeType(type), dots };
  }
  if (type === "quarter" && (duration == null || duration === d || duration === Math.round(d * 1.5))) {
    return { type: "quarter", dots: duration != null && duration > d ? 1 : dots };
  }
  if (duration == null || duration <= 0) {
    return { type: normalizeType(type), dots };
  }
  // Comparer à la durée sans points
  const candidates: Array<[NoteValueType, number]> = [
    ["whole", d * 4],
    ["half", d * 2],
    ["quarter", d],
    ["eighth", Math.max(1, Math.floor(d / 2))],
    ["16th", Math.max(1, Math.floor(d / 4))],
  ];
  for (const [t, base] of candidates) {
    if (duration === base) return { type: t, dots: 0 };
    if (duration === base + Math.floor(base / 2)) return { type: t, dots: 1 };
  }
  // Plus proche
  let best: NoteValueType = "quarter";
  let bestDiff = Infinity;
  for (const [t, base] of candidates) {
    const diff = Math.abs(duration - base);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = t;
    }
  }
  return { type: best, dots };
}

/** Largeur de colonne selon la valeur (espacement approximatif). */
export function noteColumnWidth(type: string | undefined): number {
  switch (normalizeType(type)) {
    case "whole":
      return 44;
    case "half":
      return 34;
    case "eighth":
      return 26;
    case "16th":
      return 24;
    default:
      return 28;
  }
}

function AugmentationDots({
  x,
  y,
  count,
}: {
  x: number;
  y: number;
  count: number;
}) {
  if (count <= 0) return null;
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <circle
          key={i}
          cx={x + 9 + i * 5}
          cy={y}
          r={1.6}
          className="fill-stone-900"
        />
      ))}
    </>
  );
}

function StemAndFlags({
  nx,
  cy,
  type,
  stemUp,
}: {
  nx: number;
  cy: number;
  type: NoteValueType;
  stemUp: boolean;
}) {
  if (type === "whole") return null;
  const stemX = stemUp ? nx + 4.5 : nx - 4.5;
  const stemEnd = stemUp ? cy - 28 : cy + 28;
  const flags = type === "16th" ? 2 : type === "eighth" ? 1 : 0;

  return (
    <>
      <line
        x1={stemX}
        x2={stemX}
        y1={cy}
        y2={stemEnd}
        stroke="#111"
        strokeWidth={1.2}
      />
      {flags >= 1 && (
        <path
          d={
            stemUp
              ? `M ${stemX} ${stemEnd} c 8 4, 10 12, 2 18`
              : `M ${stemX} ${stemEnd} c 8 -4, 10 -12, 2 -18`
          }
          fill="none"
          stroke="#111"
          strokeWidth={1.4}
          strokeLinecap="round"
        />
      )}
      {flags >= 2 && (
        <path
          d={
            stemUp
              ? `M ${stemX} ${stemEnd + 7} c 8 4, 10 12, 2 18`
              : `M ${stemX} ${stemEnd - 7} c 8 -4, 10 -12, 2 -18`
          }
          fill="none"
          stroke="#111"
          strokeWidth={1.4}
          strokeLinecap="round"
        />
      )}
    </>
  );
}

export function StaffRestGlyph({
  nx,
  cy,
  type,
  dots = 0,
}: {
  nx: number;
  cy: number;
  type: string | undefined;
  dots?: number;
}): ReactNode {
  const t = normalizeType(type);
  return (
    <>
      <text
        x={nx}
        y={cy + 5}
        textAnchor="middle"
        className="fill-stone-800"
        fontSize={t === "whole" || t === "half" ? 18 : 16}
      >
        {restGlyph(t)}
      </text>
      <AugmentationDots x={nx + 2} y={cy} count={dots} />
    </>
  );
}

export function StaffNoteGlyph({
  nx,
  cy,
  type,
  dots = 0,
  stemUp = true,
}: {
  nx: number;
  cy: number;
  type: string | undefined;
  dots?: number;
  stemUp?: boolean;
}): ReactNode {
  const t = normalizeType(type);
  const hollow = t === "whole" || t === "half";
  const rx = t === "whole" ? 6.5 : 5;
  const ry = t === "whole" ? 5 : 4;

  return (
    <>
      <ellipse
        cx={nx}
        cy={cy}
        rx={rx}
        ry={ry}
        transform={`rotate(-15 ${nx} ${cy})`}
        className={hollow ? "fill-none stroke-stone-900" : "fill-stone-900"}
        strokeWidth={hollow ? 1.4 : undefined}
      />
      <StemAndFlags nx={nx} cy={cy} type={t} stemUp={stemUp} />
      <AugmentationDots x={nx + (hollow ? 2 : 0)} y={cy} count={dots} />
    </>
  );
}
