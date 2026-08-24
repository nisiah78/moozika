/**
 * Disposition du clavier du dock : 2 octaves, 14 blanches et 10 noires.
 * Géométrie reprise de la maquette (les noires sont posées en absolu, à
 * `left = unité × (index_blanche + 1) − 2,8 %`, largeur 5,6 %).
 *
 * Les noms sont de la notation Tone (« C4 », « F#4 ») : le sampler Salamander
 * les comprend directement, aucune table de fréquences à maintenir.
 */

export interface WhiteKey {
  /** Nom Tone, ex. "C4". */
  note: string;
  /** Étiquette affichée en bas de touche. */
  label: string;
}

export interface BlackKey {
  note: string;
  /** Pourcentage depuis la gauche du clavier. */
  left: number;
}

const WHITE_STEPS = ["C", "D", "E", "F", "G", "A", "B"] as const;

/** Index des blanches SUIVIES d'une noire (pas de noire après E ni B). */
const BLACK_AFTER = [0, 1, 3, 4, 5, 7, 8, 10, 11, 12];

export const WHITE_KEYS: WhiteKey[] = Array.from({ length: 14 }, (_, i) => {
  const octave = 4 + Math.floor(i / 7);
  const step = WHITE_STEPS[i % 7];
  return { note: `${step}${octave}`, label: `${step}${octave}` };
});

const BLACK_WIDTH = 5.6;

export const BLACK_KEYS: BlackKey[] = BLACK_AFTER.map((wi) => {
  const unit = 100 / WHITE_KEYS.length;
  const white = WHITE_KEYS[wi];
  return {
    // La noire qui suit une blanche est son dièse.
    note: `${white.note[0]}#${white.note.slice(1)}`,
    left: unit * (wi + 1) - BLACK_WIDTH / 2,
  };
});
