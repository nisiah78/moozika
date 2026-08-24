/**
 *   npx tsx src/lib/playbackScroll.test.ts
 *
 * Le suivi de lecture « doux en bord de zone ». Seule la fonction PURE est
 * testée : la couche DOM (résolution du conteneur, mesure, scrollTo) demande un
 * navigateur, que le runner du projet n'a pas.
 */
import assert from "node:assert/strict";
import { computeFollowScroll, FOLLOW_X, type FollowAxis } from "./playbackScroll";

const axis = (o: Partial<FollowAxis> = {}): FollowAxis => ({
  scroll: 0,
  viewport: 1000,
  content: 5000,
  targetStart: 0,
  targetSize: 100,
  padStart: 0,
  padEnd: 0,
  ...FOLLOW_X,
  ...o,
});

// ── Cas où l'on ne doit rien faire ───────────────────────────────────────────

assert.equal(computeFollowScroll(axis({ content: 800 })), null, "contenu plus court que la vue");
assert.equal(computeFollowScroll(axis({ content: 1000 })), null, "contenu égal à la vue");
assert.equal(
  computeFollowScroll(axis({ padStart: 600, padEnd: 600 })),
  null,
  "marges plus grandes que la vue : zone utile nulle",
);
assert.equal(
  computeFollowScroll(axis({ targetStart: 400 })),
  null,
  "cible au milieu : c'est le cas nominal, on ne bouge pas",
);

// ── Déclenchement et recentrage ──────────────────────────────────────────────
// usable = 1000 ; bord de sortie = 1000 − 0,22 × 1000 = 780.

assert.equal(
  computeFollowScroll(axis({ targetStart: 800 })),
  470,
  "cible au-delà du bord : recentrage à l'ancre (800 + 50 − 0,38 × 1000)",
);

// L'hystérésis est la propriété qui distingue ce comportement d'un recentrage
// permanent : après un défilement, la cible retombe dans la zone morte.
assert.equal(
  computeFollowScroll(axis({ scroll: 470, targetStart: 800 })),
  null,
  "après recentrage, plus aucun déclenchement",
);

// ── Bornage aux extrémités ───────────────────────────────────────────────────

assert.equal(computeFollowScroll(axis({ targetStart: 4950 })), 4000, "borné à maxScroll");
assert.equal(
  computeFollowScroll(axis({ scroll: 3000, targetStart: 100 })),
  0,
  "reprise en arrière (D.C., redémarrage) : remonte, borné à 0",
);

// ── Cible plus grande que la zone utile ──────────────────────────────────────

assert.equal(
  computeFollowScroll(axis({ targetStart: 2000, targetSize: 1500 })),
  2000,
  "on ne peut pas centrer : aligne le début, pour voir l'attaque",
);

// ── Marges masquées (le dock piano mange le bas de la vue) ───────────────────
// padEnd = 300 → usable = 700 ; bord de sortie = 700 − 0,22 × 700 = 546.

assert.equal(
  computeFollowScroll(axis({ targetStart: 400, padEnd: 300 })),
  null,
  "[400,500] tient sous le dock",
);
assert.ok(
  computeFollowScroll(axis({ targetStart: 500, padEnd: 300 })) !== null,
  "[500,600] passerait derrière le dock : on défile",
);
assert.equal(
  computeFollowScroll(axis({ targetStart: 500 })),
  null,
  "sans dock, la MÊME cible reste tranquille — la marge est bien prise en compte",
);

// ── Anti-saccade ─────────────────────────────────────────────────────────────

assert.equal(
  computeFollowScroll(axis({ scroll: 469, targetStart: 800 })),
  null,
  "déplacement sous minDelta : on s'abstient",
);

console.log("playbackScroll.test.ts: ok");
