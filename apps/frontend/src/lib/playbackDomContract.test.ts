/**
 *   npx tsx src/lib/playbackDomContract.test.ts
 *
 * Le surlignage de lecture et le défilement automatique reposent sur un contrat
 * DOM IMPLICITE : `playbackHighlight.ts` cible des classes et des `data-*` que
 * `SolfaScore.tsx` et `StaffEditor.tsx` émettent, sans qu'aucun type ne relie
 * les deux côtés. Renommer un attribut d'un seul côté casserait le surlignage
 * ET le défilement EN SILENCE — aucun test ne s'en apercevait.
 *
 * Ce test lit les fichiers SOURCE et vérifie que les deux côtés parlent bien la
 * même langue. Ce n'est pas un test de rendu — le runner du projet n'a pas de
 * DOM — mais il attrape exactement la panne qu'on cherche à éviter.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel: string) => readFileSync(join(SRC, rel), "utf8");

const highlight = read("lib/playbackHighlight.ts");
const scroll = read("lib/playbackScroll.ts");
const solfa = read("components/SolfaScore.tsx");
const staff = read("components/StaffEditor.tsx");
const css = read("app/globals.css");

// ── Côté sol-fa ──────────────────────────────────────────────────────────────

assert.ok(highlight.includes(".solfa-beat-group[data-pm="), "le surligneur cible .solfa-beat-group[data-pm]");
assert.ok(solfa.includes('className="solfa-beat-group'), "SolfaScore rend bien la classe .solfa-beat-group");
assert.ok(solfa.includes("data-pm="), "SolfaScore émet data-pm (mesure absolue)");

for (const attr of ["pbf", "pbt"] as const) {
  assert.ok(highlight.includes(`dataset.${attr}`), `le surligneur lit dataset.${attr}`);
  assert.ok(solfa.includes(`data-${attr}=`), `SolfaScore émet data-${attr}`);
}

assert.ok(
  highlight.includes('"solfa-beat-group--playing"'),
  "le surligneur pose la classe de temps joué",
);
assert.ok(
  css.includes(".solfa-beat-group--playing"),
  "globals.css style bien la classe de temps joué — sinon le surlignage est invisible",
);

// ── Côté portée ──────────────────────────────────────────────────────────────

assert.ok(highlight.includes(".staff-measure-cell[data-pm="), "le surligneur cible .staff-measure-cell[data-pm]");
assert.ok(staff.includes("staff-measure-cell"), "StaffEditor rend bien .staff-measure-cell");
assert.ok(staff.includes("data-pm="), "StaffEditor émet data-pm");

assert.ok(highlight.includes("dataset.pulses"), "le surligneur lit dataset.pulses");
assert.ok(staff.includes("data-pulses="), "StaffEditor émet data-pulses");

assert.ok(highlight.includes('".staff-playhead"'), "le surligneur cherche la bande .staff-playhead");
assert.ok(staff.includes("staff-playhead"), "StaffEditor rend bien .staff-playhead");
assert.ok(css.includes(".staff-playhead"), "globals.css positionne .staff-playhead");

// ── Contrat entre le surligneur et le défilement ─────────────────────────────

assert.ok(
  highlight.includes("export interface HighlightTargets"),
  "le surligneur expose les nœuds ciblés",
);
assert.ok(
  scroll.includes("HighlightTargets"),
  "le défilement réutilise ce ciblage au lieu de refaire un querySelectorAll",
);
for (const key of ["solfa", "staff"] as const) {
  assert.ok(
    new RegExp(`targets\\.${key}`).test(scroll),
    `le défilement consomme targets.${key}`,
  );
}

// ── L'impression ne doit jamais montrer le surlignage ─────────────────────────
// C'est une aide écran ; l'oublier laisserait une bande colorée sur le PDF.
const printBlock = css.slice(css.lastIndexOf("@media print"));
assert.ok(printBlock.includes(".solfa-beat-group--playing"), "surlignage sol-fa neutralisé à l'impression");
assert.ok(printBlock.includes(".staff-playhead"), "bande de portée neutralisée à l'impression");

console.log("playbackDomContract.test.ts: ok");
