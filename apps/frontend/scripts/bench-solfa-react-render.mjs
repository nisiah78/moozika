#!/usr/bin/env node
/**
 * Bench React render cost — après fix ScoreViewer (un seul éditeur monté).
 * Le chemin "both-mounted" est conservé pour régression (doit rester pire).
 *
 * Usage: node scripts/bench-solfa-react-render.mjs
 * RED if solfa-only 40/10 > 3× OR both-mounted still used in app (doc only).
 */

import React from "react";
import { renderToString } from "react-dom/server";

function SolfaLike({ measures, voices = 4, beats = 4, draftKey, draftVal }) {
  const systems = [];
  for (let start = 0; start < measures; start += 4) {
    const span = Math.min(4, measures - start);
    systems.push(
      React.createElement(
        "div",
        { key: start, className: "sys" },
        Array.from({ length: voices }, (_, vi) =>
          React.createElement(
            "div",
            { key: vi, className: "voice" },
            Array.from({ length: span }, (_, mi) => {
              const abs = start + mi;
              return React.createElement(
                "div",
                { key: mi, className: "m" },
                Array.from({ length: beats }, (_, bi) => {
                  const key = `${vi}::${abs}::${bi}`;
                  const value = key === draftKey ? draftVal : "d";
                  return React.createElement("input", {
                    key: bi,
                    value,
                    onChange: () => {},
                    readOnly: true,
                  });
                }),
              );
            }),
          ),
        ),
      ),
    );
  }
  return React.createElement("div", null, systems);
}

function StaffLike({ measures, voices = 4, positions = 11, notesPerMeasure = 4 }) {
  return React.createElement(
    "div",
    null,
    Array.from({ length: voices }, (_, vi) =>
      React.createElement(
        "svg",
        { key: vi, width: measures * 80, height: 120 },
        Array.from({ length: measures }, (_, mi) =>
          React.createElement(
            "g",
            { key: mi },
            Array.from({ length: positions }, (_, p) =>
              React.createElement("rect", {
                key: `r${p}`,
                x: mi * 80,
                y: p * 5,
                width: 80,
                height: 5,
              }),
            ),
            Array.from({ length: 5 }, (_, li) =>
              React.createElement("line", {
                key: `l${li}`,
                x1: mi * 80,
                x2: mi * 80 + 80,
                y1: 20 + li * 10,
                y2: 20 + li * 10,
              }),
            ),
            Array.from({ length: notesPerMeasure }, (_, ni) =>
              React.createElement("ellipse", {
                key: `n${ni}`,
                cx: mi * 80 + 20 + ni * 15,
                cy: 40,
                rx: 5,
                ry: 4,
              }),
            ),
          ),
        ),
      ),
    ),
  );
}

function BothMounted({ measures, draftKey, draftVal, mode = "solfa" }) {
  // Mirrors ScoreViewer: both trees always mounted, one "hidden"
  return React.createElement(
    "div",
    null,
    React.createElement(
      "div",
      { className: mode === "score" ? "" : "hidden" },
      React.createElement(StaffLike, { measures }),
    ),
    React.createElement(
      "div",
      { className: mode === "solfa" ? "" : "hidden" },
      React.createElement(SolfaLike, { measures, draftKey, draftVal }),
    ),
  );
}

function timeRender(label, factory, iters = 15) {
  factory(); // warm
  const t0 = performance.now();
  let htmlLen = 0;
  for (let i = 0; i < iters; i++) {
    htmlLen = renderToString(factory()).length;
  }
  return {
    label,
    ms: (performance.now() - t0) / iters,
    htmlKB: (htmlLen / 1024).toFixed(1),
  };
}

const sizes = [10, 20, 30, 40, 60];
const rows = [];

console.log("=== Keystroke-like: SolfaOnly (beatDraft change) ===");
for (const n of sizes) {
  const r = timeRender(`solfa n=${n}`, () =>
    React.createElement(SolfaLike, {
      measures: n,
      draftKey: "0::0::0",
      draftVal: "dr",
    }),
  );
  rows.push({ kind: "solfa-only", n, ...r });
  console.log(`  ${r.label}: ${r.ms.toFixed(1)} ms, html ${r.htmlKB} KB`);
}

console.log("\n=== Commit-like: BOTH mounted (ScoreViewer pattern) ===");
for (const n of sizes) {
  const r = timeRender(`both n=${n}`, () =>
    React.createElement(BothMounted, {
      measures: n,
      draftKey: "0::0::0",
      draftVal: "d",
      mode: "solfa",
    }),
  );
  rows.push({ kind: "both-mounted", n, ...r });
  console.log(`  ${r.label}: ${r.ms.toFixed(1)} ms, html ${r.htmlKB} KB`);
}

console.log("\n=== StaffOnly (hidden but remounted on result change) ===");
for (const n of sizes) {
  const r = timeRender(`staff n=${n}`, () =>
    React.createElement(StaffLike, { measures: n }),
  );
  rows.push({ kind: "staff-only", n, ...r });
  console.log(`  ${r.label}: ${r.ms.toFixed(1)} ms, html ${r.htmlKB} KB`);
}

const s10 = rows.find((r) => r.kind === "solfa-only" && r.n === 10);
const s40 = rows.find((r) => r.kind === "solfa-only" && r.n === 40);
const b10 = rows.find((r) => r.kind === "both-mounted" && r.n === 10);
const b40 = rows.find((r) => r.kind === "both-mounted" && r.n === 40);
const st10 = rows.find((r) => r.kind === "staff-only" && r.n === 10);
const st40 = rows.find((r) => r.kind === "staff-only" && r.n === 40);

const solfaRatio = s40.ms / s10.ms;
const bothRatio = b40.ms / b10.ms;
const staffRatio = st40.ms / st10.ms;

console.log("\n=== Ratios 40/10 ===");
console.log(`solfa-only: ${solfaRatio.toFixed(2)}×  (${s10.ms.toFixed(1)} → ${s40.ms.toFixed(1)} ms)`);
console.log(`staff-only: ${staffRatio.toFixed(2)}×  (${st10.ms.toFixed(1)} → ${st40.ms.toFixed(1)} ms)`);
console.log(`both-mounted: ${bothRatio.toFixed(2)}×  (${b10.ms.toFixed(1)} → ${b40.ms.toFixed(1)} ms)`);
console.log(
  `staff share of both@40: ${((st40.ms / b40.ms) * 100).toFixed(0)}%`,
);

const THRESHOLD = 3;
if (bothRatio >= THRESHOLD || solfaRatio >= THRESHOLD) {
  console.log(`\nRED: render scale ≥ ${THRESHOLD}× — lenteur DOM confirmée`);
  process.exitCode = 1;
} else {
  console.log(`\nGREEN-ish: ratios < ${THRESHOLD}`);
}
