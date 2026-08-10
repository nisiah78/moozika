/**
 * Checks purs sur le scheduler (pas de Tone.js) — exécuter :
 *   node --experimental-strip-types src/lib/playback.test.ts
 * (Node ≥22) ou via un runner TS.
 */
import assert from "node:assert/strict";
import {
  pitchToNoteName,
  voiceToEvents,
  scoreToEvents,
  soundingNoteName,
  effectiveTonicAt,
} from "./playback";
import type { ScoreResult, VoiceModel } from "./types";

assert.equal(pitchToNoteName({ step: "F", alter: 1, octave: 4, syllable: "m" }), "F#4");
assert.equal(pitchToNoteName({ step: "B", alter: -1, octave: 3, syllable: "t" }), "Bb3");
assert.equal(pitchToNoteName({ step: "C", alter: 0, octave: 5, syllable: "d" }), "C5");

// La hauteur ENTENDUE = pitch absolu stocké (déjà résolu par le parseur avec
// la tonique effective ET les marques d'octave). `d,` sous Doh=C = C3, pas C4.
assert.equal(
  soundingNoteName({
    isRest: false,
    duration: 4,
    type: "quarter",
    dots: 0,
    pitch: { step: "C", alter: 0, octave: 3, syllable: "d" },
    tieStart: false,
    tieStop: false,
  }),
  "C3",
);
// `d` sous Doh=G : le parseur a baké G4 dans le pitch → on entend G4.
assert.equal(
  soundingNoteName({
    isRest: false,
    duration: 4,
    type: "quarter",
    dots: 0,
    pitch: { step: "G", alter: 0, octave: 4, syllable: "d" },
    tieStart: false,
    tieStop: false,
  }),
  "G4",
);

const model: VoiceModel = {
  tonic: "C",
  fifths: 0,
  timeSignature: { beats: 4, beatType: 4 },
  divisions: 4,
  clef: "G",
  tempo: 120,
  partName: "Test",
  measures: [
    {
      number: 1,
      notes: [
        { isRest: true, duration: 2, type: "eighth", dots: 0, pitch: null, tieStart: false, tieStop: false },
        {
          isRest: false,
          duration: 2,
          type: "eighth",
          dots: 0,
          pitch: { step: "C", alter: 0, octave: 4, syllable: "d" },
          tieStart: false,
          tieStop: false,
        },
        {
          isRest: false,
          duration: 4,
          type: "quarter",
          dots: 0,
          pitch: { step: "E", alter: 0, octave: 4, syllable: "m" },
          tieStart: true,
          tieStop: false,
        },
        {
          isRest: false,
          duration: 4,
          type: "quarter",
          dots: 0,
          pitch: { step: "E", alter: 0, octave: 4, syllable: "m" },
          tieStart: false,
          tieStop: true,
        },
      ],
    },
  ],
};

// tempo 120 → noire = 0.5 s ; divisions=4 → 1 division = 0.125 s
const events = voiceToEvents(model, 120);
assert.equal(events.length, 2);
assert.deepEqual(events[0], { time: 0.25, duration: 0.25, note: "C4" });
// liaison : 4+4 divisions = 1.0 s à t=0.5
assert.deepEqual(events[1], { time: 0.5, duration: 1.0, note: "E4" });

// Changement de tonalité mid-partition : même syllabe `d`, hauteur entendue change
const modulated: VoiceModel = {
  ...model,
  measures: [
    {
      number: 1,
      notes: [
        {
          isRest: false,
          duration: 4,
          type: "quarter",
          dots: 0,
          pitch: { step: "C", alter: 0, octave: 4, syllable: "d" },
          tieStart: false,
          tieStop: false,
        },
      ],
    },
    {
      number: 2,
      keyTonic: "G",
      keyFifths: 1,
      notes: [
        {
          isRest: false,
          duration: 4,
          type: "quarter",
          dots: 0,
          // Doh=G : le parseur a résolu `d` en G4 dans le pitch absolu.
          pitch: { step: "G", alter: 0, octave: 4, syllable: "d" },
          tieStart: false,
          tieStop: false,
        },
      ],
    },
  ],
};
assert.equal(effectiveTonicAt(modulated, 0), "C");
assert.equal(effectiveTonicAt(modulated, 1), "G");
const modEvents = voiceToEvents(modulated, 120);
assert.equal(modEvents.length, 2);
assert.equal(modEvents[0].note, "C4");
assert.equal(modEvents[1].note, "G4");

const score: ScoreResult = {
  header: { title: "t", tonic: "C", timeSignature: { beats: 4, beatType: 4 }, tempo: 120 },
  voices: [
    { name: "S", notation: "", model },
    {
      name: "A",
      notation: "",
      model: {
        ...model,
        partName: "A",
        measures: [
          {
            number: 1,
            notes: [
              {
                isRest: false,
                duration: 4,
                type: "quarter",
                dots: 0,
                pitch: { step: "G", alter: 0, octave: 3, syllable: "s" },
                tieStart: false,
                tieStop: false,
              },
            ],
          },
        ],
      },
    },
  ],
  musicxml: "",
};
assert.equal(scoreToEvents(score).length, 3);

console.log("playback.test.ts: ok");
