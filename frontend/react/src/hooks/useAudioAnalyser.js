import { useCallback, useEffect, useRef, useState } from "react";

const FFT_SIZE = 256;
const SMOOTHING = 0.8;

/**
 * useAudioAnalyser
 *
 * Provides real-time audio amplitude (0–1) from either:
 *   - The microphone (during listening)
 *   - An <Audio> element's output (during TTS playback)
 *
 * Usage:
 *   const { amplitude, startMicAnalysis, stopMicAnalysis,
 *           connectAudioElement, disconnectAudio } = useAudioAnalyser();
 *
 * Feed `amplitude` directly into the orb as the `volume` prop.
 */
export default function useAudioAnalyser() {
  const [amplitude, setAmplitude] = useState(0);

  const contextRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);

  const _getContext = () => {
    if (!contextRef.current || contextRef.current.state === "closed") {
      contextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    return contextRef.current;
  };

  const _startLoop = () => {
    const analyser = analyserRef.current;
    if (!analyser) return;

    const data = new Uint8Array(analyser.frequencyBinCount);

    const tick = () => {
      analyser.getByteFrequencyData(data);
      // Average the lower half of bins (where voice lives)
      const sum = data.slice(0, data.length / 2).reduce((a, b) => a + b, 0);
      const avg = sum / (data.length / 2);
      setAmplitude(avg / 255);
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
  };

  const _stopLoop = () => {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    setAmplitude(0);
  };

  const _disconnect = () => {
    try { sourceRef.current?.disconnect(); } catch { /* ignore */ }
    sourceRef.current = null;
    // Stop mic stream tracks if any
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  const startMicAnalysis = useCallback(async () => {
    try {
      _stopLoop();
      _disconnect();

      const ctx = _getContext();
      if (ctx.state === "suspended") await ctx.resume();

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      streamRef.current = stream;

      const analyser = ctx.createAnalyser();
      analyser.fftSize = FFT_SIZE;
      analyser.smoothingTimeConstant = SMOOTHING;
      analyserRef.current = analyser;

      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);
      sourceRef.current = source;

      _startLoop();
    } catch (err) {
      console.warn("Mic analysis failed:", err);
    }
  }, []);

  const stopMicAnalysis = useCallback(() => {
    _stopLoop();
    _disconnect();
  }, []);

  /**
   * Connect a playing <Audio> element so its output drives the analyser.
   * Call this right after audio.play() starts.
   */
  const connectAudioElement = useCallback((audioEl) => {
    if (!audioEl) return;
    try {
      _stopLoop();
      _disconnect();

      const ctx = _getContext();
      if (ctx.state === "suspended") ctx.resume();

      const analyser = ctx.createAnalyser();
      analyser.fftSize = FFT_SIZE;
      analyser.smoothingTimeConstant = SMOOTHING;
      analyserRef.current = analyser;

      const source = ctx.createMediaElementSource(audioEl);
      source.connect(analyser);
      analyser.connect(ctx.destination); // still play audio through speakers
      sourceRef.current = source;

      _startLoop();
    } catch (err) {
      console.warn("Audio element analysis failed:", err);
    }
  }, []);

  const disconnectAudio = useCallback(() => {
    _stopLoop();
    _disconnect();
  }, []);

  useEffect(() => {
    return () => {
      _stopLoop();
      _disconnect();
      contextRef.current?.close().catch(() => {});
    };
  }, []);

  return {
    amplitude,
    startMicAnalysis,
    stopMicAnalysis,
    connectAudioElement,
    disconnectAudio,
  };
}
