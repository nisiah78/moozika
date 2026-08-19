// Runner des tests frontend — Niveau 1 de la porte pré-commit.
//
// Les tests de src/lib/*.test.ts sont écrits en node:assert pur (pas de
// framework). tsx les exécute tels quels : aucune réécriture nécessaire.
//   npm test              → tous les fichiers *.test.ts
//   npm test -- tempo     → seulement ceux dont le chemin contient "tempo"
import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { spawnSync } from "node:child_process";

const ROOT = new URL("..", import.meta.url).pathname;

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules" || entry === ".next") continue;
      out.push(...walk(full));
    } else if (entry.endsWith(".test.ts") || entry.endsWith(".test.tsx")) {
      out.push(full);
    }
  }
  return out;
}

const filter = process.argv.slice(2);
const files = walk(join(ROOT, "src"))
  .filter((f) => filter.length === 0 || filter.some((needle) => f.includes(needle)))
  .sort();

if (files.length === 0) {
  console.error(filter.length ? `Aucun test ne correspond à : ${filter.join(", ")}` : "Aucun test trouvé.");
  process.exit(1);
}

let failed = 0;
for (const file of files) {
  const label = relative(ROOT, file);
  const res = spawnSync("npx", ["tsx", file], { stdio: "inherit", cwd: ROOT });
  if (res.status === 0) {
    console.log(`  ok   ${label}`);
  } else {
    console.error(`  FAIL ${label}`);
    failed += 1;
  }
}

console.log(`\n${files.length - failed}/${files.length} fichiers de test OK`);
process.exit(failed === 0 ? 0 : 1);
