import { useEffect, useRef } from "react";

/**
 * useWakeWord
 * ===========
 * Listens continuously (when idle) for a wake phrase and fires `onWake`.
 *
 * Design goals (fixes the "sometimes she listens, sometimes doesn't" bug):
 *
 * 1. DATA-DRIVEN WAKE WORDS — the phrases that trigger a wake are not
 *    scattered `text.includes(...)` checks. They live in one config list
 *    (`resolveWakeWords()`), which can be overridden at runtime via
 *    `window.PRERNA_WAKE_WORDS = ["hey buddy", ...]` or by passing a
 *    `wakeWords` array as the 2nd argument to this hook. Nothing about the
 *    assistant's name is baked into the matching logic itself.
 *
 * 2. WORD-BOUNDARY MATCHING — phrases are matched on word boundaries
 *    instead of raw substring `includes()`, so a short phrase can't
 *    false-trigger by appearing inside an unrelated word.
 *
 * 3. SELF-HEALING WATCHDOG — Web Speech's `SpeechRecognition` can die
 *    silently (a stray exception on `.start()`, the tab losing focus, the
 *    browser just... stopping) without ever firing `onend`. Previously
 *    there was nothing to notice this, so the mic could simply stay off
 *    until the page was reloaded. A lightweight interval now checks
 *    "should I be listening right now?" against "am I actually listening?"
 *    and restarts recognition if those two disagree.
 *
 * 4. BACKOFF ON REAL ERRORS — permission/hardware errors (`not-allowed`,
 *    `audio-capture`, `service-not-allowed`) stop the retry loop instead of
 *    spinning forever; transient errors (`network`, `aborted`, `no-speech`)
 *    retry with a short backoff instead of going silent.
 *
 * The wake listener only runs when:
 *   - window.commandActive is false (no active session)
 *   - pausedRef is false (not mid-command)
 *   - Prerna isn't currently speaking (speakingStart/End events)
 */

const DEFAULT_WAKE_WORDS = [
  "prerna",
  "hey prerna",
  "hello prerna",
  "haji",
  "kaisi ho",
  "naincy suno",
  "prerna suno",
];

/** Build the active wake-word list from (in priority order): an explicit
 *  argument, a runtime window override, then the built-in default. Keeping
 *  this as one small function means the assistant's name/phrases can be
 *  changed in exactly one place (or from outside the bundle entirely). */
function resolveWakeWords(explicit) {
  if (Array.isArray(explicit) && explicit.length) return explicit;
  if (Array.isArray(window.PRERNA_WAKE_WORDS) && window.PRERNA_WAKE_WORDS.length) {
    return window.PRERNA_WAKE_WORDS;
  }
  return DEFAULT_WAKE_WORDS;
}

function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Compile wake words into word-boundary regexes once, not on every result. */
function compileWakeMatchers(words) {
  return words.map((phrase) => ({
    phrase,
    regex: new RegExp(`\\b${escapeRegExp(phrase.toLowerCase().trim())}\\b`, "i"),
  }));
}

function matchWakeWord(text, matchers) {
  for (const { phrase, regex } of matchers) {
    if (regex.test(text)) return phrase;
  }
  return null;
}

// Errors that mean "don't bother retrying" (permission/hardware, not transient).
const FATAL_ERRORS = new Set(["not-allowed", "service-not-allowed", "audio-capture"]);

export default function useWakeWord(onWake, wakeWords) {
  const recognitionRef     = useRef(null);
  const wakeCallbackRef    = useRef(onWake);
  const pausedRef          = useRef(false);
  const stoppedRef         = useRef(false);  // true = we deliberately stopped it
  const runningRef         = useRef(false);  // true = recognition.start() succeeded and hasn't ended yet
  const fatalRef           = useRef(false);  // true = permission/hardware error, stop trying
  const restartTimeoutRef  = useRef(null);

  useEffect(() => { wakeCallbackRef.current = onWake; }, [onWake]);

  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const matchers = compileWakeMatchers(resolveWakeWords(wakeWords));

    const recognition = new SpeechRecognition();
    recognition.continuous     = true;
    recognition.interimResults = false;
    recognition.lang           = "en-IN";
    recognitionRef.current     = recognition;

    const isSpeakingRef = { current: false };
    const onSpeakingStart = () => { isSpeakingRef.current = true; };
    const onSpeakingEnd   = () => { isSpeakingRef.current = false; };
    window.addEventListener("speakingStart", onSpeakingStart);
    window.addEventListener("speakingEnd", onSpeakingEnd);

    /** Should the wake listener be active right now? Single source of
     *  truth used both by onend's restart decision and by the watchdog. */
    const shouldBeListening = () =>
      !pausedRef.current && !window.commandActive && !fatalRef.current;

    const clearPendingRestart = () => {
      if (restartTimeoutRef.current) {
        clearTimeout(restartTimeoutRef.current);
        restartTimeoutRef.current = null;
      }
    };

    const safeStart = (label, delay = 0) => {
      clearPendingRestart();
      restartTimeoutRef.current = setTimeout(() => {
        restartTimeoutRef.current = null;
        if (!shouldBeListening() || runningRef.current) return;
        try {
          recognition.start();
          console.log(label);
        } catch (err) {
          // "already started" races can happen if onend/onstart overlap —
          // treat as running rather than as a failure.
          if (err && err.name === "InvalidStateError") {
            runningRef.current = true;
          } else {
            console.log("Wake restart failed:", err);
          }
        }
      }, delay);
    };

    recognition.onstart = () => {
      runningRef.current = true;
    };

    recognition.onresult = (event) => {
      const text = event.results[event.results.length - 1][0].transcript
        .toLowerCase()
        .trim();
      console.log("Wake heard:", text);

      if (isSpeakingRef.current) return;

      const matched = matchWakeWord(text, matchers);
      if (matched) {
        console.log("WAKE DETECTED:", matched);
        pausedRef.current    = true;
        stoppedRef.current   = true;
        window.commandActive = true;
        try { recognition.stop(); } catch {}
        wakeCallbackRef.current?.();
      }
    };

    recognition.onerror = (e) => {
      // aborted = we stopped it on purpose, or mic taken by useVoice — fine.
      if (e.error === "aborted" || e.error === "no-speech") return;

      if (FATAL_ERRORS.has(e.error)) {
        fatalRef.current = true;
        console.log("Wake mic unavailable, giving up:", e.error);
        return;
      }
      console.log("Wake Error:", e.error);
      // Transient error (e.g. "network"): onend will still fire and drive
      // the retry, but give it a slightly longer backoff to avoid hammering.
    };

    recognition.onend = () => {
      runningRef.current = false;

      if (pausedRef.current)    { console.log("Wake paused"); return; }
      if (window.commandActive) { console.log("Command active — wake staying off"); return; }
      if (fatalRef.current)     { return; }
      if (stoppedRef.current)   { stoppedRef.current = false; return; }

      safeStart("Wake Restart", 1000);
    };

    try {
      recognition.start();
      console.log("Wake Started");
    } catch {}

    const resumeWake = () => {
      pausedRef.current    = false;
      window.commandActive = false;

      // 1400ms: enough for TTS audio to physically finish playing before
      // the mic restarts — prevents ghost wakes from Prerna's own voice.
      safeStart("Wake Resumed", 1400);
    };

    // stopWake: called by App.jsx when a continuous session starts
    // listening. Keeps the wake listener fully off while useVoice has
    // the mic.
    const stopWake = () => {
      stoppedRef.current = true;
      clearPendingRestart();
      try { recognition.stop(); } catch {}
    };

    window.addEventListener("resumeWake", resumeWake);
    window.addEventListener("stopWake", stopWake);

    // Watchdog: every few seconds, reconcile "should be listening" against
    // "is actually listening". This is what fixes the intermittent
    // "sometimes she just doesn't listen" behaviour — recognition can die
    // without ever firing onend, so nothing else would ever notice.
    const watchdog = setInterval(() => {
      if (!shouldBeListening()) return;
      if (runningRef.current) return;
      if (restartTimeoutRef.current) return; // a restart is already queued
      safeStart("Wake Watchdog Restart");
    }, 4000);

    return () => {
      clearInterval(watchdog);
      clearPendingRestart();
      window.removeEventListener("resumeWake", resumeWake);
      window.removeEventListener("stopWake", stopWake);
      window.removeEventListener("speakingStart", onSpeakingStart);
      window.removeEventListener("speakingEnd", onSpeakingEnd);
      recognition.onstart = null;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      try { recognition.stop(); } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
