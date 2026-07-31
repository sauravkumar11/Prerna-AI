"""
Dependencies
============
Gemini model manager: automatic API key rotation on 429 quota errors, model
fallback (e.g. gemini-2.5-flash -> gemini-2.0-flash) if the configured
model itself is unavailable, AND per-(model, key) cooldown tracking.

Uses the modern `google-genai` SDK (the `google-generativeai` package is
deprecated and no longer works reliably with newer API keys / model names).

.env format:
    GEMINI_API_KEY=key1          # required
    GEMINI_API_KEY_2=key2        # optional extras
    GEMINI_API_KEY_3=key3
    ...
    GEMINI_MODEL=gemini-flash-latest   # recommended: auto-tracks the
                                        # current Gemini Flash model so you
                                        # never have to chase a deprecated
                                        # pinned version again.

Retry strategy, per call:
  - Quota error (429) on the current (model, key) pair -> mark that pair in
    cooldown (default 60s, or whatever retry delay Gemini reports), move to
    the next live pair, retry.
  - Model unavailable (404) -> mark the whole model dead for this process
    (long cooldown), move on.
  - No live (model, key) pair remains -> return a friendly in-character
    error immediately, WITHOUT making any network calls for pairs we
    already know are in cooldown. This is the fix for the previous
    behaviour, where every single message re-hammered every key on every
    model from scratch even when we already knew, from seconds earlier,
    that all of them were exhausted — doubling latency and quota pressure
    on an already-throttled account for no benefit.
"""

from __future__ import annotations

import re
import time
from threading import Lock
from typing import Any, Optional

from google import genai
from google.genai import types as genai_types

from config.settings import GEMINI_API_KEYS, GEMINI_MODEL
from utils.logger import get_logger

logger = get_logger(__name__)

# Default cooldown when a quota error doesn't tell us how long to wait.
# Gemini free-tier quotas are typically per-minute, so 60s is a safe floor.
_DEFAULT_QUOTA_COOLDOWN_S = 60.0
# A "model not found / unavailable" error isn't going to fix itself in a
# minute — deprioritize that model for a long time rather than retrying it
# every request.
_MODEL_ERROR_COOLDOWN_S = 3600.0

_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s?", re.IGNORECASE)


def _parse_retry_delay(err_str: str) -> Optional[float]:
    """Best-effort extraction of a server-reported retry delay (Gemini
    sometimes includes `retryDelay: "34s"` in the error details)."""
    match = _RETRY_DELAY_RE.search(err_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


class GeminiKeyManager:
    """Manages a pool of Gemini API keys AND a fallback chain of models,
    with cooldown tracking so exhausted (model, key) pairs are skipped
    instead of re-tried blindly on every call."""

    # NOTE ON MODEL CHOICE — updated after real production evidence:
    # gemini-2.5-flash itself is now returning 404 "no longer available to
    # new users" for some API keys (confirmed from a live log, not a
    # guess) — Google restricts specific pinned model versions per-key
    # based on when the key/project was created, so "2.5-flash works" is
    # no longer a safe assumption even though it's still a valid model
    # name for OTHER (older/grandfathered) keys in the same pool.
    # gemini-flash-latest is Google's own auto-tracking alias — it always
    # points at whatever the current Flash model is, so it isn't subject
    # to this class of per-version deprecation/restriction at all. It's
    # tried first for exactly that reason. gemini-2.5-flash and
    # gemini-2.5-flash-lite remain as fallbacks since they still work for
    # at least some keys in a mixed pool.
    FALLBACK_MODELS = [
        "gemini-flash-latest",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]

    def __init__(self, keys: list[str], model_name: str) -> None:
        if not keys:
            raise ValueError("At least one Gemini API key is required.")

        self._keys = keys
        # Configured model first, then fallbacks — de-duplicated, order kept.
        self._models = list(dict.fromkeys([model_name, *self.FALLBACK_MODELS]))

        self._clients: dict[int, Any] = {}
        self._lock = Lock()
        # (model_idx, key_idx) -> unix timestamp until which this pair is
        # known-dead and should be skipped without a network call.
        self._cooldown_until: dict[tuple[int, int], float] = {}
        # How many consecutive generate_content() CALLS have ended without
        # this model ever succeeding (every key failed/was on cooldown).
        # This is what actually fixes the pattern seen in production: the
        # CONFIGURED primary model (position 0, from .env's GEMINI_MODEL)
        # always got tried first on every single request even after
        # failing on all 6 keys on every one of the last 10 requests in a
        # row — per-call cooldown alone doesn't carry that "this model has
        # been consistently dead across many separate requests" signal
        # forward. This does, and resets to 0 the moment the model
        # succeeds even once, so it's not a permanent demotion.
        self._model_failure_streak: dict[int, int] = {}
        self._init_client(0)

        logger.info(
            "Gemini key manager ready — %d key(s), models: %s",
            len(keys), ", ".join(self._models),
        )

    def _init_client(self, index: int) -> None:
        if index in self._clients:
            return
        self._clients[index] = genai.Client(api_key=self._keys[index])
        logger.debug("Initialised client for key index %d", index)

    def _ordered_model_indices(self) -> list[int]:
        """Models with fewer recent consecutive full-call failures are
        tried first; ties keep the original configured order. A model
        that's failed every key on the last several requests in a row
        gets tried LAST instead of first — still tried (cooldown alone
        governs whether a given pair is skipped entirely), just not
        wastefully first in line every single time."""
        return sorted(
            range(len(self._models)),
            key=lambda m: (self._model_failure_streak.get(m, 0), m),
        )

    def _pairs_in_priority_order(self) -> list[tuple[int, int]]:
        return [(m, k) for m in self._ordered_model_indices() for k in range(len(self._keys))]

    def _live_pairs(self, now: float) -> list[tuple[int, int]]:
        return [
            pair for pair in self._pairs_in_priority_order()
            if self._cooldown_until.get(pair, 0.0) <= now
        ]

    def _mark_cooldown(self, pair: tuple[int, int], seconds: float) -> None:
        with self._lock:
            self._cooldown_until[pair] = time.time() + seconds

    def _bump_failure_streak(self, model_idx: int) -> None:
        """v1.1.2 fix: this read-modify-write was previously unlocked,
        while its sibling _cooldown_until mutation (_mark_cooldown above)
        already was. Since /chat is a sync route running in Starlette's
        thread pool, concurrent requests genuinely execute on different
        OS threads — an unlocked `dict.get(k, 0) + 1` read-then-write can
        race and undercount a genuine failure streak. Low real-world
        impact (worst case: a slightly-stale streak, not a crash), but a
        real correctness gap now closed with the same lock already used
        for cooldown tracking."""
        with self._lock:
            self._model_failure_streak[model_idx] = self._model_failure_streak.get(model_idx, 0) + 1

    def _reset_failure_streak(self, model_idx: int) -> None:
        with self._lock:
            self._model_failure_streak[model_idx] = 0

    def _earliest_available_in(self) -> float:
        """Seconds until the soonest (model, key) pair becomes live again —
        used only to give an honest wait estimate in the fallback message."""
        if not self._cooldown_until:
            return 0.0
        soonest = min(self._cooldown_until.values())
        return max(0.0, soonest - time.time())

    def generate_content(self, prompt: str, generation_config: dict | None = None) -> Any:
        """Call generate_content, skipping any (model, key) pair already
        known to be in cooldown, and cooling down any pair that fails.

        Signature and return shape (an object exposing `.text`) match the
        previous implementation, so callers (chat.py, planner.py) need no
        changes.
        """
        config = genai_types.GenerateContentConfig(**generation_config) if generation_config else None

        now = time.time()
        live_pairs = self._live_pairs(now)

        if not live_pairs:
            wait_s = int(self._earliest_available_in())
            logger.error("All Gemini (model, key) pairs are in cooldown — no network call made.")
            return self._exhausted_response(wait_s)

        last_model_idx = None

        for model_idx, key_idx in live_pairs:
            # Track model transitions BEFORE the live cooldown re-check
            # below, so a model whose remaining keys are all still on
            # cooldown (from an earlier failure this same call) still
            # correctly counts as "fully failed" for this call, not just
            # the ones that made an actual network attempt.
            if last_model_idx is not None and model_idx != last_model_idx:
                self._bump_failure_streak(last_model_idx)
            last_model_idx = model_idx

            # Re-check against CURRENT cooldown state, not just the
            # snapshot taken before this loop started. Without this, an
            # earlier iteration in this SAME call marking a model dead
            # (e.g. a 404 "no longer available") doesn't stop the loop
            # from still trying that model's other precomputed keys —
            # observed in production as 3 wasted sequential 404s for one
            # already-known-dead model before falling through to the next.
            if self._cooldown_until.get((model_idx, key_idx), 0.0) > time.time():
                continue

            model_name = self._models[model_idx]
            self._init_client(key_idx)
            client = self._clients[key_idx]

            try:
                result = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                # Success — this model is clearly working again; drop any
                # accumulated deprioritization immediately rather than
                # waiting for it to decay.
                self._reset_failure_streak(model_idx)
                return result

            except Exception as exc:
                err_str = str(exc)
                status_code = getattr(exc, "code", None)

                is_quota = (
                    status_code == 429
                    or "429" in err_str
                    or "quota" in err_str.lower()
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "rate" in err_str.lower()
                )
                is_model_error = (
                    status_code == 404
                    or "404" in err_str
                    or "NOT_FOUND" in err_str
                    or "not found" in err_str.lower()
                    or "no longer available" in err_str
                )

                if is_model_error:
                    logger.error("Model %s unavailable: %s", model_name, err_str[:200])
                    for k in range(len(self._keys)):
                        self._mark_cooldown((model_idx, k), _MODEL_ERROR_COOLDOWN_S)
                    continue

                if is_quota:
                    delay = _parse_retry_delay(err_str) or _DEFAULT_QUOTA_COOLDOWN_S
                    logger.warning(
                        "Key index %d hit quota on model %s. Cooling down for %.0fs.",
                        key_idx, model_name, delay,
                    )
                    self._mark_cooldown((model_idx, key_idx), delay)
                    continue

                raise  # unexpected error — don't swallow it, let it surface

        # Every live pair we tried this call also failed. The last model
        # attempted never had its transition-out increment applied (there
        # was no "next" model to trigger it) — finalize it here.
        if last_model_idx is not None:
            self._bump_failure_streak(last_model_idx)

        wait_s = int(self._earliest_available_in())
        logger.error("Exhausted every available Gemini (model, key) pair this call.")
        return self._exhausted_response(wait_s)

    @staticmethod
    def _exhausted_response(wait_s: int) -> Any:
        if wait_s > 0:
            hint = f" Should recover in about {wait_s}s — try again shortly."
        else:
            hint = " Please check your .env GEMINI_API_KEY / GEMINI_MODEL settings, or try again in a minute."

        class ExhaustedResponse:
            text = f"[CALM] Saurav, I couldn't reach any configured Gemini model or key right now.{hint}"

        return ExhaustedResponse()


_manager: GeminiKeyManager | None = None


def init_gemini() -> None:
    """Called once from main.py lifespan startup."""
    global _manager
    _manager = GeminiKeyManager(GEMINI_API_KEYS, GEMINI_MODEL)


def get_gemini_model() -> GeminiKeyManager:
    if _manager is None:
        raise RuntimeError("Gemini not initialised — call init_gemini() first.")
    return _manager