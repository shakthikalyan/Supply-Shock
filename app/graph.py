"""
app/graph.py
FalkorDB client with read/write guards, parameterised-only queries,
and automatic audit logging of every call.
"""

import os
import time
from pathlib import Path
from typing import Any

import falkordb

from app import audit

# ── Config ────────────────────────────────────────────────────────────────────
_URL = os.getenv("FALKORDB_URL")
_HOST = os.getenv("FALKORDB_HOST", "localhost")
_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
_PASSWORD = os.getenv("FALKORDB_PASSWORD")
GRAPH_NAME = os.getenv("GRAPH_NAME", "supplyshock")
QUERY_DIR = Path(__file__).parent.parent / "queries"

# ── Connection (lazy) ─────────────────────────────────────────────────────────
_client: falkordb.FalkorDB | None = None
_graph: falkordb.Graph | None = None


def _get_graph() -> falkordb.Graph:
    global _client, _graph
    if _graph is None:
        if _URL:
            _client = falkordb.FalkorDB.from_url(_URL)
        else:
            host = _HOST
            port = _PORT
            if ":" in str(host) and not str(host).startswith("["):
                parts = host.split(":")
                host = parts[0]
                try:
                    port = int(parts[1])
                except ValueError:
                    pass
            kwargs: dict[str, Any] = {"host": host, "port": port}
            if _PASSWORD:
                kwargs["password"] = _PASSWORD
                kwargs["username"] = os.getenv("FALKORDB_USERNAME", "falkordb")
            _client = falkordb.FalkorDB(**kwargs)
        _graph = _client.select_graph(GRAPH_NAME)
    return _graph


def is_available() -> bool:
    try:
        g = _get_graph()
        g.query("RETURN 1")
        return True
    except Exception:
        return False


# ── Query helpers ─────────────────────────────────────────────────────────────

def _load_cypher(filename: str) -> str:
    """Load a .cypher file from the queries/ directory."""
    path = QUERY_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Cypher file not found: {path}")
    return path.read_text(encoding="utf-8")


def read_query(
    cypher_file: str,
    params: dict | None = None,
    tool_name: str = "raw_read",
) -> list[dict]:
    """
    Execute a READ query from a .cypher file.
    Raises RuntimeError if FalkorDB is unreachable.
    """
    if not is_available():
        raise RuntimeError("FalkorDB is unavailable. Cannot execute query.")

    cypher = _load_cypher(cypher_file)
    params = params or {}

    with audit.timer() as t:
        try:
            result = _get_graph().ro_query(cypher, params)
            col_names = [h[1] if isinstance(h, (list, tuple)) else str(h) for h in result.header]
            rows = [dict(zip(col_names, r)) for r in result.result_set]
            audit.log_entry(
                tool=tool_name,
                cypher=cypher,
                params=params,
                result_rows=len(rows),
                latency_ms=t.elapsed_ms,
                success=True,
            )
            return rows
        except Exception as exc:
            audit.log_entry(
                tool=tool_name,
                cypher=cypher,
                params=params,
                result_rows=None,
                latency_ms=t.elapsed_ms,
                success=False,
                error=str(exc),
            )
            raise


def write_query(
    cypher: str,
    params: dict | None = None,
    tool_name: str = "raw_write",
) -> dict:
    """
    Execute a WRITE query (inline Cypher string — only called by commit_mitigation
    and the simulation engine with fully-constructed, parameterised strings).
    """
    if not is_available():
        raise RuntimeError("FalkorDB is unavailable. Cannot execute write query.")

    params = params or {}

    with audit.timer() as t:
        try:
            result = _get_graph().query(cypher, params)
            stats = {
                "nodes_created": result.nodes_created,
                "relationships_created": result.relationships_created,
                "properties_set": result.properties_set,
                "nodes_deleted": result.nodes_deleted,
            }
            audit.log_entry(
                tool=tool_name,
                cypher=cypher,
                params=params,
                result_rows=None,
                latency_ms=t.elapsed_ms,
                success=True,
                extra={"write_stats": stats},
            )
            return stats
        except Exception as exc:
            audit.log_entry(
                tool=tool_name,
                cypher=cypher,
                params=params,
                result_rows=None,
                latency_ms=t.elapsed_ms,
                success=False,
                error=str(exc),
            )
            raise


def raw_read(cypher: str, params: dict | None = None, tool_name: str = "raw_read") -> list[dict]:
    """Execute a READ query with an inline Cypher string."""
    if not is_available():
        raise RuntimeError("FalkorDB is unavailable.")
    params = params or {}
    with audit.timer() as t:
        try:
            result = _get_graph().ro_query(cypher, params)
            col_names = [h[1] if isinstance(h, (list, tuple)) else str(h) for h in result.header]
            rows = [dict(zip(col_names, r)) for r in result.result_set]
            audit.log_entry(tool=tool_name, cypher=cypher, params=params,
                            result_rows=len(rows), latency_ms=t.elapsed_ms, success=True)
            return rows
        except Exception as exc:
            audit.log_entry(tool=tool_name, cypher=cypher, params=params,
                            result_rows=None, latency_ms=t.elapsed_ms, success=False, error=str(exc))
            raise


def graph_copy(src: str, dst: str):
    """Copy a graph using GRAPH.COPY (for simulation)."""
    if not is_available():
        raise RuntimeError("FalkorDB is unavailable.")
    try:
        _client.connection.execute_command("GRAPH.COPY", src, dst)
    except Exception as exc:
        raise RuntimeError(f"GRAPH.COPY failed: {exc}") from exc


def graph_delete(name: str):
    """Delete a graph (used to clean up simulation copies)."""
    try:
        _client.connection.execute_command("GRAPH.DELETE", name)
    except Exception:
        pass


def select_graph_by_name(name: str) -> falkordb.Graph:
    """Return a Graph object for an arbitrary graph name."""
    _get_graph()
    return _client.select_graph(name)
