// Run with vitest once installed: npm i -D vitest && npx vitest run
// (not yet installed in this project — no network access was available
// to add it here, so this hasn't actually been executed. The cases below
// mirror exactly what was manually verified with a standalone Node
// script during development, including the real transcript line "Yes."
// that exposed the original confirmation-loop bug.)

import { describe, it, expect } from "vitest";
import { isAffirmative } from "./affirmative";

describe("isAffirmative", () => {
  it("recognizes a plain 'Yes.' reply (the real transcript that exposed the bug)", () => {
    expect(isAffirmative("Yes.")).toBe(true);
  });

  it("recognizes common Hindi/Hinglish confirmations", () => {
    expect(isAffirmative("haan kar do")).toBe(true);
    expect(isAffirmative("Delete kar do")).toBe(true);
    expect(isAffirmative("theek hai")).toBe(true);
  });

  it("recognizes plain English confirmations", () => {
    expect(isAffirmative("ok")).toBe(true);
    expect(isAffirmative("sure")).toBe(true);
    expect(isAffirmative("go ahead")).toBe(true);
  });

  it("does NOT treat an unrelated new command as a confirmation", () => {
    // Critical: a pending confirmation must be cancellable by simply
    // saying something else, not accidentally swallowed as a "yes".
    expect(isAffirmative("Now play a game")).toBe(false);
    expect(isAffirmative("Open YouTube and play Dilbar")).toBe(false);
  });

  it("does not false-positive on a word that merely contains an affirmative substring", () => {
    expect(isAffirmative("Delete karna hai")).toBe(false);
  });

  it("is case-insensitive and tolerates trailing punctuation", () => {
    expect(isAffirmative("YES!")).toBe(true);
    expect(isAffirmative("Haan?")).toBe(true);
  });
});
