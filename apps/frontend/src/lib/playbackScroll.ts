/**
 * Défilement automatique pendant la lecture — « suivi doux en bord de zone ».
 *
 * Rien ne bouge tant que la mesure jouée est confortablement visible ; dès
 * qu'elle approche du bord, le conteneur glisse doucement pour la ramener vers
 * le centre. Ni suivi centré permanent (trop de mouvement), ni saut par page
 * (trop brusque).
 *
 * CONTRAINTE DURE, héritée de playbackHighlight.ts : rien ici ne passe par
 * React. Un rendu par pulsation saturerait le thread principal et ferait
 * décrocher l'ordonnanceur de Tone. Ce module est impératif de bout en bout.
 *
 * Le calcul est SÉPARÉ du DOM : `computeFollowScroll` est une fonction pure,
 * testable sans navigateur (le runner du projet est `tsx` sans DOM), et
 * `followPlaybackScroll` n'est qu'une fine couche de mesure et d'écriture.
 */

import type { HighlightTargets } from "./playbackHighlight";

// ── Calcul pur ───────────────────────────────────────────────────────────────

export interface FollowAxis {
  /** Défilement actuel du conteneur (scrollLeft ou scrollTop). */
  scroll: number;
  /** Longueur visible du conteneur (clientWidth ou clientHeight). */
  viewport: number;
  /** Longueur totale du contenu (scrollWidth ou scrollHeight). */
  content: number;
  /** Début de la cible, en coordonnées de CONTENU. */
  targetStart: number;
  /** Longueur de la cible. */
  targetSize: number;
  /** Marge masquée au début (barre collante, rail). */
  padStart: number;
  /** Marge masquée à la fin (dock piano). */
  padEnd: number;
  /** Zone morte côté début, en fraction de la zone utile. */
  deadStart: number;
  /** Zone morte côté fin, en fraction de la zone utile. */
  deadEnd: number;
  /** Où recentrer : 0.5 = centre exact de la zone utile. */
  anchor: number;
  /** En deçà, on ne bouge pas : évite les micro-saccades. */
  minDelta: number;
}

/**
 * Nouveau défilement à appliquer, ou `null` pour « ne rien faire ».
 */
export function computeFollowScroll(a: FollowAxis): number | null {
  const usable = a.viewport - a.padStart - a.padEnd;
  const maxScroll = Math.max(0, a.content - a.viewport);

  // Rien à défiler (contenu plus court que la vue) ou zone utile dégénérée
  // (les marges mangent tout) : on s'abstient plutôt que de calculer n'importe
  // quoi. C'est aussi ce qui rend le module inoffensif avant toute mise en page.
  if (maxScroll <= 0 || usable <= 0) return null;

  const lo = a.scroll + a.padStart + a.deadStart * usable;
  const hi = a.scroll + a.padStart + usable - a.deadEnd * usable;

  // Confortablement visible : on ne bouge pas. C'est tout l'intérêt de la
  // zone morte — sans elle on recentrerait à chaque mesure.
  if (a.targetStart >= lo && a.targetStart + a.targetSize <= hi) return null;

  const desired =
    a.targetSize > usable
      ? // Cible plus grande que la zone utile (un système entier, une mesure
        // très large) : on ne peut pas la centrer, on aligne son DÉBUT.
        a.targetStart - a.padStart
      : a.targetStart + a.targetSize / 2 - a.padStart - a.anchor * usable;

  const clamped = Math.max(0, Math.min(desired, maxScroll));

  // En bord de partition, le bornage peut ramener à la position actuelle : on
  // renvoie null au lieu de déclencher un défilement de zéro pixel à chaque
  // mesure.
  if (Math.abs(clamped - a.scroll) < a.minDelta) return null;
  return clamped;
}

/**
 * Réglages par défaut.
 *
 * `deadEnd > deadStart` parce que la musique AVANCE : il faut déclencher avant
 * que la mesure ne colle au bord de sortie, alors que le bord d'entrée ne sert
 * qu'aux reprises et aux redémarrages.
 *
 * `anchor < 0.5` : après recentrage, ~62 % de la zone utile montre la musique
 * À VENIR, donc le prochain déclenchement est plus loin — moins de mouvements
 * pour le même confort de lecture.
 */
export const FOLLOW_X: Omit<FollowAxis, "scroll" | "viewport" | "content" | "targetStart" | "targetSize" | "padStart" | "padEnd"> = {
  deadStart: 0.1,
  deadEnd: 0.22,
  anchor: 0.38,
  minDelta: 24,
};

export const FOLLOW_Y: typeof FOLLOW_X = {
  deadStart: 0.12,
  deadEnd: 0.2,
  anchor: 0.35,
  minDelta: 24,
};

// ── Couche DOM ───────────────────────────────────────────────────────────────

type Axis = "x" | "y";

interface Port {
  el: HTMLElement | null; // null = l'élément racine défilant (le document)
  scroll: number;
  viewport: number;
  content: number;
  /** Origine du port en coordonnées écran, pour convertir un rect en contenu. */
  originScreen: number;
  padStart: number;
  padEnd: number;
}

/** Suspension du suivi après une prise en main par l'utilisateur. */
const USER_GRACE_MS = 2500;
let suppressUntil = 0;
let lastMeasure = -1;
let listenersOn = false;

function noteUserIntent(): void {
  suppressUntil = performance.now() + USER_GRACE_MS;
}

/**
 * On écoute l'INTENTION, jamais l'évènement `scroll`.
 *
 * Un défilement programmatique émet lui aussi des `scroll` — en quantité et
 * pendant une durée inconnues avec `behavior: "smooth"`. S'en servir pour
 * détecter l'utilisateur reviendrait à se suspendre soi-même. `wheel`,
 * `touchstart`, `pointerdown` et les touches de navigation, eux, ne sont jamais
 * synthétisés par un scroll programmatique : zéro faux positif par construction.
 */
const NAV_KEYS = new Set([
  "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
  "PageUp", "PageDown", "Home", "End", " ",
]);

function onKey(e: KeyboardEvent): void {
  if (NAV_KEYS.has(e.key)) noteUserIntent();
}

function attachListeners(): void {
  if (listenersOn || typeof window === "undefined") return;
  listenersOn = true;
  const opts = { passive: true, capture: true } as const;
  window.addEventListener("wheel", noteUserIntent, opts);
  window.addEventListener("touchstart", noteUserIntent, opts);
  window.addEventListener("pointerdown", noteUserIntent, opts);
  window.addEventListener("keydown", onKey, opts);
}

function detachListeners(): void {
  if (!listenersOn || typeof window === "undefined") return;
  listenersOn = false;
  const opts = { capture: true } as const;
  window.removeEventListener("wheel", noteUserIntent, opts);
  window.removeEventListener("touchstart", noteUserIntent, opts);
  window.removeEventListener("pointerdown", noteUserIntent, opts);
  window.removeEventListener("keydown", onKey, opts);
}

/** Marges masquées, déclarées en CSS et jamais codées en dur ici. */
function safeMargins(el: HTMLElement | null, axis: Axis): { padStart: number; padEnd: number } {
  const target = el ?? document.documentElement;
  const cs = getComputedStyle(target);
  const root = getComputedStyle(document.documentElement);
  const px = (v: string) => {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n : 0;
  };
  // `scroll-padding-*` est LA propriété standard qui déclare la « région de
  // visualisation optimale » d'un conteneur défilant. Le repli par variables
  // permet de la poser sans toucher au conteneur lui-même.
  if (axis === "x") {
    return {
      padStart: px(cs.scrollPaddingLeft) || px(root.getPropertyValue("--playback-safe-left")),
      padEnd: px(cs.scrollPaddingRight) || px(root.getPropertyValue("--playback-safe-right")),
    };
  }
  return {
    padStart: px(cs.scrollPaddingTop) || px(root.getPropertyValue("--playback-safe-top")),
    padEnd: px(cs.scrollPaddingBottom) || px(root.getPropertyValue("--playback-safe-bottom")),
  };
}

/**
 * Remonte les ancêtres jusqu'au premier conteneur RÉELLEMENT défilant.
 *
 * Le test est CONJOINT — overflow ET débordement effectif — et le second est
 * obligatoire : `.solfa-score` déclare `overflow-x: auto` sans contrainte de
 * hauteur, donc son `overflow-y` calculé vaut `auto` alors que son contenu ne
 * déborde pas verticalement. Un détecteur qui ne regarderait que l'overflow
 * l'élirait comme conteneur vertical, et le sol-fa ne défilerait JAMAIS.
 */
function resolveScrollPort(from: Element, axis: Axis): HTMLElement | null {
  for (let el = from.parentElement; el; el = el.parentElement) {
    if (el.hasAttribute("data-playback-scroll-port")) return el;
    const cs = getComputedStyle(el);
    const ov = axis === "x" ? cs.overflowX : cs.overflowY;
    const over =
      axis === "x" ? el.scrollWidth - el.clientWidth : el.scrollHeight - el.clientHeight;
    if ((ov === "auto" || ov === "scroll") && over > 1) return el;
  }
  return null; // le document
}

function readPort(el: HTMLElement | null, axis: Axis): Port {
  const pads = safeMargins(el, axis);
  if (!el) {
    const doc = document.documentElement;
    return {
      el: null,
      scroll: axis === "x" ? window.scrollX : window.scrollY,
      viewport: axis === "x" ? doc.clientWidth : doc.clientHeight,
      content: axis === "x" ? doc.scrollWidth : doc.scrollHeight,
      originScreen: 0,
      ...pads,
    };
  }
  const r = el.getBoundingClientRect();
  return {
    el,
    scroll: axis === "x" ? el.scrollLeft : el.scrollTop,
    viewport: axis === "x" ? el.clientWidth : el.clientHeight,
    content: axis === "x" ? el.scrollWidth : el.scrollHeight,
    // `clientLeft/Top` retire l'épaisseur de bordure : sans ça la cible serait
    // décalée de la bordure du conteneur.
    originScreen: (axis === "x" ? r.left + el.clientLeft : r.top + el.clientTop),
    ...pads,
  };
}

/** Étendue écran d'un groupe de nœuds, réunie sur un axe. */
function unionExtent(els: HTMLElement[], axis: Axis): { start: number; size: number } | null {
  let min = Infinity;
  let max = -Infinity;
  for (const el of els) {
    const r = el.getBoundingClientRect();
    const s = axis === "x" ? r.left : r.top;
    const e = axis === "x" ? r.right : r.bottom;
    if (s < min) min = s;
    if (e > max) max = e;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
  return { start: min, size: Math.max(0, max - min) };
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function applyScroll(port: Port, axis: Axis, value: number): void {
  const behavior: ScrollBehavior = prefersReducedMotion() ? "auto" : "smooth";
  const opts: ScrollToOptions =
    axis === "x" ? { left: value, behavior } : { top: value, behavior };

  // Le smooth natif est exécuté par le navigateur : ZÉRO travail JS par frame,
  // donc aucune concurrence avec la boucle rAF de Tone. Une interpolation
  // maison écrirait scrollLeft 60 fois par seconde — précisément ce que
  // playbackHighlight.ts proscrit.
  const supportsSmooth =
    typeof document !== "undefined" && "scrollBehavior" in document.documentElement.style;

  if (port.el) {
    if (supportsSmooth) port.el.scrollTo(opts);
    else if (axis === "x") port.el.scrollLeft = value;
    else port.el.scrollTop = value;
    return;
  }
  if (supportsSmooth) window.scrollTo(opts);
  else if (axis === "x") window.scrollTo(value, window.scrollY);
  else window.scrollTo(window.scrollX, value);
}

function follow(els: HTMLElement[], axis: Axis, tuning: typeof FOLLOW_X): void {
  if (els.length === 0) return;
  const port = readPort(resolveScrollPort(els[0], axis), axis);
  const extent = unionExtent(els, axis);
  if (!extent) return;

  // Écran → contenu.
  const targetStart = extent.start - port.originScreen + port.scroll;

  const next = computeFollowScroll({
    scroll: port.scroll,
    viewport: port.viewport,
    content: port.content,
    targetStart,
    targetSize: extent.size,
    padStart: port.padStart,
    padEnd: port.padEnd,
    ...tuning,
  });
  if (next === null) return;
  applyScroll(port, axis, next);
}

/**
 * Suit la lecture. Appelé à chaque temps, mais n'AGIT qu'au changement de
 * mesure : la cible ne bouge pas pendant une mesure, donc évaluer à chaque
 * pulsation donnerait toujours la même réponse. Bénéfice : au plus un
 * défilement animé à la fois, et une seule lecture de géométrie par seconde.
 */
export function followPlaybackScroll(targets: HighlightTargets, measure: number): void {
  if (typeof window === "undefined") return;
  attachListeners();

  if (measure === lastMeasure) return;
  lastMeasure = measure;

  if (performance.now() < suppressUntil) return;

  if (targets.staff.length > 0) {
    // Portée : une seule bande horizontale, toutes les voix partagent la même
    // grille — l'axe X porte le suivi. L'axe Y ne sert que si la pile de voix
    // déborde en hauteur.
    follow(targets.staff, "x", FOLLOW_X);
    follow(targets.staff, "y", FOLLOW_Y);
  } else if (targets.solfa.length > 0) {
    // Sol-fa : les systèmes sont paginés verticalement, c'est l'axe Y qui
    // compte. L'union des cellules surlignées couvre exactement les rangées de
    // voix jouées — ni la rangée de directives, ni celle d'ajout de voix.
    follow(targets.solfa, "y", FOLLOW_Y);
    follow(targets.solfa, "x", FOLLOW_X);
  }
}

/** Fin de lecture : on oublie tout, la prochaine repart proprement. */
export function resetPlaybackScroll(): void {
  lastMeasure = -1;
  suppressUntil = 0;
  detachListeners();
}
