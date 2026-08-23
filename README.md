# Prerna

## Author

**Saurav Kumar**

Creator and maintainer of **Prerna AI**.

Prerna AI is a long-term research and engineering project focused on building a next-generation AI companion that evolves into an AI Operating System.


> **An AI Companion for Windows**

Prerna is an intelligent desktop AI companion designed to function as a personal AI operating layer rather than a traditional chatbot.

Instead of only answering questions, Prerna can understand context, remember information, automate Windows, interact with applications, control browsers, execute multi-step tasks, and assist users through natural conversations.

The long-term vision is to evolve Prerna into a production-grade AI Operating System capable of perception, reasoning, planning, execution, and long-term memory.

---

# Current Status

**Current Version**

Prerna Core **v1.1**

**Development Stage**

Active Development

**Architecture Philosophy**

Incremental Evolution

---

# Features

Current capabilities include:

- Natural voice conversation
- Google Gemini integration
- Long-term memory
- Session memory
- Desktop automation
- Browser automation
- WhatsApp automation
- YouTube automation
- Application launcher
- Planner & Executor
- Instant intent engine
- Performance tracing
- Structured logging
- Chrome session management
- Context-aware conversations

---

# Technology Stack

## Backend

- Python
- FastAPI
- Google Gemini API
- Selenium
- PyAutoGUI
- Edge TTS
- SQLite / JSON Memory

## Frontend

- Electron
- React

---

# Project Philosophy

Prerna is intentionally developed **incrementally**.

The objective is **not** to rewrite the project repeatedly.

Instead:

- Preserve existing functionality
- Improve architecture version by version
- Build production-ready features
- Maintain backward compatibility
- Add automated tests before major refactors
- Measure performance before optimizing

---

# Development Roadmap

## Completed

- ✅ Prerna Core v1.1 — Performance Foundation

## Planned

- 🔄 v1.1.1 — Test Infrastructure
- 🔄 v1.1.2 — Reliability & Type Safety
- 🔄 v1.1.3 — Dependency & Cleanup
- 🔄 v1.2 — Event Bus
- 🔄 v1.3 — World State
- 🔄 v1.4 — Capability Registry
- 🔄 v1.5 — Plugin System
- 🔄 v1.6 — Memory Refactor
- 🔄 v1.7 — Goal Engine
- 🔄 v1.8 — Vision Engine
- 🔄 v1.9 — Autonomous Execution
- 🚀 v2.0 — Prerna AI Operating System

---

# Repository Structure

```
backend/
frontend/
docs/
tests/
scripts/
```

---

# Development Workflow

Every version follows the same lifecycle:

1. Plan
2. Review
3. Implement
4. Test
5. Verify
6. Release
7. Tag

Large rewrites are intentionally avoided.

---

# Versioning

Prerna follows Semantic Versioning.

Examples:

- v1.1.0
- v1.1.1
- v1.2.0
- v2.0.0

---

# Testing

Every architectural change should include automated regression tests whenever practical.

No feature is considered complete until it has been verified.

---

# Documentation

The `docs/` directory contains:

- Architecture
- Roadmap
- Design Decisions
- Version History
- Release Notes

These documents are treated as the project's source of truth.

---

# Security

Sensitive files such as `.env`, API keys, tokens, and credentials are never committed.

---

# License

To be selected before public release.

---

# Future Vision

Prerna aims to become an AI Operating System capable of:

- Continuous perception
- Context awareness
- Long-term memory
- Goal-based planning
- Desktop understanding
- Browser understanding
- Personal intelligence
- Autonomous task execution
- Natural conversations
- Plugin-based extensibility

The project emphasizes stability, maintainability, and long-term evolution over rapid feature growth.
