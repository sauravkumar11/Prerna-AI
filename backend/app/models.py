"""
Models
======
Pydantic request and response models shared across API routers.

v1.1.2 Enhancement: Added validation and type safety improvements.
- Field validation with min/max lengths
- Enum validation for emotions
- Clear error messages
- Full backward compatibility
"""

from __future__ import annotations

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, validator


class HistoryItem(BaseModel):
    """Chat history entry with validation (v1.1.2)"""
    role: str = Field(..., min_length=1, max_length=20, description="Speaker role (user/assistant)")
    content: str = Field(..., min_length=1, max_length=50000, description="Message content")

    @validator('role')
    def validate_role(cls, v: str) -> str:
        """Validate role is either 'user' or 'assistant'"""
        if v.lower() not in ('user', 'assistant'):
            raise ValueError("Role must be 'user' or 'assistant'")
        return v.lower()


class ChatRequest(BaseModel):
    """Chat request with enhanced validation (v1.1.2)"""
    message: str = Field(..., min_length=1, max_length=50000, description="User message")
    history: List[HistoryItem] = Field(default_factory=list, description="Conversation history")
    confirmed: bool = Field(default=False, description="Dangerous action confirmation")
    # When set, re-executes THIS exact step directly instead of re-invoking
    # the planner on the resent original text. Without this, confirming a
    # dangerous action meant asking Gemini to plan the same message a
    # second time — which, being a non-deterministic LLM call, could (and
    # did, in practice) produce a DIFFERENT plan than the first time, most
    # notably silently rerouting to "chat" instead of re-selecting the
    # same tool action, several turns after the user already said yes.
    confirmed_step: Optional[Dict[str, Any]] = Field(None, description="Confirmed execution step")

    @validator('message')
    def message_not_empty(cls, v: str) -> str:
        """Ensure message is not just whitespace"""
        if not v.strip():
            raise ValueError("Message cannot be empty or whitespace only")
        return v.strip()

    @validator('history')
    def limit_history(cls, v: List[HistoryItem]) -> List[HistoryItem]:
        """Limit history to last 100 messages to prevent memory issues"""
        if len(v) > 100:
            return v[-100:]
        return v


class TTSRequest(BaseModel):
    """Text-to-speech request with enhanced validation (v1.1.2)"""
    message: str = Field(..., min_length=1, max_length=10000, description="Text to speak")
    emotion: str = Field(default="CALM", description="Emotion tag for TTS")

    @validator('emotion')
    def validate_emotion(cls, v: str) -> str:
        """Validate emotion is a supported value"""
        valid_emotions = {
            "CALM", "HAPPY", "SAD", "ANGRY", "SURPRISED",
            "EXCITED", "FEARFUL", "DISGUSTED", "NEUTRAL"
        }
        v_upper = v.upper()
        if v_upper not in valid_emotions:
            raise ValueError(f"Emotion must be one of {valid_emotions}, got '{v}'")
        return v_upper

    @validator('message')
    def message_not_empty(cls, v: str) -> str:
        """Ensure message is not just whitespace"""
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()


class ChatResponse(BaseModel):
    """Chat response model (v1.1.2)"""
    response: str = Field(..., description="Response text")
    requires_confirmation: bool = Field(default=False, description="Needs user confirmation")

    class Config:
        """Pydantic config for response"""
        json_schema_extra = {
            "example": {
                "response": "Done",
                "requires_confirmation": False
            }
        }
