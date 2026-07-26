import { useRef, useState } from "react";

const MAX_HISTORY = 20;

/**
 * useConversation
 *
 * Owns the messages array shown in the chat UI, and the rolling history
 * array sent to the backend with each request.
 *
 * Returns { messages, addUserMessage, addAssistantMessage, addErrorMessage, conversationHistory }
 */
export default function useConversation() {
  const [messages, setMessages] = useState([]);
  const conversationHistory = useRef([]);

  const _push = (msg) => {
    conversationHistory.current.push(msg);
    // Cap both display list and API payload — prevents unbounded growth in long sessions
    if (conversationHistory.current.length > MAX_HISTORY) {
      conversationHistory.current = conversationHistory.current.slice(-MAX_HISTORY);
    }
  };

  const addUserMessage = (content) => {
    const msg = { role: "user", content };
    setMessages((prev) => [...prev, msg]);
    _push(msg);
    return msg;
  };

  const addAssistantMessage = (content) => {
    const msg = { role: "assistant", content };
    setMessages((prev) => [...prev, msg]);
    _push(msg);
    return msg;
  };

  const addErrorMessage = (content = "Sorry Saurav, something went wrong.") => {
    const msg = { role: "assistant", content };
    setMessages((prev) => [...prev, msg]);
    return msg;
  };

  return {
    messages,
    conversationHistory,
    addUserMessage,
    addAssistantMessage,
    addErrorMessage,
  };
}
