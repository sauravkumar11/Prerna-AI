import { useEffect, useRef, useState } from "react";

// How long to wait after you stop talking before treating the command as
// finished. Chrome's own no-speech cutoff is aggressive (often ~2-3s), which
// was ending recognition mid-sentence on any brief pause. continuous mode +
// this manual timer gives real breathing room.
const SILENCE_TIMEOUT_MS = 2000;

// If nothing is heard at all (recognition started but you never said
// anything), give up after this long instead of waiting forever.
const NO_SPEECH_TIMEOUT_MS = 8000;

export default function useVoice() {
  const recognitionRef = useRef(null);
  const silenceTimerRef = useRef(null);
  const noSpeechTimerRef = useRef(null);
  const finalTranscriptRef = useRef("");

  const [transcript, setTranscript] =
    useState("");

  const [listening, setListening] =
    useState(false);

  const [volume, setVolume] =
    useState(0);

  const clearTimers = () => {
    clearTimeout(silenceTimerRef.current);
    clearTimeout(noSpeechTimerRef.current);
  };

  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition ||
      window.webkitSpeechRecognition;

    if (!SpeechRecognition) return;

    const recognition =
      new SpeechRecognition();

    // continuous + interim results: keeps the session open through short
    // pauses instead of ending after the first breath. We decide when a
    // command is "done" ourselves via the silence timer below, instead of
    // leaving that entirely up to the browser's own (short) cutoff.
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.lang = "en-IN";

    recognition.onstart = () => {
      console.log("Recognition started");
      finalTranscriptRef.current = "";
      setListening(true);

      // Tell useWakeWord to stay off — we have the mic now
      window.dispatchEvent(new Event("stopWake"));

      clearTimers();
      noSpeechTimerRef.current = setTimeout(() => {
        console.log("No speech within timeout, stopping.");
        try { recognition.stop(); } catch { }
      }, NO_SPEECH_TIMEOUT_MS);
    };

    recognition.onresult = (
      event
    ) => {
      let interim = "";
      let final = finalTranscriptRef.current;

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const chunk = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += (final ? " " : "") + chunk.trim();
        } else {
          interim += chunk;
        }
      }

      finalTranscriptRef.current = final;

      const combined = (final + " " + interim).trim();

      console.log(
        "Command:",
        combined
      );

      setTranscript(combined);

      // Heard something - we're no longer waiting for speech to start,
      // we're waiting for it to stop. Reset the silence timer every time
      // new speech comes in.
      clearTimers();
      silenceTimerRef.current = setTimeout(() => {
        console.log("Silence detected, stopping.");
        try {
          recognition.stop();
        } catch { }
      }, SILENCE_TIMEOUT_MS);
    };

    recognition.onend = () => {
      console.log(
        "Recognition ended"
      );

      clearTimers();
      setListening(false);
      setVolume(0);

      window.dispatchEvent(
        new Event("resumeWake")
      );
    };

    recognition.onerror = (
      event
    ) => {
      console.log(
        "Recognition error:",
        event.error
      );

      if (
        event.error === "aborted" ||
        event.error === "no-speech"
      ) {
        return;
      }

      clearTimers();
      setListening(false);

      window.dispatchEvent(
        new Event("resumeWake")
      );
    };

    recognitionRef.current =
      recognition;

    return () => {
      clearTimers();
      try {
        recognition.stop();
      } catch { }
    };
  }, []);

  const startListening = () => {
    if (
      !recognitionRef.current ||
      listening
    )
      return;

    setTranscript("");
    finalTranscriptRef.current = "";

    try {
      recognitionRef.current.start();
    } catch { }
  };

  const stopListening = () => {
    clearTimers();

    try {
      recognitionRef.current?.stop();
    } catch { }

    setListening(false);
  };

  return {
    transcript,
    listening,
    volume,
    startListening,
    stopListening,
    resetTranscript: () =>
      setTranscript(""),
  };
}
