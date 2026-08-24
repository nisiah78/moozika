/**
 *   npx tsx src/lib/pianoKeys.test.ts
 */
import assert from "node:assert/strict";
import { BLACK_KEYS, WHITE_KEYS } from "./pianoKeys";

assert.equal(WHITE_KEYS.length, 14, "deux octaves de blanches");
assert.equal(BLACK_KEYS.length, 10, "deux octaves de noires");
assert.equal(WHITE_KEYS[0].note, "C4");
assert.equal(WHITE_KEYS[13].note, "B5");

const blacks = BLACK_KEYS.map((k) => k.note);
assert.deepEqual(
  blacks,
  ["C#4", "D#4", "F#4", "G#4", "A#4", "C#5", "D#5", "F#5", "G#5", "A#5"],
  "disposition réelle d'un clavier",
);
// La règle musicale : pas de touche noire entre mi-fa ni entre si-do.
assert.ok(!blacks.some((n) => n.startsWith("E#")), "aucun mi dièse");
assert.ok(!blacks.some((n) => n.startsWith("B#")), "aucun si dièse");

for (const k of BLACK_KEYS) {
  assert.ok(k.left > 0 && k.left + 5.6 < 100, `${k.note} tient dans le clavier`);
}
assert.deepEqual(
  [...BLACK_KEYS].sort((a, b) => a.left - b.left).map((k) => k.note),
  blacks,
  "les noires sont déjà ordonnées de gauche à droite",
);

// Les noms partent directement au sampler Tone : ils doivent être valides.
for (const n of [...WHITE_KEYS.map((k) => k.note), ...blacks]) {
  assert.match(n, /^[A-G]#?[0-9]$/, `${n} est une note Tone valide`);
}

console.log("pianoKeys.test.ts: ok");
