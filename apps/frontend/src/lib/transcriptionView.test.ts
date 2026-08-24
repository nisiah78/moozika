/**
 *   npx tsx src/lib/transcriptionView.test.ts
 */
import assert from "node:assert/strict";
import { displayName, extOf, toneOf } from "./transcriptionView";
import { ACTIVE_STATUSES, progressView, type Transcription, type TranscriptionStatus } from "./transcriptionsApi";

const job = (o: Partial<Transcription> = {}): Transcription => ({ id: "1", status: "queued", ...o });

// ── Les 5 états de l'API ont tous un libellé ─────────────────────────────────
// La maquette n'en dessine que 4 : « cancelled » existe côté API et aurait
// laissé une ligne sans état.
const ALL: TranscriptionStatus[] = ["queued", "running", "done", "failed", "cancelled"];
const labels = ALL.map((status) => toneOf(job({ status })).label);
assert.deepEqual(labels, ["En file", "Analyse OMR", "Prête", "Échec", "Annulée"]);
for (const status of ALL) {
  assert.ok(toneOf(job({ status })).color.length > 0, `couleur définie pour ${status}`);
}
assert.deepEqual(ACTIVE_STATUSES, ["queued", "running"], "seuls ces deux états sont « en cours »");

// ── Vignette d'extension ─────────────────────────────────────────────────────
assert.equal(extOf("partition.pdf"), "PDF");
assert.equal(extOf("PARTITION.PDF"), "PDF", "insensible à la casse");
assert.equal(extOf("a.mxl"), "MXL");
assert.equal(extOf("a.xml"), "XML");
assert.equal(extOf("a.musicxml"), "XML");
assert.equal(extOf(undefined), "?", "nom absent : pas d'exception");
assert.equal(extOf("sans-extension"), "?");
assert.equal(extOf("dossier.v2/fichier.pdf"), "PDF", "un point dans le chemin ne trompe pas");

// ── Nom affiché ──────────────────────────────────────────────────────────────
assert.equal(displayName(job({ sourceFilename: "mivavaha.pdf" })), "mivavaha");
assert.equal(displayName(job()), "Transcription", "repli quand le nom manque");

// ── La barre indéterminée tombe où le pourcentage MENT ────────────────────────
// Mesuré en conditions réelles : phase `ocr` bloquée à pct=10 pendant deux
// minutes sur un scan mono-page. Afficher ce 10 % ferait passer un traitement
// sain pour un plantage.
assert.equal(progressView(job({ status: "running", phase: "audiveris", pct: 20 })).pct, null);
assert.equal(progressView(job({ status: "running", phase: "ocr", pct: 10 })).pct, null);
assert.equal(progressView(job({ status: "running", phase: "layout", pct: 70 })).pct, 70, "phase mesurable");
assert.equal(progressView(job({ status: "running", phase: "convert", pct: 90 })).pct, 90);
assert.equal(
  progressView(job({ status: "running", phase: "layout", message: "Voix 3/6" })).label,
  "Voix 3/6",
  "le message du serveur prime sur le libellé de phase",
);

console.log("transcriptionView.test.ts: ok");
