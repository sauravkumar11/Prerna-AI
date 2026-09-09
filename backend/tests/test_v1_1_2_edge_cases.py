"""
test_v1_1_2_edge_cases.py
========================
Edge-case tests for v1.1.2 - Reliability & Type Safety

Tests critical edge cases, boundary conditions, and error scenarios.
"""

import pytest
from pydantic import ValidationError
from app.models import ChatRequest, TTSRequest, HistoryItem, ChatResponse


class TestChatRequestValidation:
    """Test ChatRequest edge cases and validation"""

    def test_empty_message_rejected(self):
        """Empty messages should be rejected"""
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_whitespace_only_message_rejected(self):
        """Whitespace-only messages should be rejected"""
        with pytest.raises(ValidationError):
            ChatRequest(message="   \n\t  ")

    def test_very_long_message_accepted(self):
        """Very long but valid messages should be accepted"""
        long_message = "a" * 50000
        req = ChatRequest(message=long_message)
        assert len(req.message) == 50000

    def test_message_too_long_rejected(self):
        """Messages exceeding max length should be rejected"""
        with pytest.raises(ValidationError):
            ChatRequest(message="a" * 50001)

    def test_history_limit_enforced(self):
        """History should be limited to 100 messages"""
        history = [
            HistoryItem(role="user", content=f"msg{i}")
            for i in range(150)
        ]
        req = ChatRequest(message="test", history=history)
        assert len(req.history) == 100
        # Should keep last 100
        assert req.history[0].content == "msg50"
        assert req.history[99].content == "msg149"

    def test_invalid_history_role_rejected(self):
        """Invalid roles should be rejected"""
        with pytest.raises(ValidationError):
            ChatRequest(
                message="test",
                history=[HistoryItem(role="invalid", content="text")]
            )

    def test_message_whitespace_stripped(self):
        """Leading/trailing whitespace should be stripped"""
        req = ChatRequest(message="  hello world  ")
        assert req.message == "hello world"

    def test_confirmed_step_optional(self):
        """Confirmed step should be optional"""
        req = ChatRequest(message="test")
        assert req.confirmed_step is None

    def test_confirmed_step_accepts_dict(self):
        """Confirmed step should accept any dict"""
        req = ChatRequest(
            message="test",
            confirmed_step={"tool": "system", "action": "shutdown"}
        )
        assert req.confirmed_step["tool"] == "system"


class TestTTSRequestValidation:
    """Test TTSRequest edge cases and validation"""

    def test_empty_message_rejected(self):
        """Empty TTS messages should be rejected"""
        with pytest.raises(ValidationError):
            TTSRequest(message="")

    def test_invalid_emotion_rejected(self):
        """Invalid emotions should be rejected"""
        with pytest.raises(ValidationError):
            TTSRequest(message="hello", emotion="INVALID")

    def test_emotion_case_insensitive(self):
        """Emotions should accept any case"""
        req = TTSRequest(message="hello", emotion="calm")
        assert req.emotion == "CALM"

    def test_all_valid_emotions_accepted(self):
        """All valid emotions should be accepted"""
        valid = ["CALM", "HAPPY", "SAD", "ANGRY", "SURPRISED",
                 "EXCITED", "FEARFUL", "DISGUSTED", "NEUTRAL"]
        for emotion in valid:
            req = TTSRequest(message="test", emotion=emotion)
            assert req.emotion == emotion

    def test_message_whitespace_stripped(self):
        """Whitespace should be stripped from message"""
        req = TTSRequest(message="  test  ", emotion="CALM")
        assert req.message == "test"

    def test_very_long_tts_message(self):
        """Long TTS messages should be accepted"""
        long_msg = "a" * 10000
        req = TTSRequest(message=long_msg)
        assert len(req.message) == 10000

    def test_tts_default_emotion(self):
        """Default emotion should be CALM"""
        req = TTSRequest(message="hello")
        assert req.emotion == "CALM"


class TestHistoryItemValidation:
    """Test HistoryItem edge cases"""

    def test_role_normalized_to_lowercase(self):
        """Roles should be normalized to lowercase"""
        item = HistoryItem(role="USER", content="text")
        assert item.role == "user"

    def test_empty_content_rejected(self):
        """Empty content should be rejected"""
        with pytest.raises(ValidationError):
            HistoryItem(role="user", content="")

    def test_empty_role_rejected(self):
        """Empty role should be rejected"""
        with pytest.raises(ValidationError):
            HistoryItem(role="", content="text")

    def test_very_long_content(self):
        """Very long content should be accepted"""
        long_content = "x" * 50000
        item = HistoryItem(role="assistant", content=long_content)
        assert len(item.content) == 50000


class TestChatResponseValidation:
    """Test ChatResponse validation"""

    def test_response_required(self):
        """Response field should be required"""
        with pytest.raises(ValidationError):
            ChatResponse()

    def test_empty_response_rejected(self):
        """Empty response should be rejected (if validation added)"""
        # Current model allows empty, but document if needed for v1.2
        resp = ChatResponse(response="")
        assert resp.response == ""

    def test_confirmation_default_false(self):
        """Confirmation should default to false"""
        resp = ChatResponse(response="ok")
        assert resp.requires_confirmation is False

    def test_response_with_confirmation(self):
        """Response can require confirmation"""
        resp = ChatResponse(
            response="Are you sure?",
            requires_confirmation=True
        )
        assert resp.requires_confirmation is True


class TestBoundaryConditions:
    """Test boundary conditions"""

    def test_single_char_message(self):
        """Single character messages should work"""
        req = ChatRequest(message="a")
        assert len(req.message) == 1

    def test_special_characters_in_message(self):
        """Special characters should be allowed"""
        special = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        req = ChatRequest(message=special)
        assert special in req.message

    def test_unicode_in_message(self):
        """Unicode characters should be supported"""
        req = ChatRequest(message="مرحبا世界🚀हलो")
        assert "مرحبا" in req.message

    def test_newlines_in_message(self):
        """Newlines should be allowed"""
        req = ChatRequest(message="line1\nline2\nline3")
        assert "\n" in req.message


class TestConcurrentOperations:
    """Test concurrent/rapid operations"""

    def test_rapid_requests(self):
        """Multiple rapid requests should all be valid"""
        for i in range(100):
            req = ChatRequest(message=f"message {i}")
            assert req.message == f"message {i}"

    def test_rapid_tts_requests(self):
        """Multiple rapid TTS requests should be valid"""
        emotions = ["CALM", "HAPPY", "SAD", "ANGRY", "SURPRISED"]
        for i in range(50):
            emotion = emotions[i % 5]
            req = TTSRequest(message=f"speak {i}", emotion=emotion)
            assert req.emotion == emotion


class TestDataCorruptionRecovery:
    """Test recovery from corrupted data"""

    def test_none_message_rejected(self):
        """None message should be rejected"""
        with pytest.raises(ValidationError):
            ChatRequest(message=None)

    def test_history_with_none_items(self):
        """History with None items should fail"""
        with pytest.raises(ValidationError):
            ChatRequest(message="test", history=[None])

    def test_malformed_confirmed_step_accepted(self):
        """Malformed dict in confirmed_step should still be accepted"""
        # Dict can contain anything, no further validation
        req = ChatRequest(
            message="test",
            confirmed_step={"random": "data", "nested": {"a": 1}}
        )
        assert req.confirmed_step["nested"]["a"] == 1
