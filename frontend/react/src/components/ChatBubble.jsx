function ChatBubble({ role, message }) {
  return (
    <div className={`chat-row ${role === "user" ? "user-row" : ""}`}>
      {role === "assistant" && (
        <div className="assistant-dot"></div>
      )}

      <div className={`message ${role}`}>
        {message}
      </div>
    </div>
  );
}

export default ChatBubble;