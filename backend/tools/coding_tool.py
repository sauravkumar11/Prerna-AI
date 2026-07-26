"""
Coding tool
===========
Git operations always take an explicit repo path - Prerna doesn't guess
"the current project" since there isn't a reliable notion of one from a
voice command alone.
"""

from __future__ import annotations

import subprocess
import webbrowser

from agent.registry import ToolResult, action

TOOL_DESCRIPTION = "Open a project in VS Code, run basic git commands, or jump to a localhost port."


def _git(repo_path: str, args: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo_path] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )


@action("coding", "open_project", "Open a project folder in VS Code.", required_args=["path"], tool_description=TOOL_DESCRIPTION)
def open_project(path: str) -> ToolResult:
    subprocess.Popen(["code", path], shell=True)
    return ToolResult(True, f"Opening {path} in VS Code.")


@action("coding", "git_status", "Show git status for a repo.", required_args=["path"])
def git_status(path: str) -> ToolResult:
    result = _git(path, ["status", "--short", "--branch"])
    if result.returncode != 0:
        return ToolResult(False, result.stderr.strip() or "That doesn't look like a git repo.")
    return ToolResult(True, result.stdout.strip() or "Working tree clean.", data={"raw": result.stdout})


@action("coding", "git_pull", "Pull the latest changes.", required_args=["path"])
def git_pull(path: str) -> ToolResult:
    result = _git(path, ["pull"])
    if result.returncode != 0:
        return ToolResult(False, result.stderr.strip() or "Pull failed.")
    return ToolResult(True, result.stdout.strip() or "Already up to date.")


@action("coding", "git_push", "Push committed changes.", required_args=["path"])
def git_push(path: str) -> ToolResult:
    result = _git(path, ["push"])
    if result.returncode != 0:
        return ToolResult(False, result.stderr.strip() or "Push failed.")
    return ToolResult(True, result.stdout.strip() or "Pushed.")


@action("coding", "git_commit", "Commit staged changes with a message.", required_args=["path", "message"])
def git_commit(path: str, message: str) -> ToolResult:
    result = _git(path, ["commit", "-m", message])
    if result.returncode != 0:
        return ToolResult(False, result.stderr.strip() or "Nothing to commit, or commit failed.")
    return ToolResult(True, result.stdout.strip() or "Committed.")


@action("coding", "open_localhost", "Open a localhost port in the browser.", required_args=["port"])
def open_localhost(port: int) -> ToolResult:
    webbrowser.open(f"http://localhost:{port}")
    return ToolResult(True, f"Opening localhost:{port}.")
