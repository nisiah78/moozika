#!/usr/bin/env node
/**
 * Feedback loop: mesure le coût d'édition sol-fa vs taille (mesures).
 * Simule le chemin commit de SolfaScore.publishParsed :
 *   pour chaque voix: parseSolfaNotation → puis regenerateFromModels (model-to-musicxml)
 * + coûts CPU locaux (clone JSON, rebuild notation, cascade, build systems).
 *
 * Usage: node scripts/bench-solfa-edit.mjs
 * Exit 1 si le ratio 40/10 mesures du commit dépasse le seuil (régression nette).
 */

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080").replace(/\/$/, "");

const VOICES = [
  { name: "Soprano", clef: "treble" },
  { name: "Alto", clef: "treble" },
  { name: "Tenor", clef: "treble" },
  { name: "Bass", clef: "bass" },
];

function measureNotation(n) {
  // 4/4 : d : r : m : f
  const cell = "d : r : m : f";
  return Array.from({ length: n }, () => cell).join(" | ");
}

function gridFor(n, bpm = 4) {
  return Array.from({ length: n }, () => Array.from({ length: bpm }, (_, i) => "drmf"[i]));
}

function rebuildVoiceNotation(measures, beatsPerMeasure = 4) {
  return measures
    .map((beats) => {
      const padded = [...beats];
      while (padded.length < beatsPerMeasure) padded.push("");
      const mid = Math.floor(beatsPerMeasure / 2);
      const parts = [];
      for (let i = 0; i < beatsPerMeasure; i++) {
        parts.push(padded[i].trim());
        if (i < beatsPerMeasure - 1) parts.push(i + 1 === mid ? "!" : ":");
      }
      return parts.join(" ");
    })
    .join(" | ");
}

function analyzeBeatFill(raw, beatDiv = 4) {
  const text = raw.replace(/\s+/g, " ").trim();
  if (text === "") return { status: "ok" };
  if (/\s/.test(text)) return { status: "over" };
  return { status: "ok" };
}

function errorsForVoice(voiceName, grid) {
  const out = {};
  grid.forEach((measure, mi) => {
    measure.forEach((beat, bi) => {
      const fill = analyzeBeatFill(beat);
      out[`${voiceName}::${mi}::${bi}`] =
        fill.status === "under" || fill.status === "over" || fill.status === "invalid";
    });
  });
  return out;
}

function buildSystems(notationByVoice, mps = 4) {
  const parsed = Object.values(notationByVoice).map((n) =>
    n.split("|").map((m) => m.trim()).filter(Boolean),
  );
  const nMeasures = Math.max(...parsed.map((p) => p.length));
  const systems = [];
  for (let start = 0; start < nMeasures; start += mps) {
    systems.push({ start: start + 1, span: Math.min(mps, nMeasures - start) });
  }
  return systems;
}

function bench(label, fn, iters = 50) {
  // warm
  fn();
  const t0 = performance.now();
  for (let i = 0; i < iters; i++) fn();
  const ms = (performance.now() - t0) / iters;
  return { label, msPerCall: ms, iters };
}

async function apiJson(path, body) {
  const t0 = performance.now();
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  const ms = performance.now() - t0;
  if (!res.ok) throw new Error(`${path} ${res.status}: ${data.detail || JSON.stringify(data)}`);
  return { ms, data };
}

async function simulateCommit(measureCount) {
  const notation = measureNotation(measureCount);
  const parseTimes = [];
  const models = [];

  for (const v of VOICES) {
    const { ms, data } = await apiJson("/convert/solfa-parse", {
      notation,
      tonic: "C",
      clef: v.clef,
      doh_octave: 4,
      beats: 4,
      beat_type: 4,
    });
    parseTimes.push(ms);
    models.push(data.model);
  }

  const regen = await apiJson("/convert/model-to-musicxml", {
    models,
    title: `bench-${measureCount}`,
  });

  const parseTotal = parseTimes.reduce((a, b) => a + b, 0);
  return {
    measureCount,
    parseMs: parseTimes,
    parseTotalMs: parseTotal,
    regenMs: regen.ms,
    commitTotalMs: parseTotal + regen.ms,
    musicxmlBytes: (regen.data.musicxml || "").length,
    modelJsonBytes: JSON.stringify(models).length,
    inputCountEstimate: measureCount * 4 /*voices*/ * 4 /*beats*/ + measureCount * 4 /*lyrics*/,
    staffSvgGroupsEstimate: measureCount * 4 /*voices*/,
  };
}

async function main() {
  const sizes = [10, 20, 30, 40, 60];
  console.log(`API=${API}`);
  console.log("\n=== CPU local (synchrone, chemin keystroke / re-render) ===");

  const cpuRows = [];
  for (const n of sizes) {
    const grids = Object.fromEntries(
      VOICES.map((v) => [v.name, gridFor(n)]),
    );
    const notations = Object.fromEntries(
      VOICES.map((v) => [v.name, rebuildVoiceNotation(grids[v.name])]),
    );
    const fakeScore = {
      header: { title: "x", tonic: "C", timeSignature: { beats: 4, beatType: 4 } },
      voices: VOICES.map((v) => ({
        name: v.name,
        notation: notations[v.name],
        model: {
          tonic: "C",
          clef: v.clef,
          divisions: 1,
          measures: Array.from({ length: n }, () => ({
            notes: [
              { isRest: false, duration: 1, type: "quarter", pitch: { step: "C", alter: 0, octave: 4 } },
              { isRest: false, duration: 1, type: "quarter", pitch: { step: "D", alter: 0, octave: 4 } },
              { isRest: false, duration: 1, type: "quarter", pitch: { step: "E", alter: 0, octave: 4 } },
              { isRest: false, duration: 1, type: "quarter", pitch: { step: "F", alter: 0, octave: 4 } },
            ],
          })),
        },
      })),
      musicxml: "<stub/>",
    };

    const clone = bench(`cloneScore n=${n}`, () => JSON.parse(JSON.stringify(fakeScore)), 30);
    const rebuild = bench(
      `rebuild×4 n=${n}`,
      () => VOICES.forEach((v) => rebuildVoiceNotation(grids[v.name])),
      100,
    );
    const errors = bench(
      `beatErrors×4 n=${n}`,
      () => VOICES.forEach((v) => errorsForVoice(v.name, grids[v.name])),
      100,
    );
    const systems = bench(`buildSystems n=${n}`, () => buildSystems(notations), 200);
    const inputs = n * 4 * 4 + n * 4;
    cpuRows.push({
      n,
      cloneMs: clone.msPerCall,
      rebuildMs: rebuild.msPerCall,
      errorsMs: errors.msPerCall,
      systemsMs: systems.msPerCall,
      inputs,
      jsonKB: (JSON.stringify(fakeScore).length / 1024).toFixed(1),
    });
  }

  console.table(
    cpuRows.map((r) => ({
      measures: r.n,
      "cloneScore ms": r.cloneMs.toFixed(3),
      "rebuild×4 ms": r.rebuildMs.toFixed(3),
      "beatErrors ms": r.errorsMs.toFixed(3),
      "systems ms": r.systemsMs.toFixed(3),
      inputs: r.inputs,
      "score JSON KB": r.jsonKB,
    })),
  );

  console.log("\n=== Commit réseau (publishParsed : 4× parse + 1× model-to-musicxml) ===");
  const commitRows = [];
  for (const n of sizes) {
    process.stdout.write(`  measuring commit n=${n}… `);
    const row = await simulateCommit(n);
    console.log(`${row.commitTotalMs.toFixed(0)} ms`);
    commitRows.push(row);
  }

  console.table(
    commitRows.map((r) => ({
      measures: r.measureCount,
      "parse×4 ms": r.parseTotalMs.toFixed(0),
      "regen ms": r.regenMs.toFixed(0),
      "commit total ms": r.commitTotalMs.toFixed(0),
      "musicxml KB": (r.musicxmlBytes / 1024).toFixed(1),
      "models KB": (r.modelJsonBytes / 1024).toFixed(1),
      "solfa inputs": r.inputCountEstimate,
    })),
  );

  const c10 = commitRows.find((r) => r.measureCount === 10);
  const c40 = commitRows.find((r) => r.measureCount === 40);
  const ratio = c40.commitTotalMs / c10.commitTotalMs;
  console.log(`\nRatio commit 40/10 mesures = ${ratio.toFixed(2)}×`);
  console.log(
    `CPU beatErrors 40/10 = ${(cpuRows.find((r) => r.n === 40).errorsMs / cpuRows.find((r) => r.n === 10).errorsMs).toFixed(2)}×`,
  );
  console.log(
    `Inputs 40 vs 10 = ${cpuRows.find((r) => r.n === 40).inputs} vs ${cpuRows.find((r) => r.n === 10).inputs}`,
  );

  // Verdict feedback-loop : rouge si commit 40 mesures > 2.5× commit 10
  // (symptôme utilisateur : édition nettement plus lente au-delà de ~30 mesures)
  const THRESHOLD = 2.5;
  if (ratio >= THRESHOLD) {
    console.log(
      `\nRED: commit scale ${ratio.toFixed(2)}× ≥ ${THRESHOLD} — lenteur confirmée sur chemin blur/commit`,
    );
    process.exitCode = 1;
  } else {
    console.log(
      `\nGREEN-ish on network alone (${ratio.toFixed(2)}× < ${THRESHOLD}) — chercher aussi re-render DOM / StaffEditor caché`,
    );
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
