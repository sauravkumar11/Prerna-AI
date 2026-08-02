# -*- coding: utf-8 -*-
"""
Tests for app/dependencies.py — GeminiKeyManager

Every test here mocks google.genai.Client directly (the real SDK boundary)
rather than the whole module, so these tests exercise the actual retry/
cooldown/deprioritization logic, not a re-implementation of it. Three
properties get the heaviest coverage because they map directly to real
incidents found via production trace logs this session:

1. Cooldown tracking must actually stop re-hammering a known-dead
   (model, key) pair on the VERY NEXT call, not just within one call.
2. A model-unavailable (404) error must not waste repeat attempts on the
   SAME dead model within one call (the "3 wasted 404s in a row" bug).
3. A model that's failed on every key across several SEPARATE requests
   must get deprioritized in try-order on subsequent requests (the
   "gemini-2.5-flash fails 100% of the time but still tried first on
   every single message" bug) — and must self-heal the moment it
   succeeds again.
"""

from __future__ import annotations

import time
import unittest.mock as mock

import app.dependencies as deps


class _FakeError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


def _make_client_factory(behavior):
    """behavior: dict[(model, api_key)] -> Exception instance, or None for
    a normal success. Returns a class usable as google.genai.Client."""

    class _FakeClient:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.models = self

        def generate_content(self, model, contents, config):
            err = behavior.get((model, self.api_key))
            if err is not None:
                raise err
            class _R:
                text = f"ok from {self.api_key} on {model}"
            return _R()

    return _FakeClient


def test_successful_call_returns_result_text():
    behavior = {}
    with mock.patch.object(deps.genai, "Client", _make_client_factory(behavior)):
        mgr = deps.GeminiKeyManager(["k0"], "gemini-flash-latest")
        result = mgr.generate_content("hello")
        assert result.text == "ok from k0 on gemini-flash-latest"


def test_quota_error_rotates_to_next_key():
    behavior = {("gemini-flash-latest", "k0"): _FakeError("429 RESOURCE_EXHAUSTED quota", code=429)}
    with mock.patch.object(deps.genai, "Client", _make_client_factory(behavior)):
        mgr = deps.GeminiKeyManager(["k0", "k1"], "gemini-flash-latest")
        result = mgr.generate_content("hello")
        assert result.text == "ok from k1 on gemini-flash-latest"


def test_cooldown_prevents_repeat_call_on_known_dead_key():
    """The fix for the original quota-exhaustion bug: once a key is known
    dead, the NEXT call must not waste a network call re-testing it."""
    call_log = []
    class _AlwaysQuotaClient:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.models = self
        def generate_content(self, model, contents, config):
            call_log.append((model, self.api_key))
            raise _FakeError("429 RESOURCE_EXHAUSTED quota", code=429)

    with mock.patch.object(deps.genai, "Client", _AlwaysQuotaClient):
        mgr = deps.GeminiKeyManager(["k0", "k1"], "gemini-flash-latest")

        # First call: must genuinely try every (model, key) pair at least
        # once (nothing known dead yet). Deliberately NOT hardcoding an
        # exact count here — FALLBACK_MODELS' length has already changed
        # twice this session, so pinning to today's exact model count
        # would make this test brittle for the wrong reason.
        result1 = mgr.generate_content("hello")
        assert "couldn't reach" in result1.text.lower()
        calls_after_first = len(call_log)
        assert calls_after_first > 0

        # Second call, immediately after: every (model, key) pair tried
        # above is now known dead from the first call — must fail with
        # ZERO new network calls.
        call_log.clear()
        result2 = mgr.generate_content("hello again")
        assert len(call_log) == 0
        assert "couldn't reach" in result2.text.lower()


def test_model_error_does_not_waste_repeat_attempts_within_one_call():
    """Regression test for a real production bug: a 404 'no longer
    available' on model A wasted 2 MORE calls to the same dead model
    (other keys) within the SAME generate_content() call, because the
    live-pairs list was a stale snapshot taken before the model was
    marked dead. Must be exactly 1 wasted call, not 3."""
    call_log = []

    class _Client:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.models = self
        def generate_content(self, model, contents, config):
            call_log.append((model, self.api_key))
            if model == "gemini-2.5-flash":
                raise _FakeError(
                    "404 NOT_FOUND. This model models/gemini-2.5-flash is no longer available to new users.",
                    code=404,
                )
            class _R:
                text = f"ok from {self.api_key} on {model}"
            return _R()

    with mock.patch.object(deps.genai, "Client", _Client):
        mgr = deps.GeminiKeyManager(["k0", "k1", "k2"], "gemini-2.5-flash")
        result = mgr.generate_content("hello")

        dead_model_calls = [c for c in call_log if c[0] == "gemini-2.5-flash"]
        assert len(dead_model_calls) == 1, (
            f"expected exactly 1 wasted call on the known-dead model, got {len(dead_model_calls)}: {call_log}"
        )
        assert "ok from" in result.text


def test_model_deprioritized_after_full_failure_across_separate_requests():
    """Regression test for a real production bug: the CONFIGURED primary
    model (position 0) kept getting tried first on every single request
    even after failing on every key on every one of the last several
    requests in a row. After the model fails completely once, subsequent
    SEPARATE requests must go straight to a working model with zero
    wasted calls."""
    call_log = []

    class _Client:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.models = self
        def generate_content(self, model, contents, config):
            call_log.append(model)
            if model == "gemini-2.5-flash":
                raise _FakeError("429 RESOURCE_EXHAUSTED quota", code=429)
            class _R:
                text = f"ok on {model}"
            return _R()

    with mock.patch.object(deps.genai, "Client", _Client):
        mgr = deps.GeminiKeyManager(["k0", "k1", "k2"], "gemini-2.5-flash")

        # Request 1: has to discover the model is dead — wastes 3 calls.
        mgr._cooldown_until.clear()
        call_log.clear()
        mgr.generate_content("msg 1")
        assert call_log.count("gemini-2.5-flash") == 3

        # Requests 2 and 3 (separate calls, simulating separate /chat
        # requests, with enough time having passed for cooldowns to
        # clear): must go straight to the working model, zero wasted
        # calls on the chronically-dead one.
        for i in range(2, 4):
            mgr._cooldown_until.clear()
            call_log.clear()
            mgr.generate_content(f"msg {i}")
            assert call_log.count("gemini-2.5-flash") == 0, (
                f"request {i}: still wasting calls on a chronically-dead model: {call_log}"
            )


def test_model_deprioritization_self_heals_on_success():
    """A model's failure streak must reset to 0 the moment it succeeds
    again — this is not a permanent demotion.

    Note: with the REAL fallback chain (3 models), a deprioritized model
    that still has a working alternative available correctly never gets
    retried again — that's intentional (see test above: no point wasting
    a call re-testing a demoted model when something else already works).
    So to actually exercise the reset-on-success path, every OTHER model
    is also made to fail here, forcing gemini-2.5-flash to be attempted
    despite its streak — which is exactly when self-healing matters."""
    state = {"flash_2_5_works": False}

    class _Client:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.models = self
        def generate_content(self, model, contents, config):
            if model == "gemini-2.5-flash" and state["flash_2_5_works"]:
                class _R:
                    text = f"ok on {model}"
                return _R()
            raise _FakeError("429 RESOURCE_EXHAUSTED quota", code=429)

    with mock.patch.object(deps.genai, "Client", _Client):
        mgr = deps.GeminiKeyManager(["k0"], "gemini-2.5-flash")

        # Everything fails, including gemini-2.5-flash — it accumulates a
        # failure streak like every other model attempted this call.
        mgr._cooldown_until.clear()
        mgr.generate_content("everything fails")
        model_idx = mgr._models.index("gemini-2.5-flash")
        assert mgr._model_failure_streak.get(model_idx, 0) > 0

        # Now ONLY gemini-2.5-flash works — since the others still fail,
        # the manager is forced to eventually reach it despite the streak,
        # and on success its streak must reset to 0.
        state["flash_2_5_works"] = True
        mgr._cooldown_until.clear()
        result = mgr.generate_content("only 2.5-flash works now")
        assert "ok on gemini-2.5-flash" in result.text
        assert mgr._model_failure_streak.get(model_idx, 0) == 0


def test_retry_delay_parsed_from_error_message():
    err_str = "429 RESOURCE_EXHAUSTED. retryDelay: '34s'"
    delay = deps._parse_retry_delay(err_str)
    assert delay == 34.0


def test_retry_delay_defaults_when_not_present():
    assert deps._parse_retry_delay("some unrelated error") is None


def test_exhausted_response_mentions_wait_time_when_known():
    response = deps.GeminiKeyManager._exhausted_response(37)
    assert "37s" in response.text


def test_exhausted_response_gives_env_hint_when_wait_unknown():
    response = deps.GeminiKeyManager._exhausted_response(0)
    assert ".env" in response.text


def test_model_failure_streak_thread_safe_under_real_concurrency():
    """v1.1.2 fix: _model_failure_streak's read-modify-write increments
    were previously unlocked, unlike its sibling _cooldown_until (which
    already used self._lock). Since /chat is a sync FastAPI route,
    Starlette runs it in a thread pool — concurrent requests genuinely
    execute on different OS threads, not just interleaved coroutines.

    This test uses REAL threading.Thread workers (not asyncio, not
    sequential calls) to actually exercise the race: N threads each
    trigger 3 increments (one per model, since all 3 models fail on
    every call in this scenario). Without the lock, some increments would
    be lost to a classic read-then-write race. With it, the final count
    must be EXACTLY N per model — no lost updates."""
    import threading

    class _AlwaysFailClient:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.models = self
        def generate_content(self, model, contents, config):
            raise _FakeError("429 RESOURCE_EXHAUSTED quota", code=429)

    with mock.patch.object(deps.genai, "Client", _AlwaysFailClient):
        mgr = deps.GeminiKeyManager(["k0"], "gemini-2.5-flash")

        N_THREADS = 20

        def worker():
            mgr._cooldown_until.clear()
            mgr.generate_content("concurrent test")

        threads = [threading.Thread(target=worker) for _ in range(N_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Every model index attempted (all 3, since every call fails on
        # all of them) must show EXACTLY N_THREADS — any lost update from
        # an unlocked race would show up as a count strictly less than
        # N_THREADS on at least one key.
        assert len(mgr._model_failure_streak) == len(mgr._models)
        for model_idx, count in mgr._model_failure_streak.items():
            assert count == N_THREADS, (
                f"model index {model_idx} has count {count}, expected exactly {N_THREADS} "
                "— a lower count means a lost update from an unprotected race"
            )