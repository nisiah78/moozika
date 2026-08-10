/**
 *   npx tsx src/lib/triplets.test.ts
 */
import assert from "node:assert/strict";
import {
  applyTriplet,
  canChooseTwoBeatTriplet,
  expandGridSlotsForTriplets,
  hideBeatSeparatorAfter,
  isLastBeatOfMeasure,
  mergeTripletBeatRaw,
  removeTripletAt,
  tripletPlusAction,
  tripletRoleAt,
} from "./triplets";
import { rebuildVoiceNotation } from "./scoreEdit";
import { analyzeTripletFill, normalizeGridCascade } from "./solfaRhythmEdit";
import type { ScoreResult } from "./types";

const score: ScoreResult = {
  header: {
    title: "t",
    tonic: "C",
    timeSignature: { beats: 4, beatType: 4 },
    tempo: null,
  },
  voices: [
    {
      name: "Soprano",
      notation: "",
      model: {
        tonic: "C",
        fifths: 0,
        timeSignature: { beats: 4, beatType: 4 },
        divisions: 4,
        clef: "treble",
        tempo: null,
        partName: "S",
        measures: [{ number: 1, notes: [] }, { number: 2, notes: [] }],
      },
    },
  ],
  musicxml: "",
};

const sched = [4, 4];

assert.equal(isLastBeatOfMeasure(0, 3, sched), true);
assert.equal(canChooseTwoBeatTriplet(0, 3, sched), false);
assert.equal(tripletPlusAction(undefined, 0, 3, sched), "apply-one");
assert.equal(tripletPlusAction(undefined, 0, 1, sched), "pick");

const one = applyTriplet(score, "Soprano", 0, 1, 1, sched);
assert.equal(one.voices[0].model.triplets?.length, 1);
assert.equal(one.voices[0].model.triplets?.[0].spanBeats, 1);
assert.equal(tripletRoleAt(one.voices[0].model.triplets, 0, 1), "single");
assert.equal(hideBeatSeparatorAfter(one.voices[0].model.triplets, 0, 1), false);

const two = applyTriplet(score, "Soprano", 0, 1, 2, sched);
assert.equal(two.voices[0].model.triplets?.[0].spanBeats, 2);
assert.equal(tripletRoleAt(two.voices[0].model.triplets, 0, 1), "start");
assert.equal(tripletRoleAt(two.voices[0].model.triplets, 0, 2), "end");
assert.equal(tripletRoleAt(two.voices[0].model.triplets, 0, 3), null);
assert.equal(hideBeatSeparatorAfter(two.voices[0].model.triplets, 0, 1), true);
assert.equal(hideBeatSeparatorAfter(two.voices[0].model.triplets, 0, 2), false);

const forced = applyTriplet(score, "Soprano", 0, 3, 2, sched);
assert.equal(forced.voices[0].model.triplets?.[0].spanBeats, 1);

const removed = removeTripletAt(two, "Soprano", 0, 1);
assert.equal(removed.voices[0].model.triplets?.length ?? 0, 0);

assert.equal(
  tripletPlusAction(two.voices[0].model.triplets, 0, 1, sched),
  "remove",
);

assert.equal(mergeTripletBeatRaw("d", "rm"), "drm");
assert.equal(analyzeTripletFill("drm", 2, 4).status, "ok");
assert.equal(analyzeTripletFill("drm", 1, 4).status, "ok");
assert.equal(analyzeTripletFill("d.r.m", 1, 4).status, "invalid");
assert.equal(analyzeTripletFill("dr", 1, 4).status, "under");
assert.equal(analyzeTripletFill("drmf", 1, 4).status, "over");
assert.equal(analyzeTripletFill("d,rm", 1, 4).status, "ok");

const twoSpan = applyTriplet(score, "Soprano", 0, 0, 2, sched);
const triplets = twoSpan.voices[0].model.triplets!;
const grid = [["drm", "", "f", "s"]];
assert.equal(
  rebuildVoiceNotation(grid, 4, undefined, triplets),
  "drm : f ! s",
);

// Pas d'auto-correction : drm reste intact sous triolet
const cascaded = normalizeGridCascade([["drm", "", "f", "s"]], 4, 4, triplets);
assert.deepEqual(cascaded[0], ["drm", "", "f", "s"]);

assert.deepEqual(
  expandGridSlotsForTriplets([["drm", "f", "s"]], [4], triplets)[0],
  ["drm", "", "f", "s"],
);

console.log("triplets.test.ts: ok");
