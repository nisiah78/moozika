/**
 *   npx tsx src/lib/beatAnnotations.test.ts
 */
import assert from "node:assert/strict";
import {
  applyBeatAnnotation,
  beatOffsetDivisions,
  globalChipsForBeat,
  removeBeatAnnotationChip,
} from "./beatAnnotations";
import type { ScoreResult } from "./types";

const score: ScoreResult = {
  header: {
    title: "t",
    tonic: "C",
    timeSignature: { beats: 4, beatType: 4 },
    tempo: 120,
  },
  voices: [
    {
      name: "Soprano",
      notation: "d : r : m : f",
      model: {
        tonic: "C",
        fifths: 0,
        timeSignature: { beats: 4, beatType: 4 },
        divisions: 4,
        clef: "treble",
        tempo: 120,
        partName: "S",
        measures: [{ number: 1, notes: [] }],
      },
    },
  ],
  musicxml: "",
};

assert.equal(beatOffsetDivisions(score.voices[0].model, 0, 0), 0);
assert.equal(beatOffsetDivisions(score.voices[0].model, 0, 2), 8);

const withF = applyBeatAnnotation(score, "Soprano", 0, 1, {
  id: "dynamics",
  level: "f",
});
assert.ok(
  withF.voices.every((v) =>
    v.model.measures[0].directions?.some((d) => d.kind === "dynamics" && d.value === "f"),
  ),
);

const m0 = withF.voices[0].model.measures[0];
const chips = globalChipsForBeat(m0, withF.voices[0].model, 0, 1);
assert.equal(chips.length, 1);
assert.equal(chips[0].label, "f");

const removed = removeBeatAnnotationChip(withF, "Soprano", 0, chips[0]);
assert.equal(removed.voices[0].model.measures[0].directions?.length ?? 0, 0);

console.log("beatAnnotations.test.ts: ok");
