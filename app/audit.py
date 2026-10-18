"""
app/audit.py
Audit log: records every tool call, Cypher query, parameters, result row count,
and latency.  Entries stream via SSE and are persisted to JSONL on disk.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# In-memory ring buffer (last 500 entries) for SSE
_entries: list[dict] = []
_MAX_ENTRIES = 500

# Disk persistence
_LOG_DIR = Path("audit_logs")
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FILE = _LOG_DIR / "audit.jsonl"

# Subscribers waiting for new entries (SSE)
_subscribers: list[Any] = []


def log_entry(
    tool: str,
    cypher: str | None,
    params: dict | None,
    result_rows: int | None,
    latency_ms: float,
    success: bool,
    error: str | None = None,
    extra: dict | None = None,
) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "cypher": cypher,
        "params": params,
        "result_rows": result_rows,
        "latency_ms": round(latency_ms, 2),
        "success": success,
        "error": error,
        **(extra or {}),
    }
    _entries.append(entry)
    if len(_entries) > _MAX_ENTRIES:
        _entries.pop(0)

    # Append to disk
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    # Notify SSE subscribers
    for queue in _subscribers:
        try:
            queue.append(entry)
        except Exception:
            pass

    return entry


def subscribe() -> list:
    """Return a mutable list that will receive new audit entries."""
    q: list = []
    _subscribers.append(q)
    return q


def unsubscribe(q: list):
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


def recent(n: int = 100) -> list[dict]:
    return _entries[-n:]


class timer:
    """Context manager: returns elapsed ms."""
    def __init__(self):
        self._start = time.perf_counter()

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000

    def __exit__(self, *_):
        pass
