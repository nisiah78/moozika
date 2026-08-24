/**
 *   npx tsx src/lib/contactMailto.test.ts
 */
import assert from "node:assert/strict";
import { buildContactMailto, CONTACT_ADDRESS } from "./contactMailto";

const url = buildContactMailto({
  from: "vous@exemple.com",
  subject: "Sujet & test",
  message: "Ligne 1\nLigne 2 é",
});

assert.ok(url.startsWith(`mailto:${CONTACT_ADDRESS}?`));
// URLSearchParams encode l'espace en « + », que les clients mail n'interprètent
// PAS dans un corps de message : le remplacement par %20 est indispensable.
assert.ok(!url.includes("+"), "aucun + résiduel");
assert.ok(url.includes("%0A"), "retours à la ligne encodés");
assert.ok(url.includes("Sujet%20%26%20test"), "espaces et esperluette encodés");
assert.ok(url.includes("R%C3%A9pondre%20%C3%A0"), "adresse de réponse reportée dans le corps");

const minimal = buildContactMailto({ from: "", subject: "", message: "coucou" });
assert.ok(minimal.includes("subject=Message%20depuis%20moozika"), "sujet par défaut");
assert.ok(!minimal.includes("R%C3%A9pondre"), "sans adresse, pas de bloc réponse");

console.log("contactMailto.test.ts: ok");
