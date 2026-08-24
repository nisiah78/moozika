/**
 *   npx tsx src/lib/libraryFilter.test.ts
 */
import assert from "node:assert/strict";
import { filterByNotation, formatUpdated, notationsOf, searchScores, sourceLabel } from "./libraryFilter";
import type { ScoreListItem } from "./scoresApi";

const item = (title: string, sourceType = "solfa"): ScoreListItem => ({
  id: title,
  title,
  tonic: "C",
  sourceType,
  status: "ready",
  version: 1,
  updatedAt: "2026-08-21T14:22:11+00:00",
  createdAt: "2026-08-01T00:00:00+00:00",
});

// ── Recherche ────────────────────────────────────────────────────────────────

const items = [item("JESOA TSY MBA MANDAO"), item("Mivavaha"), item("Ry Tanindrazanay")];
assert.equal(searchScores(items, "").length, 3, "requête vide : tout");
assert.equal(searchScores(items, "   ").length, 3, "espaces seuls : tout");
assert.equal(searchScores(items, "jesoa").length, 1, "insensible à la casse");
assert.equal(searchScores(items, "MIVAVAHA").length, 1);
assert.equal(searchScores(items, "zzz").length, 0, "pas de faux positif");
assert.equal(searchScores(items, "a").length, 3, "sous-chaîne, pas préfixe");
// Les titres malgaches sont accentués : chercher sans accent doit fonctionner,
// et inversement.
assert.equal(searchScores([item("Café")], "cafe").length, 1, "accent plié dans la donnée");
assert.equal(searchScores([item("Cafe")], "café").length, 1, "accent plié dans la requête");
assert.equal(searchScores([item("")], "x").length, 0, "titre vide : pas d'exception");

// ── Regroupement par notation ────────────────────────────────────────────────

assert.deepEqual(notationsOf("solfa"), ["solfa"]);
assert.deepEqual(notationsOf("staff"), ["solfege"]);
assert.deepEqual(notationsOf("musicxml"), ["solfa", "solfege"], "import agnostique : les deux");
assert.deepEqual(notationsOf("inconnu"), ["solfa", "solfege"], "type inconnu : visible partout");

const mixed = [
  ...Array.from({ length: 8 }, (_, i) => item(`s${i}`, "solfa")),
  ...Array.from({ length: 4 }, (_, i) => item(`t${i}`, "staff")),
  item("x0", "musicxml"),
];
const solfa = filterByNotation(mixed, "solfa");
const solfege = filterByNotation(mixed, "solfege");
assert.equal(solfa.length, 9, "8 sol-fa + le MusicXML");
assert.equal(solfege.length, 5, "4 solfège + le MusicXML");
assert.ok(!solfa.some((i) => i.sourceType === "staff"), "aucun solfège dans la liste sol-fa");
assert.ok(!solfege.some((i) => i.sourceType === "solfa"), "aucun sol-fa dans la liste solfège");
// L'invariant qui compte : aucune partition ne peut disparaître des deux listes.
assert.equal(
  new Set([...solfa, ...solfege].map((i) => i.id)).size,
  mixed.length,
  "l'union des deux listes couvre toute la bibliothèque",
);

// ── Étiquettes ───────────────────────────────────────────────────────────────

assert.equal(sourceLabel("solfa"), "PDF sol-fa");
assert.equal(sourceLabel("staff"), "PDF solfège", "« portée » ne nomme plus la notation");
assert.equal(sourceLabel("musicxml"), "MusicXML");
assert.equal(sourceLabel("bizarre"), "bizarre", "valeur inconnue montrée telle quelle");

assert.equal(formatUpdated(undefined), null, "date absente");
assert.equal(formatUpdated("pas-une-date"), null, "date invalide : pas de « Invalid Date »");
assert.ok((formatUpdated("2026-08-21T14:22:11+00:00") ?? "").includes("2026"));

console.log("libraryFilter.test.ts: ok");
