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

Prerna Core **v1.1.1** ✅ (Latest)

**Latest Release Highlights**
- ✅ Comprehensive Test Infrastructure (75+ tests)
- ✅ Reminder & Task Management System
- ✅ Type Safety & Error Handling Framework
- ✅ Full backward compatibility maintained

**Development Stage**

Active Development

**Architecture Philosophy**

Incremental Evolution

---

# Features

Current capabilities include:

## Core AI & Conversation
- Natural voice conversation (Hindi & English)
- Google Gemini integration for reasoning
- Long-term memory & short-term session memory
- Conversation history & context awareness
- Emotion detection & personality tags

## Productivity & Task Management ✨ NEW in v1.1.1
- **Reminder & Task System**
  - Create, list, complete, and delete tasks
  - Filter by priority, status, category
  - Overdue detection & due date management
  - Persistent JSON-based storage
  - Automatic summarization & analytics
  - Natural language voice commands

## Desktop & System Automation
- Desktop automation (lock, shutdown, restart)
- Application launcher (20+ apps)
- Browser automation & web navigation
- WhatsApp automation (send messages, calls)
- YouTube automation (play, pause, next)
- Instagram automation
- File operations & clipboard management
- Screenshot & camera control
- Volume & Bluetooth control
- WiFi management

## Advanced Features
- Planner & Executor for multi-step tasks
- Instant intent engine for fast responses
- Predictive assistant (proactive suggestions)
- Performance tracing & structured logging
- Chrome session management
- Email integration
- Alarm & note management
- Coding assistance
- Search integration

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
- ✅ **v1.1.1 — Test Infrastructure & Reminder System** (Current)
  - 75+ comprehensive tests
  - Reminder & Task management
  - Type system & error handling
  - Full backward compatibility

## In Progress & Planned

- 🔄 v1.1.2 — Reliability & Type Safety Enhancements
- 🔄 v1.1.3 — Dependency Updates & Cleanup
- 🔄 v1.2 — Event Bus Architecture
- 🔄 v1.3 — World State Management
- 🔄 v1.4 — Enhanced Capability Registry
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
