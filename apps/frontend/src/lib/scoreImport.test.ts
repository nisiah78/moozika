/**
 * Checks purs — exécuter :
 *   node --experimental-strip-types src/lib/scoreImport.test.ts
 */
import assert from "node:assert/strict";
import {
  isMusicXmlFile,
  isPdfFile,
  musicXmlResponseToScoreResult,
} from "./scoreImport";
import type { MusicXmlParseResponse } from "./types";

assert.equal(isMusicXmlFile(new File([], "part.musicxml")), true);
assert.equal(isMusicXmlFile(new File([], "score.mxl")), true);
assert.equal(isMusicXmlFile(new File([], "sheet.pdf")), false);

assert.equal(isPdfFile(new File([], "cantique.pdf", { type: "application/pdf" })), true);
assert.equal(isPdfFile(new File([], "part.xml")), false);

const api: MusicXmlParseResponse = {
  header: { tonic: "D", beats: 4, beatType: 4, tempo: 75 },
  voices: [
    {
      name: "Soprano",
      notation: "d : r",
      model: {
        tonic: "D",
        fifths: 2,
        timeSignature: { beats: 4, beatType: 4 },
        divisions: 4,
        clef: "treble",
        tempo: 75,
        partName: "Soprano",
        measures: [],
      },
    },
  ],
  warnings: ["[chord] accord réduit"],
};
const xmlFile = new File(["<score-partwise/>"], "jesoa.musicxml");
const mapped = musicXmlResponseToScoreResult(api, xmlFile, "<score-partwise/>");
assert.equal(mapped.header.title, "jesoa");
assert.equal(mapped.header.tonic, "D");
assert.equal(mapped.voices[0].notation, "d : r");
assert.equal(mapped.musicxml, "<score-partwise/>");
assert.equal(mapped.uploadedFile, undefined);
assert.deepEqual(mapped.warnings, ["[chord] accord réduit"]);

const mxlFile = new File([], "score.mxl");
const mxlMapped = musicXmlResponseToScoreResult(
  { header: { tonic: "C", beats: 4, beatType: 4, tempo: null }, voices: [] },
  mxlFile,
  "",
);
assert.equal(mxlMapped.uploadedFile, mxlFile);
assert.equal(mxlMapped.musicxml, "");

console.log("scoreImport.test.ts OK");
