/**
 * Checks purs — exécuter :
 *   node --experimental-strip-types src/lib/solfaScore.test.ts
 */
import assert from "node:assert/strict";
import {
  buildSolfaSystems,
  formatMeasureBeats,
  measuresPerSystemFor,
} from "./solfaScore";
import type { ScoreResult, VoiceModel } from "./types";

const emptyModel: VoiceModel = {
  tonic: "Gb",
  fifths: -6,
  timeSignature: { beats: 4, beatType: 4 },
  divisions: 4,
  clef: "treble",
  tempo: null,
  partName: "S",
  measures: [],
};

const result: ScoreResult = {
  header: {
    title: "Hitahy anao anie ny Tompo",
    tonic: "Gb",
    timeSignature: { beats: 4, beatType: 4 },
    tempo: null,
  },
  voices: [
    {
      name: "Soprano",
      notation: ": : : | : : : .m | m : -.m : m.m : r.m | r : d : - : -.d | m : m : - : m.r",
      model: emptyModel,
    },
    {
      name: "Alto",
      notation: ": : : | : : : | : : : | : : : | : : :",
      model: { ...emptyModel, partName: "A" },
    },
  ],
  musicxml: "",
};

const systems = buildSolfaSystems(result, 4);
assert.equal(systems.length, 2);
assert.equal(systems[0].startNumber, 1);
assert.equal(systems[0].voices.length, 1, "intro : soprano seul");
assert.equal(systems[1].startNumber, 5);
assert.equal(systems[1].voices.length, 1, "alto encore silencieux");

// Dès qu'Alto chante, on le garde même sur un système de silences.
const withEntry: ScoreResult = {
  ...result,
  voices: [
    result.voices[0],
    {
      name: "Alto",
      notation:
        ": : : | : : : | : : : | : : : | m : m : m : m | : : : | : : : | : : :",
      model: { ...emptyModel, partName: "A" },
    },
  ],
};
const afterEntry = buildSolfaSystems(withEntry, 4);
assert.equal(afterEntry[0].voices.length, 1, "système 1 : S seul");
assert.equal(afterEntry[1].voices.length, 2, "système 2 : S+A (A entre)");
assert.equal(afterEntry[1].voices[1].isRestOnly, false);

const formatted = formatMeasureBeats(
  [
    { raw: "m", text: "m" },
    { raw: "-", text: "-" },
    { raw: "-", text: "-" },
    { raw: ".m", text: ".m" },
  ],
  [1, 1, 1, 2],
  4,
);
assert.equal(formatted, "m : - ! - : .m");

assert.equal(measuresPerSystemFor(4), 4);
assert.equal(measuresPerSystemFor(6), 3);

const sixFour: ScoreResult = {
  ...result,
  header: { ...result.header, timeSignature: { beats: 6, beatType: 4 } },
  voices: [
    {
      name: "Soprano",
      notation: ": : : : : : | : : : : : : | : : : : : : | : : : : : : | : : : : : : | : : : : : : | : : : : : :",
      model: emptyModel,
    },
  ],
};
const sixFourSystems = buildSolfaSystems(sixFour);
assert.equal(sixFourSystems.length, 3, "7 mesures en 6/4 → 3+3+1");
assert.equal(sixFourSystems[0].voices[0].measures.length, 3);
assert.equal(sixFourSystems[1].startNumber, 4);

console.log("solfaScore.test.ts: ok");
