const API_BASE =
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000";

export async function sendCommand(message, history = [], confirmed = false, confirmedStep = null) {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, confirmed, confirmed_step: confirmedStep }),
  });

  const data = await response.json();

  console.log("Backend status:", response.status);
  console.log("Backend response:", data);

  // Even if backend returns 500, try to surface the message gracefully
  // instead of throwing and breaking the conversation session
  if (!response.ok) {
    // If backend returned a detail string, use it as the response
    const detail = data?.detail || data?.message || null;
    if (detail) {
      return { response: `[CALM] ${detail}` };
    }
    throw new Error(JSON.stringify(data));
  }

  return data;
}

export async function fetchTTS(message, emotion = "CALM") {
  const response = await fetch(`${API_BASE}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, emotion }),
  });

  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = body?.detail || "";
    } catch { /* not JSON */ }
    throw new Error(`TTS failed: ${response.status}${detail ? ` - ${detail}` : ""}`);
  }

  return response.blob();
}
