"""Per-turn stage tracing — answers "which stage of the round-trip is slow?".

Local addition (not upstream Hermes). Opt-in via ``HERMES_TURN_TRACE=1`` in
the environment or ``~/.hermes/.env``. When disabled, ``mark()`` returns after
one module-level boolean check, so the turn path pays nothing.

Each call appends one JSON object to ``<hermes_home>/logs/turn_trace.jsonl``::

    {"t": 1785240000.123, "stage": "handler_enter", "chat": "...@lid"}

``t`` is wall-clock seconds (``time.time()``), directly comparable to the
bridge's ``Date.now()/1000`` and to the timestamps in ``gateway.log`` /
``agent.log``, which is what lets the waterfall span the Node/Python split.

Stages emitted by the current probes, in round-trip order::

    bridge (node)   upsert -> queued -> drained -> [send_recv -> send_done]
    adapter (py)    bridge_recv -> debounce_start -> debounce_flush
    gateway (py)    handler_enter -> history_loaded -> text_prepared
                    -> agent_start -> agent_done -> send_start -> send_done
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

_TRUTHY = ("1", "true", "yes", "on")

ENABLED = os.environ.get("HERMES_TURN_TRACE", "").strip().lower() in _TRUTHY

_LOCK = threading.Lock()
_PATH: Path | None = None


def _resolve_path() -> Path:
    """Locate the trace file, honouring the active Hermes profile."""
    override = os.environ.get("HERMES_TURN_TRACE_FILE")
    if override:
        return Path(override)
    try:
        from hermes_constants import get_hermes_home

        home = get_hermes_home()
    except Exception:
        home = Path.home() / ".hermes"
    return Path(home) / "logs" / "turn_trace.jsonl"


def mark(stage: str, chat: str | None = None, **fields) -> None:
    """Record that ``stage`` was reached now. Never raises, never blocks long."""
    if not ENABLED:
        return
    global _PATH
    record = {"t": round(time.time(), 3), "stage": stage}
    if chat:
        record["chat"] = str(chat)
    for key, value in fields.items():
        if value is not None:
            record[key] = value
    try:
        with _LOCK:
            if _PATH is None:
                _PATH = _resolve_path()
                _PATH.parent.mkdir(parents=True, exist_ok=True)
            with _PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Tracing is diagnostic; a full disk or a read-only log dir must never
        # take down a turn.
        pass
