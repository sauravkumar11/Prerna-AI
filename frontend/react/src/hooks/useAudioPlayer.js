import { useRef, useState } from "react";
import { fetchTTS } from "../services/api";

/**
 * useAudioPlayer
 *
 * Manages TTS audio playback:
 *  - Fetches audio from /tts
 *  - Plays it and waits for it to finish (resolves when playback ends, not
 *    just when it starts - so callers can reliably sequence mic start after
 *    speech end)
 *  - Handles abort / interruption cleanly
 *  - Exposes isSpeaking state
 *
 * Returns { isSpeaking, play, stop }
 */
export default function useAudioPlayer({ onSpeakingChange, loadingRef, onAudioElement } = {}) {
  const [isSpeaking, setIsSpeaking] = useState(false);

  const currentAudioRef = useRef(null);
  const abortControllerRef = useRef(null);
  const pendingResolveRef = useRef(null);
  const cancelledRef = useRef(false);

  const _setSpeaking = (val) => {
    setIsSpeaking(val);
    onSpeakingChange?.(val);
    // Broadcast to useWakeWord so it doesn't fire on Prerna's own voice
    window.dispatchEvent(new Event(val ? "speakingStart" : "speakingEnd"));
  };

  const _resolveAny = () => {
    if (pendingResolveRef.current) {
      pendingResolveRef.current();
      pendingResolveRef.current = null;
    }
  };

  const stop = () => {
    cancelledRef.current = true;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;

    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.currentTime = 0;
      const src = currentAudioRef.current.src;
      if (src?.startsWith("blob:")) URL.revokeObjectURL(src);
      currentAudioRef.current = null;
    }

    _resolveAny();
    _setSpeaking(false);
  };

  const play = async (text, emotion = "CALM") => {
    if (!text) return;

    cancelledRef.current = false;

    // Abort any in-flight fetch and stop current audio first.
    abortControllerRef.current?.abort();
    _resolveAny();
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.currentTime = 0;
      currentAudioRef.current = null;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    _setSpeaking(true);

    try {
      const blob = await fetchTTS(text, emotion);

      if (controller.signal.aborted || cancelledRef.current) return;

      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      currentAudioRef.current = audio;
      onAudioElement?.(audio);  // let caller connect the FFT analyser

      console.log("Playing:", text);

      await new Promise((resolve) => {
        pendingResolveRef.current = resolve;

        const finish = () => {
          URL.revokeObjectURL(url);
          currentAudioRef.current = null;
          _setSpeaking(false);
          pendingResolveRef.current = null;
          resolve();
        };

        audio.onended = () => { console.log("Finished:", text); finish(); };
        audio.onerror = finish;
        audio.play().catch((err) => {
          console.error("Audio play() failed:", err);
          finish();
        });
      });

    } catch (error) {
      if (error.name !== "AbortError") {
        console.error("Prerna Voice Error:", error);
        window.dispatchEvent(new Event("resumeWake"));
      }
      _setSpeaking(false);
    }
  };

  return { isSpeaking, play, stop };
}
