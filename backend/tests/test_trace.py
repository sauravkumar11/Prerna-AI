# -*- coding: utf-8 -*-
"""
Tests for utils/trace.py

The core guarantee this module provides — and the reason it's worth
testing thoroughly — is that a trace ID propagates into EVERY logger call
anywhere in the codebase automatically, with zero changes to any of those
call sites' signatures. That's the property most worth protecting against
regression, since it's easy to accidentally break by, say, making the
contextvar module-instance-specific instead of global, or forgetting to
reset it on exit (which would leak one request's trace ID into another).
"""

from __future__ import annotations

import io
import logging

from utils.logger import get_logger
from utils.trace import new_trace, current_trace_id


def _capture(logger_obj: logging.Logger) -> io.StringIO:
    buf = io.StringIO()
    for h in logger_obj.handlers:
        h.stream = buf
    return buf


def test_no_active_trace_shows_placeholder():
    assert current_trace_id() == "-"


def test_trace_id_is_short_hex_string():
    with new_trace("test") as trace:
        assert len(trace.trace_id) == 8
        assert all(c in "0123456789abcdef" for c in trace.trace_id)


def test_current_trace_id_matches_trace_object_inside_context():
    with new_trace("test") as trace:
        assert current_trace_id() == trace.trace_id


def test_trace_id_resets_after_context_exits():
    with new_trace("test") as trace:
        assert current_trace_id() == trace.trace_id
    assert current_trace_id() == "-"


def test_two_sequential_traces_get_different_ids():
    with new_trace("first") as t1:
        id1 = t1.trace_id
    with new_trace("second") as t2:
        id2 = t2.trace_id
    assert id1 != id2


def test_unmodified_module_logger_picks_up_trace_id_automatically():
    """The core guarantee: a logger from a completely different, unrelated
    module (never touched to add trace support) still gets the trace ID
    injected, purely via the contextvar + logging.Filter mechanism."""
    other_logger = get_logger("some.totally.unrelated.module.for.this.test")
    buf = _capture(other_logger)

    with new_trace("propagation test") as trace:
        other_logger.info("hello from an unrelated module")
        logged = buf.getvalue()

    assert f"[{trace.trace_id}]" in logged


def test_log_line_outside_any_trace_shows_dash():
    other_logger = get_logger("some.other.unrelated.module.for.this.test")
    buf = _capture(other_logger)
    other_logger.info("no trace active right now")
    assert "[-]" in buf.getvalue()


def test_stage_timing_is_recorded():
    trace_container = {}
    with new_trace("timing test") as trace:
        with trace.stage("stage_a"):
            pass
        with trace.stage("stage_b"):
            pass
        trace_container["trace"] = trace

    trace = trace_container["trace"]
    stage_names = [name for name, _ in trace.stages]
    assert stage_names == ["stage_a", "stage_b"]


def test_summary_includes_stage_names_and_total():
    with new_trace("hello world") as trace:
        with trace.stage("context_load"):
            pass
    summary = trace.summary()
    assert "context_load" in summary
    assert "total=" in summary
    assert trace.trace_id in summary


def test_summary_with_no_stages_indicates_early_return():
    with new_trace("early return case") as trace:
        pass
    summary = trace.summary()
    assert "no stages recorded" in summary


def test_duplicate_stage_entry_does_not_warn_on_normal_single_use():
    trace_logger = get_logger("utils.trace")
    buf = _capture(trace_logger)

    with new_trace("normal") as trace:
        with trace.stage("gemini_chat_call"):
            pass

    assert "Duplicate work" not in buf.getvalue()


def test_duplicate_stage_entry_warns_when_genuinely_duplicated():
    """The concrete 'detect duplicate Gemini calls / repeated browser
    creation' feature from the v1.1 brief: entering the SAME stage name
    twice in one request must log a WARNING."""
    trace_logger = get_logger("utils.trace")
    buf = _capture(trace_logger)

    with new_trace("buggy") as trace:
        with trace.stage("gemini_chat_call"):
            pass
        with trace.stage("gemini_chat_call"):
            pass

    logged = buf.getvalue()
    assert "Duplicate work" in logged
    assert "gemini_chat_call" in logged
    assert trace.trace_id in logged


def test_exception_inside_stage_still_records_timing():
    """A stage that raises must still be recorded (so a slow, failing
    stage is still visible in the trace) and the exception must still
    propagate normally — the context manager isn't meant to swallow it."""
    with new_trace("exception test") as trace:
        try:
            with trace.stage("failing_stage"):
                raise ValueError("boom")
        except ValueError:
            pass

    stage_names = [name for name, _ in trace.stages]
    assert "failing_stage" in stage_names