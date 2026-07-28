# PROJECT_CONTEXT.md

# Prerna AI
# PROJECT_CONTEXT.md

# Prerna AI

**Author:** Saurav Kumar  
**Project Owner:** Saurav Kumar

## About the Author

Prerna AI is an independent long-term project created and maintained by **Saurav Kumar**.

The vision is to build Prerna from an AI desktop companion into a full AI Operating System through incremental, production-ready development.

All major architectural decisions are made by the project owner. AI assistants (such as ChatGPT or Claude) are used as engineering collaborators to help with implementation, review, and documentation. Final design decisions remain with the project owner.

## Vision

Prerna is an AI Companion that evolves into an AI Operating System.

The architecture is designed to grow incrementally while keeping every version stable.

---

# Current Version

Prerna Core v1.1

Status:
Stable Development

Current Milestone:
v1.1.1 - Test Infrastructure

---

# Technology Stack

Frontend
- Electron
- React

Backend
- FastAPI
- Python

AI
- Gemini

Speech
- Edge TTS

Automation
- Selenium
- Windows Automation

---

# Architecture

Current Components

- Planner
- Executor
- Memory
- Browser Tools
- Voice
- Logging
- Performance Monitoring

Future Components

- Event Bus
- World State
- Capability Registry
- Plugin System
- Goal Engine
- Vision Engine
- Knowledge Graph

---

# Development Philosophy

- Never rewrite large parts of the project.
- Improve incrementally.
- Keep every release stable.
- Prefer refactoring over rewriting.
- Backward compatibility is important.

---

# Git Workflow

main

↓

develop

↓

feature/*

Never develop directly on main.

---

# Coding Standards

- Production-ready code only.
- No placeholder implementations.
- Keep functions small and focused.
- Avoid duplicate code.
- Follow existing project structure.
- Add logging where appropriate.
- Write tests whenever practical.

---

# Documentation Rules

Whenever architecture changes:

- Update CHANGELOG.md
- Update VERSION_HISTORY.md
- Update ROADMAP.md
- Update ARCHITECTURE.md if needed

---

# Current Roadmap

v1.1.1 Test Infrastructure

↓

v1.1.2 Reliability & Type Safety

↓

v1.1.3 Dependency Cleanup

↓

v1.2 Event Bus

↓

v1.3 World State

↓

v1.4 Capability Registry

↓

v1.5 Plugin Architecture

↓

v1.6 Memory Refactor

↓

v1.7 Goal Engine

↓

v1.8 Vision

↓

v1.9 Autonomous Execution

↓

v2.0 AI Operating System

---

# Rules for AI Assistants

Before making changes:

1. Understand the current architecture.
2. Preserve existing functionality.
3. Avoid unnecessary rewrites.
4. Keep changes focused.
5. Update documentation when required.
6. Explain significant architectural decisions.
7. If unsure, ask before making breaking changes.