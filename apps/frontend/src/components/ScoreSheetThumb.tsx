/**
 * Aperçu « papier » d'une partition : portées schématiques en SVG.
 * Repris de la maquette (viewBox 0 0 100 140, preserveAspectRatio="none" —
 * l'étirement est volontaire, la vignette remplit sa case).
 *
 * Ce n'est PAS un rendu de la partition réelle : produire une vraie miniature
 * demanderait de charger et mettre en page chaque MusicXML de la grille. La
 * graine fait juste varier l'aspect d'une carte à l'autre.
 */
export function ScoreSheetThumb({ lines = 5, seed = 0 }: { lines?: number; seed?: number }) {
  const rows = Array.from({ length: lines }, (_, k) => 22 + k * 26);
  return (
    <svg viewBox="0 0 100 140" preserveAspectRatio="none" width="100%" height="100%" aria-hidden>
      {rows.map((yy, k) => (
        <g key={yy}>
          {/* Barre de titre au-dessus de chaque bloc, largeur variable. */}
          <line
            x1={14}
            y1={yy - 8}
            x2={`${34 + ((seed + k) % 3) * 12}%`}
            y2={yy - 8}
            stroke="var(--paper-line)"
            strokeWidth={2.4}
          />
          {[0, 1, 2, 3, 4].map((l) => (
            <line
              key={l}
              x1={14}
              y1={yy + l * 3.2}
              x2="86%"
              y2={yy + l * 3.2}
              stroke="var(--paper-line)"
              strokeWidth={0.8}
            />
          ))}
        </g>
      ))}
    </svg>
  );
}
