import type { Config } from "tailwindcss";

/**
 * Les couleurs pointent vers les variables CSS de `src/app/globals.css`, qui
 * reste la source de vérité de la palette. Conséquence VOULUE : la « feuille »
 * de partition peut repointer ces tokens pour son seul sous-arbre (îlot clair
 * dans une app sombre), et le bloc `@media print` les repointe en noir sur
 * blanc en un seul endroit. Des hex figés ici interdiraient les deux.
 *
 * Contrainte à connaître : une couleur déclarée en `var()` nue ne supporte PAS
 * les modificateurs d'opacité Tailwind (`bg-surface/50`). Le design ne s'en
 * sert jamais — il utilise `opacity` sur l'élément ou `color-mix()` sur la
 * couleur. Faire de même plutôt que d'adopter la gymnastique `<alpha-value>`.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        "surface-2": "var(--color-surface-2)",
        ink: "var(--color-text)",
        accent: "var(--color-accent)",
        "accent-600": "var(--color-accent-600)",
        "accent-700": "var(--color-accent-700)",
        divider: "var(--color-divider)",
        canvas: "var(--canvas)",
        paper: "var(--paper)",
        "paper-ink": "var(--paper-ink)",
        "paper-line": "var(--paper-line)",
        "paper-div": "var(--paper-div)",
        ok: "var(--ok)",
        err: "var(--err)",
      },
      fontFamily: {
        sans: ["var(--font-archivo)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
    },
    /* Dans `theme` et non `theme.extend` : on ÉCRASE l'échelle au lieu de
       l'étendre. Le design est strictement à angles droits (--radius-*: 0px),
       et cet écrasement met à plat les ~100 `rounded*` déjà écrits dans les
       composants — sans les éditer un par un. Les rayons écrits en CSS pur
       ont été neutralisés à la main dans globals.css. */
    borderRadius: {
      none: "0",
      sm: "0",
      DEFAULT: "0",
      md: "0",
      lg: "0",
      xl: "0",
      "2xl": "0",
      "3xl": "0",
      full: "0",
    },
  },
  plugins: [],
};

export default config;
