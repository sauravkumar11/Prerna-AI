import { useCallback, useEffect, useRef, useState } from "react";

// Phrases that end the continuous session
const EXIT_PHRASES = [
  "goodbye", "good bye", "bye", "bye bye",
  "stop listening", "go to sleep", "sleep",
  "that's all", "thats all", "done", "thank you prerna",
  "shukriya", "alvida", "bas karo", "band karo",
];

// How long to wait with no activity before auto-sleeping (ms)
const IDLE_TIMEOUT_MS = 45_000;

/**
 * useConversationMode
 *
 * Manages the continuous conversation session. Once started:
 *  - `active` stays true until an exit phrase or idle timeout
 *  - `startSession()` begins a new session
 *  - `endSession()` stops listening and resets
 *  - `isExitPhrase(text)` lets callers check if the user wants to quit
 *  - `resetIdleTimer()` should be called after every interaction to push
 *    the idle timeout back
 *
 * The actual mic start/stop is NOT done here — this hook only manages
 * session state. App.jsx decides when to call startListening() based on
 * `active`.
 */
export default function useConversationMode({ onSessionEnd } = {}) {
  const [active, setActive] = useState(false);
  const idleTimerRef = useRef(null);

  const clearIdle = () => clearTimeout(idleTimerRef.current);

  const endSession = useCallback(() => {
    clearIdle();
    setActive(false);
    window.commandActive = false;
    onSessionEnd?.();
  }, [onSessionEnd]);

  const resetIdleTimer = useCallback(() => {
    clearIdle();
    idleTimerRef.current = setTimeout(() => {
      console.log("Conversation idle timeout — going to sleep.");
      endSession();
    }, IDLE_TIMEOUT_MS);
  }, [endSession]);

  const startSession = useCallback(() => {
    setActive(true);
    window.commandActive = true;
    resetIdleTimer();
  }, [resetIdleTimer]);

  const isExitPhrase = useCallback((text) => {
    const lower = (text || "").toLowerCase().trim();
    return EXIT_PHRASES.some((phrase) => lower.includes(phrase));
  }, []);

  // Clean up on unmount
  useEffect(() => () => clearIdle(), []);

  return {
    active,
    startSession,
    endSession,
    resetIdleTimer,
    isExitPhrase,
  };
}
