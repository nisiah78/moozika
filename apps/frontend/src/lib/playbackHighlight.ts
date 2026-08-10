/**
 * Surlignage du temps en cours de lecture — IMPÉRATIF (hors React).
 *
 * Appelé à chaque pulsation depuis le callback Draw de Tone.js. On NE passe PAS
 * par un state React : un setState par temps re-rendrait SolfaScore / StaffEditor
 * (lourds) plusieurs fois par seconde, saturant le thread principal et faisant
 * décrocher l'ordonnanceur audio de Tone (notes déclenchées en retard = lecture
 * hachée / hors tempo). Ici on ne fait qu'un querySelector + classList/style :
 * coût négligeable, le thread reste libre pour l'audio.
 *
 * Les composants rendent une structure STATIQUE avec des data-attributs
 * (`data-pm` = mesure absolue, `data-pbf`/`data-pbt` = plage de temps couverte
 * en sol-fa ; `.staff-measure-cell[data-pm][data-pulses]` + `.staff-playhead`
 * en portée). Le surligneur lit ces attributs pour cibler les bons nœuds.
 */

import type { PlaybackPosition } from "./playback";

const SOLFA_CLASS = "solfa-beat-group--playing";

let shownSolfa: HTMLElement[] = [];
let shownStaff: HTMLElement[] = [];

/** Retire tout surlignage actuellement affiché. */
function clear(): void {
  for (const el of shownSolfa) el.classList.remove(SOLFA_CLASS);
  shownSolfa = [];
  for (const band of shownStaff) band.style.display = "none";
  shownStaff = [];
}

/**
 * Surligne le temps `pos` (ou efface si null). Sûr même si le DOM a changé
 * entre deux appels (nœuds détachés → remove sans effet, on re-cible).
 */
export function applyBeatHighlight(pos: PlaybackPosition | null): void {
  if (typeof document === "undefined") return;
  clear();
  if (!pos) return;

  // ── Sol-fa : cellule(s) de temps de toutes les voix à cette mesure ──────────
  document
    .querySelectorAll<HTMLElement>(`.solfa-beat-group[data-pm="${pos.measure}"]`)
    .forEach((el) => {
      const from = Number(el.dataset.pbf ?? "NaN");
      const to = Number(el.dataset.pbt ?? el.dataset.pbf ?? "NaN");
      if (pos.beat >= from && pos.beat <= to) {
        el.classList.add(SOLFA_CLASS);
        shownSolfa.push(el);
      }
    });

  // ── Portée : bande d'un temps dans la mesure active (chaque portée) ─────────
  document
    .querySelectorAll<HTMLElement>(`.staff-measure-cell[data-pm="${pos.measure}"]`)
    .forEach((cell) => {
      const pulses = Math.max(1, Number(cell.dataset.pulses) || 1);
      const band = cell.querySelector<HTMLElement>(".staff-playhead");
      if (!band) return;
      const bi = Math.min(Math.max(0, pos.beat), pulses - 1);
      band.style.left = `${(bi / pulses) * 100}%`;
      band.style.width = `${(1 / pulses) * 100}%`;
      band.style.display = "block";
      shownStaff.push(band);
    });
}
