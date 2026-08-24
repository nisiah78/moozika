/**
 * Icônes du design : SVG inline écrits à la main, style Feather.
 * Aucune librairie — le design n'en utilise pas, et en ajouter une pour une
 * vingtaine de tracés de 24×24 serait une dépendance pour rien.
 * Les tracés sont repris littéralement de docs/Moozika.html.
 */

export type IconProps = { size?: number; className?: string };

function Svg({ size = 18, className, d, fill }: IconProps & { d: string[]; fill?: boolean }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill ? "currentColor" : "none"}
      stroke={fill ? undefined : "currentColor"}
      strokeWidth={fill ? undefined : 2}
      className={className}
      aria-hidden
    >
      {d.map((p) => (
        <path key={p} d={p} />
      ))}
    </svg>
  );
}

export const IconLibrary = (p: IconProps) => <Svg {...p} d={["M4 4h16v16H4zM9 4v16"]} />;
export const IconChevronDown = (p: IconProps) => <Svg {...p} d={["M6 9l6 6 6-6"]} />;
export const IconUpload = (p: IconProps) => <Svg {...p} d={["M12 15V3M7 8l5-5 5 5M5 15v4h14v-4"]} />;
export const IconBook = (p: IconProps) => (
  <Svg {...p} d={["M4 5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 1-2-2zM9 3v18"]} />
);
export const IconMail = (p: IconProps) => <Svg {...p} d={["M4 5h16v14H4zM4 6l8 6 8-6"]} />;
export const IconPlus = (p: IconProps) => <Svg {...p} d={["M12 5v14M5 12h14"]} />;
export const IconSearch = (p: IconProps) => (
  <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={p.className} aria-hidden>
    <circle cx="11" cy="11" r="7" />
    <path d="M21 21l-4-4" />
  </svg>
);
export const IconRefresh = (p: IconProps) => (
  <Svg {...p} d={["M21 12a9 9 0 1 1-3-6.7L21 8", "M21 3v5h-5"]} />
);
export const IconTrash = (p: IconProps) => (
  <Svg {...p} d={["M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"]} />
);
export const IconArrowRight = (p: IconProps) => <Svg {...p} d={["M5 12h14M13 6l6 6-6 6"]} />;
export const IconArrowLeft = (p: IconProps) => <Svg {...p} d={["M19 12H5M11 6l-6 6 6 6"]} />;
export const IconPencil = (p: IconProps) => (
  <Svg {...p} d={["M11 4H4v16h16v-7M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z"]} />
);
export const IconPlay = (p: IconProps) => <Svg {...p} fill d={["M6 4l14 8-14 8z"]} />;
export const IconPause = (p: IconProps) => <Svg {...p} fill d={["M7 5h4v14H7zM13 5h4v14h-4z"]} />;
export const IconDownload = (p: IconProps) => (
  <Svg {...p} d={["M12 3v12M8 11l4 4 4-4M5 21h14"]} />
);
export const IconSave = (p: IconProps) => <Svg {...p} d={["M5 3h11l3 3v15H5zM8 3v6h8"]} />;
export const IconCheck = (p: IconProps) => <Svg {...p} d={["M4 12l5 5L20 6"]} />;
export const IconClose = (p: IconProps) => <Svg {...p} d={["M6 6l12 12M18 6L6 18"]} />;
export const IconSend = (p: IconProps) => <Svg {...p} d={["M22 2L11 13M22 2l-7 20-4-9-9-4z"]} />;
export const IconInfo = (p: IconProps) => (
  <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={p.className} aria-hidden>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8v.01" />
  </svg>
);
export const IconGear = (p: IconProps) => (
  <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={p.className} aria-hidden>
    <circle cx="12" cy="12" r="3" />
    <path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.3 1a7 7 0 0 0-1.7-1l-.3-2.5H10l-.3 2.5a7 7 0 0 0-1.7 1l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 1.7 1l.3 2.5h3.6l.3-2.5a7 7 0 0 0 1.7-1l2.3 1 2-3.4-2-1.5c.1-.3.1-.7.1-1z" />
  </svg>
);
