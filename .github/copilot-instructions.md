# Prerna AI Development Instructions

Prerna is a long-term AI Companion project.

## Core Philosophy

- Never perform large-scale rewrites.
- Preserve existing functionality.
- Improve architecture incrementally.
- Every version must remain stable.
- Prefer refactoring over rewriting.
- Always maintain backward compatibility unless explicitly approved.

---

## Current Version

Prerna Core v1.1

---

## Development Workflow

Every feature follows:

Plan

↓

Architecture Review

↓

Implementation

↓

Testing

↓

Verification

↓

Documentation

↓

Release

---

## Coding Standards

- Production-ready code only.
- No placeholder implementations.
- No duplicated logic.
- Keep functions focused.
- Use meaningful names.
- Prefer composition over inheritance.
- Use asynchronous programming where appropriate.

---

## Architecture Goals

Future architecture includes:

- Event Bus
- World State
- Capability Registry
- Plugin System
- Goal Engine
- Knowledge Graph
- Vision Engine

Do not implement future architecture unless the current version specifically requires it.

---

## Documentation

Update documentation whenever architecture changes.

---

## Testing

Every new feature should include tests whenever practical.

---

## Security

Never expose API keys.

Never commit credentials.

Never hardcode secrets.

Use .env.

---

## Git

Never work directly on main.

Always develop using:

feature/*

↓

develop

↓

main