"""
Models
======
Pydantic request and response models shared across API routers.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel


class HistoryItem(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[HistoryItem] = []
    confirmed: bool = False  # True = user has confirmed a dangerous action
    # When set, re-executes THIS exact step directly instead of re-invoking
    # the planner on the resent original text. Without this, confirming a
    # dangerous action meant asking Gemini to plan the same message a
    # second time — which, being a non-deterministic LLM call, could (and
    # did, in practice) produce a DIFFERENT plan than the first time, most
    # notably silently rerouting to "chat" instead of re-selecting the
    # same tool action, several turns after the user already said yes.
    confirmed_step: dict | None = None


class TTSRequest(BaseModel):
    message: str
    emotion: str = "CALM"


class ChatResponse(BaseModel):
    response: str
    requires_confirmation: bool = False
