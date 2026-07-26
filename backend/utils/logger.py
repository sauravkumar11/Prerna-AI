"""
Logger
======
Single-place logger setup.  Every module does:

    from utils.logger import get_logger
    logger = get_logger(__name__)

instead of calling logging.basicConfig() in multiple places or using print().

Every log line now automatically includes the current request's Trace ID
(via a logging.Filter reading utils.trace's contextvar) — this required NO
change to the get_logger(name) signature or to any of the hundreds of
existing logger.info(...)/warning(...)/etc. call sites across the
codebase. A log line outside any active trace (e.g. during startup) shows
"-" for the trace ID instead of a blank/broken field.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


class _TraceIdFilter(logging.Filter):
    """Injects the current request's trace ID (if any) into every log
    record as record.trace_id, so it can be included in the format string
    without any call site needing to pass it explicitly."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Local import to avoid a circular import at module load time
        # (utils.trace imports get_logger from this module).
        from utils.trace import current_trace_id
        record.trace_id = current_trace_id()
        return True


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # already configured (e.g. uvicorn reloads)

    if level is None:
        level = logging.DEBUG if _is_debug() else logging.INFO

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(_TraceIdFilter())

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  [%(trace_id)s]  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.propagate = False

    return logger


def _is_debug() -> bool:
    import os
    return os.getenv("LOG_LEVEL", "").upper() == "DEBUG"