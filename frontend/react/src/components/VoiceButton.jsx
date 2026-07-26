import "./VoiceButton.css";

export default function VoiceButton({
  isListening,
  startListening,
}) {
  return (
    <button
      className={`voice-btn ${isListening ? "listening" : ""}`}
      onClick={startListening}
    >
      🎤
    </button>
  );
}