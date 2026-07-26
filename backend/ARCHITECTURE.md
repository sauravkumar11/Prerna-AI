# Architecture

## Backend

```
backend/
├── main.py                  # App creation, middleware, router mounting ONLY
├── config/
│   └── settings.py          # All env vars, paths, constants — single source of truth
├── app/
│   ├── api/
│   │   ├── chat.py          # POST /chat — planner → executor → Gemini flow
│   │   ├── tts.py           # POST /tts  — edge-tts audio generation
│   │   └── health.py        # GET  /     & GET /api/health
│   ├── dependencies.py      # Gemini model singleton (init once at startup)
│   ├── models.py            # Pydantic request/response models
│   └── persona.py           # System prompt, emotion tags, fixed shortcut responses
├── agent/
│   ├── planner.py           # Gemini → list of {tool, args, reason} steps
│   ├── reasoning.py         # Which tool/action matches a step (no LLM call)
│   ├── validation.py        # Args present? Confirmation needed? (separate from reasoning)
│   ├── executor.py          # Runs list of steps in order; stops on failure/confirmation
│   ├── predictor.py         # Proactive suggestions ("I'm leaving" → suggest Maps)
│   ├── registry.py          # @action decorator, ToolResult, describe_tools()
│   └── context.py           # Assembles memory into what prompts need
├── tools/                   # One file per capability; all self-register via @action
│   ├── browser_tool.py
│   ├── youtube_tool.py
│   ├── instagram_tool.py
│   ├── whatsapp_tool.py
│   ├── system_tool.py       # Lock/shutdown/restart/sleep + app launcher
│   ├── camera_tool.py
│   ├── screenshot_tool.py
│   ├── vscode_tool.py
│   ├── file_tool.py
│   ├── clipboard_tool.py
│   ├── volume_tool.py
│   ├── bluetooth_tool.py
│   ├── wifi_tool.py
│   ├── notepad_tool.py
│   ├── notes_tool.py
│   ├── alarm_tool.py
│   ├── search_tool.py
│   ├── coding_tool.py
│   └── email_tool.py
├── memory/
│   └── memory_manager.py    # All persistence: long-term, short-term, conversation, emotion
├── voice/
│   └── tts.py               # edge-tts audio generation with emotion rate/pitch control
└── utils/
    └── logger.py            # get_logger(__name__) — structured, consistent format

```

## Pipeline

```
User voice
    ↓
Wake word detected (useWakeWord.js)
    ↓
"Haan Saurav?" played (useAudioPlayer.js)
    ↓
Mic opened (useVoice.js — continuous, silence-based cutoff)
    ↓
Command transcribed
    ↓
POST /chat
    ↓
Planner  → list of steps [{tool, args, reason}, ...]
    ↓
Reasoning → which handler?
    ↓
Validation → args complete? safe to run?
    ↓
Executor  → runs steps in order, stops on failure/confirmation
    ↓
Memory update (log_activity, add_conversation_turn)
    ↓
Response → POST /tts → audio → played back
    ↓
Wake word resumes
```

## Adding a new tool

1. Create `tools/your_tool.py`
2. Decorate each capability with `@action("tool_name", "action_name", "description")`
3. Import it in `tools/__init__.py`

Zero changes needed in executor, planner, or main.py.

## Key design decisions

- **Registry pattern**: tools self-register; no if/elif chains anywhere
- **Multi-step plans**: planner returns a list so "open camera and click pictures" runs both steps
- **Conversation context**: last N turns passed to planner so follow-ups resolve correctly  
- **Validated danger**: shutdown/delete/restart marked `dangerous=True`; executor requires explicit confirmation
- **No hardcoded paths**: everything comes from `config/settings.py`
- **Centralized logger**: `get_logger(__name__)` everywhere instead of `print()` or bare `logging`
