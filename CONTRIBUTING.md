# Contributing to Prerna AI

Thank you for contributing.

## Branch Strategy

Never commit directly to `main`.

Use:

feature/*

↓

develop

↓

main

---

## Commit Messages

Examples:

feat: add browser session manager

fix: resolve memory leak in executor

refactor: simplify planner routing

docs: update roadmap

test: add planner unit tests

---

## Development Process

1. Create an issue.
2. Create a feature branch.
3. Implement the change.
4. Test locally.
5. Update documentation if needed.
6. Open a Pull Request.
7. Merge into `develop`.

---

## Coding Standards

- Follow the existing architecture.
- Keep code modular.
- Prefer readability over cleverness.
- Avoid duplicated logic.
- Add comments only when they improve understanding.

---

## Testing

Before submitting:

- Backend starts successfully.
- Frontend builds successfully.
- Existing functionality still works.
- New functionality is tested.

---

## Documentation

If your change affects:

- architecture
- roadmap
- APIs
- configuration

Update the relevant documentation.

---

## Pull Requests

Every PR should include:

- Summary
- Motivation
- Testing performed
- Documentation updates (if applicable)

---

## Philosophy

Prerna evolves through small, well-tested improvements.

Avoid large rewrites unless explicitly planned.