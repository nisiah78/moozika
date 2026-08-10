/**
 *   npx tsx src/lib/tempo.test.ts
 */
import assert from "node:assert/strict";
import {
  defaultTempoSettings,
  resolveQuarterBpm,
  tempoFromOptionId,
} from "./tempo";
import type { ScoreResult } from "./types";

const base: ScoreResult = {
  header: {
    title: "t",
    tonic: "C",
    timeSignature: { beats: 4, beatType: 4 },
    tempo: 120,
  },
  voices: [],
  musicxml: "",
};

assert.equal(resolveQuarterBpm({ bpm: 120, beatUnit: 4, dotted: false }), 120);
assert.equal(resolveQuarterBpm({ bpm: 120, beatUnit: 8, dotted: false }), 60);
assert.equal(resolveQuarterBpm({ bpm: 90, beatUnit: 4, dotted: true }), 135);
assert.equal(resolveQuarterBpm({ bpm: 60, beatUnit: 2, dotted: false }), 120);

const sixEight = defaultTempoSettings({
  ...base,
  header: {
    ...base.header,
    timeSignature: { beats: 6, beatType: 8 },
    tempo: 72,
  },
});
assert.equal(sixEight.beatUnit, 8);
assert.equal(sixEight.dotted, false);
assert.equal(sixEight.bpm, 72);

const saved = defaultTempoSettings({
  ...base,
  header: {
    ...base.header,
    tempo: 88,
    tempoBeatUnit: 8,
    tempoDotted: true,
  },
});
assert.deepEqual(saved, { bpm: 88, beatUnit: 8, dotted: true });

assert.deepEqual(tempoFromOptionId("eighth", 100), {
  bpm: 100,
  beatUnit: 8,
  dotted: false,
});

console.log("tempo.test.ts: ok");
