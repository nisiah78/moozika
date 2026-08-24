/**
 *   npx tsx src/lib/navigation.test.ts
 */
import assert from "node:assert/strict";
import { isNotation, isPathActive, notationToMode, ROUTES } from "./navigation";

assert.ok(isNotation("solfa"));
assert.ok(isNotation("solfege"));
assert.ok(!isNotation("portee"), "« portée » n'est pas une notation");
assert.ok(!isNotation(undefined));

assert.equal(notationToMode("solfa"), "solfa");
assert.equal(notationToMode("solfege"), "score", "la vue solfège monte l'éditeur de portée");

assert.equal(ROUTES.library(), "/bibliotheque/solfa", "sol-fa par défaut");
assert.equal(ROUTES.library("solfege"), "/bibliotheque/solfege");
assert.equal(ROUTES.score("abc"), "/partition/abc");
assert.equal(ROUTES.draft(), "/partition/nouveau");

// Actif sur soi-même et sur ses descendants.
assert.ok(isPathActive("/import", "/import"));
assert.ok(isPathActive("/bibliotheque/solfa", "/bibliotheque"));
assert.ok(isPathActive("/apprendre/solfege", "/apprendre"));
// La comparaison porte sur des SEGMENTS : un simple startsWith activerait
// « Importer » sur une future route /importation.
assert.ok(!isPathActive("/importation", "/import"), "pas de correspondance partielle de segment");
assert.ok(!isPathActive("/bibliotheque-old", "/bibliotheque"));
assert.ok(!isPathActive("/contact", "/import"));

console.log("navigation.test.ts: ok");
