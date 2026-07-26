// Recognizes a "yes, go ahead" reply to a pending confirmation prompt
// (English + common Hindi/Hinglish forms), so a dangerous action isn't
// lost/re-planned from scratch when the user just says "yes".
//
// Extracted into its own module (rather than living inline in App.jsx) so
// it's actually unit-testable — see src/utils/affirmative.test.js.
// NOTE: that test file needs a runner to execute (npm i -D vitest; no
// test runner exists in this project yet, and no network access was
// available here to add one) — the test file is written and ready to run
// once vitest (or jest) is installed, but hasn't been executed by me.

export const AFFIRMATIVE_PHRASES = [
  "yes", "yeah", "yep", "yup", "confirm", "confirmed", "correct", "sure",
  "ok", "okay", "go ahead", "do it",
  "haan", "ha", "haa", "bilkul", "theek hai", "thik hai", "kar do", "karo",
  "kardo", "kar dijiye", "kr do",
];

export function isAffirmative(text) {
  const t = text.trim().toLowerCase().replace(/[.!?]+$/, "");
  return AFFIRMATIVE_PHRASES.some(
    (p) => t === p || t.startsWith(p + " ") || t.endsWith(" " + p)
  );
}
