import { useEffect, useRef, useState } from "react";
import "./App.css";

import SiriOrb from "./components/SiriOrb";
import ChatBubble from "./components/ChatBubble";

import useVoice from "./hooks/useVoice";
import useWakeWord from "./hooks/useWakeWord";
import useAudioPlayer from "./hooks/useAudioPlayer";
import useAudioAnalyser from "./hooks/useAudioAnalyser";
import useConversation from "./hooks/useConversation";
import useConversationMode from "./hooks/useConversationMode";
import { sendCommand } from "./services/api";
import { isAffirmative } from "./utils/affirmative";

// ── Constants ─────────────────────────────────────────────────────────────────
const EMOTION_REGEX = /^\[(EXCITED|PLAYFUL|CARING|SAD|ANGRY|SHY|SURPRISED|CALM)\]/i;

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning, Saurav. I'm ready whenever you are.";
  if (h < 18) return "Good afternoon, Saurav. What can I do for you?";
  return "Good evening, Saurav. I'm here whenever you need me.";
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  // ── Orb display state ─────────────────────────────────────────────────────
  const [orbState, setOrbState] = useState("idle"); // idle | wake | listening | thinking | speaking
  const [orbEmotion, setOrbEmotion] = useState("CALM");
  const [loading, setLoading] = useState(false);

  // ── Refs ──────────────────────────────────────────────────────────────────
  const loadingRef = useRef(false);
  const requestIdRef = useRef(0);
  const thinkingTimerRef = useRef(null);
  const cancelledRef = useRef(false);
  const respondedRef = useRef(false);
  const lastProcessedRef = useRef("");
  const greetedRef = useRef(false);
  const chatRef = useRef(null);
  // Holds the ORIGINAL command text (e.g. "Delete kar do") while a
  // dangerous action is awaiting "yes"/"haan" confirmation, so the next
  // reply can resend that same command with confirmed=true instead of
  // re-planning whatever the user says next (which is what caused the
  // infinite "are you sure?" loop — "yes" was being planned as a brand
  // new, unrelated message every time).
  const pendingConfirmationRef = useRef(null);

  useEffect(() => { loadingRef.current = loading; }, [loading]);

  // ── Hooks ─────────────────────────────────────────────────────────────────
  const { messages, conversationHistory, addUserMessage, addAssistantMessage, addErrorMessage } = useConversation();

  const { amplitude, startMicAnalysis, stopMicAnalysis, connectAudioElement, disconnectAudio } = useAudioAnalyser();

  const { isSpeaking, play: playAudio, stop: stopAudio } = useAudioPlayer({
    onSpeakingChange: (speaking) => {
      setOrbState(speaking ? "speaking" : (loadingRef.current ? "thinking" : "idle"));
      if (!speaking) disconnectAudio();
    },
    onAudioElement: (audioEl) => connectAudioElement(audioEl),
  });

  const { transcript, listening, startListening, stopListening, resetTranscript } = useVoice();

  const { active: sessionActive, startSession, endSession, resetIdleTimer, isExitPhrase } = useConversationMode({
    onSessionEnd: () => {
      // Session ended (timeout or exit phrase) — reset everything cleanly
      // and restart the wake word listener so "Hey Prerna" works again
      setOrbState("idle");
      setOrbEmotion("CALM");
      loadingRef.current = false;
      setLoading(false);
      cancelledRef.current = false;
      window.commandActive = false;
      stopListening();
      // Small delay so in-flight mic releases before wake restarts
      setTimeout(() => {
        window.dispatchEvent(new Event("resumeWake"));
      }, 800);
    },
  });

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // ── Greeting ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (greetedRef.current) return;
    greetedRef.current = true;
    const text = getGreeting();
    addAssistantMessage(text);
    playAudio(text, "PLAYFUL");
  }, []); // eslint-disable-line

  // ── Sync orb with mic analysis ────────────────────────────────────────────
  useEffect(() => {
    if (listening) {
      startMicAnalysis();
      setOrbState("listening");
    } else {
      stopMicAnalysis();
    }
  }, [listening]); // eslint-disable-line

  // ── Core: play voice ───────────────────────────────────────────────────────
  const playPrernaVoice = async (text, emotion = "CALM") => {
    if (cancelledRef.current) return;
    setOrbState("speaking");
    setOrbEmotion(emotion);
    await playAudio(text, emotion);
    if (!loadingRef.current && !sessionActive) setOrbState("idle");
  };

  // ── Core: process a command ───────────────────────────────────────────────
  const processCommand = async (text) => {
    if (!text?.trim()) return;
    resetIdleTimer();

    if (isExitPhrase(text)) {
      endSession();
      await playPrernaVoice("Okay Saurav, talk to me when you need me.", "CARING");
      return;
    }

    addUserMessage(text);
    cancelledRef.current = false;
    respondedRef.current = false;
    const requestId = ++requestIdRef.current;

    // ── Resolve any pending "are you sure?" confirmation ──────────────────
    // If a dangerous action is awaiting confirmation, an affirmative reply
    // ("yes", "haan", "kar do", ...) resends the EXACT step that triggered
    // it (deterministic — see backend confirmed_step), falling back to the
    // original text only if the backend didn't supply a step for some
    // reason. Anything else cancels the pending action instead of silently
    // merging into it.
    let sendText = text;
    let confirmed = false;
    let confirmedStep = null;
    if (pendingConfirmationRef.current) {
      if (isAffirmative(text)) {
        sendText = pendingConfirmationRef.current.originalText;
        confirmed = true;
        confirmedStep = pendingConfirmationRef.current.step || null;
      }
      pendingConfirmationRef.current = null;
    }

    setLoading(true);
    loadingRef.current = true;
    setOrbState("thinking");

    const _afterResponse = async () => {
      // Called after every response (success or handled error) to resume
      // continuous listening or return to idle cleanly
      if (sessionActive && !cancelledRef.current) {
        setOrbState("listening");
        resetIdleTimer();
        window.commandActive = true;
        window.dispatchEvent(new Event("stopWake"));
        startListening();
      } else {
        setOrbState("idle");
        window.dispatchEvent(new Event("resumeWake"));
      }
    };

    try {
      const response = await sendCommand(sendText, conversationHistory.current, confirmed, confirmedStep);

      if (cancelledRef.current || requestId !== requestIdRef.current) return;

      respondedRef.current = true;
      clearTimeout(thinkingTimerRef.current);

      // Backend is asking to confirm a dangerous action — remember both the
      // original text (fallback) and the exact pending step (preferred —
      // see the resolution block above) so the next "yes" is deterministic.
      if (response.requires_confirmation) {
        pendingConfirmationRef.current = {
          originalText: sendText,
          step: response.pending_step || null,
        };
      }

      let content = response.response || response.reply || response.message || "Done.";
      let speechContent = response.speech || content;
      let emotion = "CALM";
      const match = content.match(EMOTION_REGEX);
      if (match) {
        emotion = match[1];
        content = content.replace(match[0], "").trim();
      }
      // Strip the same emotion tag from the speech text if it's there too
      // (tool replies share the same "[CALM] ..." prefix as the display text).
      const speechMatch = speechContent.match(EMOTION_REGEX);
      if (speechMatch) {
        speechContent = speechContent.replace(speechMatch[0], "").trim();
      }

      addAssistantMessage(content);
      setOrbEmotion(emotion);
      setLoading(false);
      loadingRef.current = false;

      // Always speak the response (even quota messages) before resuming
      await playPrernaVoice(speechContent, emotion);
      await _afterResponse();

    } catch (err) {
      // Only real network errors reach here now (backend returns friendly
      // messages for quota errors instead of throwing 500)
      console.error("Command error:", err);
      if (cancelledRef.current) return;

      clearTimeout(thinkingTimerRef.current);
      respondedRef.current = true;
      setLoading(false);
      loadingRef.current = false;

      const errMsg = "Sorry Saurav, I couldn't connect to the backend. Is it running?";
      addErrorMessage(errMsg);
      await playPrernaVoice(errMsg, "CARING");
      await _afterResponse();
    }
  };

  // ── Wake word callback ────────────────────────────────────────────────────
  useWakeWord(() => {
    if (listening || isSpeaking) return;
    console.log("WAKE CALLBACK");

    startSession();
    setOrbState("wake");
    setOrbEmotion("PLAYFUL");

    (async () => {
      await playPrernaVoice("Haan Saurav?", "PLAYFUL");
      if (!cancelledRef.current) {
        setOrbState("listening");
        startListening();
      }
    })();
  });

  // ── Transcript processing ─────────────────────────────────────────────────
  useEffect(() => {
    const text = transcript.trim();
    if (cancelledRef.current) return;

    if (!listening && text && text !== lastProcessedRef.current) {
      lastProcessedRef.current = text;
      processCommand(text);
      resetTranscript();
      return;
    }

    if (!listening && !text && !loadingRef.current && !isSpeaking) {
      if (sessionActive) {
        resetIdleTimer();
        window.commandActive = true;
        window.dispatchEvent(new Event("stopWake"));
        startListening();
      } else {
        // No speech heard outside a session — just silently go back to idle.
        // Don't say "Sorry I didn't catch that" on startup or idle misses.
        setOrbState("idle");
      }
    }
  }, [listening, transcript]); // eslint-disable-line

  // ── Cleanup on unmount ────────────────────────────────────────────────────
  useEffect(() => () => {
    clearTimeout(thinkingTimerRef.current);
    stopAudio();
    stopMicAnalysis();
  }, []); // eslint-disable-line

  // ── Manual speak/stop button ──────────────────────────────────────────────
  const toggleVoice = () => {
    if (listening || isSpeaking || loading) {
      cancelledRef.current = true;
      requestIdRef.current++;
      clearTimeout(thinkingTimerRef.current);
      endSession();
      stopListening();
      resetTranscript();
      lastProcessedRef.current = "";
      stopAudio();
      stopMicAnalysis();
      disconnectAudio();
      setLoading(false);
      loadingRef.current = false;
      setOrbState("idle");
      window.dispatchEvent(new Event("resumeWake"));
      return;
    }

    // Manual speak — start a session
    cancelledRef.current = false;
    startSession();
    setOrbState("listening");
    startListening();
  };

  const showOrb = true; // always visible — idle state shows subtle breathing

  // ── Render (layout unchanged) ─────────────────────────────────────────────
  return (
    <div className="app">
      <div className="chat-area" ref={chatRef}>
        {messages.map((msg, i) => (
          <ChatBubble key={i} role={msg.role} message={msg.content} />
        ))}
      </div>

      <div className="floating-controls">
        <div className="floating-orb-container">
          <SiriOrb
            state={orbState}
            emotion={orbEmotion}
            amplitude={amplitude}
          />
          <p className="status-text">
            {orbState === "wake"       ? "Prerna is awake..."
             : orbState === "listening"  ? (transcript || "Listening...")
             : orbState === "thinking"   ? "Thinking..."
             : orbState === "speaking"   ? "Speaking..."
             : ""}
          </p>
        </div>

        <button className="mic-button" onClick={toggleVoice}>
          {listening || isSpeaking || loading ? "Stop" : "Speak"}
        </button>
      </div>
    </div>
  );
}