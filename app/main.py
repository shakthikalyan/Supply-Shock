"""
app/main.py
FastAPI application: REST endpoints + SSE stream.
"""

import asyncio
import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app import audit, graph
from app.agent import run_agent
from app.tools import actions, analysis

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SupplyShock API",
    description="Supply-chain disruption mitigation agent powered by FalkorDB",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static web files
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


# ── Request / Response models ─────────────────────────────────────────────────

class EventRequest(BaseModel):
    type: str = "port_closure"
    node_id: str = "PORT-01"
    description: str = "Port of Shanghai closed due to extreme weather event."


class ApprovalRequest(BaseModel):
    proposal_id: str


# ── Active agent runs (for SSE streaming) ─────────────────────────────────────
_active_runs: dict[str, list[dict]] = {}   # run_id → event queue


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/health")
async def health():
    db_ok = graph.is_available()
    return {
        "status": "ok" if db_ok else "degraded",
        "falkordb": db_ok,
        "graph": graph.GRAPH_NAME,
    }


# ── Graph snapshot for the UI canvas ─────────────────────────────────────────

@app.get("/api/graph")
async def get_graph():
    if not graph.is_available():
        raise HTTPException(503, "FalkorDB unavailable")
    return analysis.get_graph_snapshot()


# ── Trigger disruption event ──────────────────────────────────────────────────

@app.post("/api/event")
async def trigger_event(req: EventRequest, background_tasks: BackgroundTasks):
    import uuid
    run_id = str(uuid.uuid4())
    queue: list[dict] = []
    _active_runs[run_id] = queue

    def _stream_cb(step: dict):
        queue.append(step)

    def _run():
        try:
            # Mark the disrupted node in the graph
            if graph.is_available():
                try:
                    graph.write_query(
                        "MATCH (n {id: $nid}) SET n.status = 'disrupted'",
                        {"nid": req.node_id},
                        tool_name="event_ingestor:mark_disrupted",
                    )
                except Exception:
                    pass

            proposal = run_agent(req.model_dump(), stream_callback=_stream_cb)
            queue.append({"type": "done", "proposal": proposal})
        except Exception as exc:
            queue.append({"type": "error", "error": str(exc)})

    background_tasks.add_task(_run)
    return {"run_id": run_id}


# ── SSE stream for a run ──────────────────────────────────────────────────────

@app.get("/api/stream/{run_id}")
async def stream_run(run_id: str):
    if run_id not in _active_runs:
        raise HTTPException(404, "Run not found")

    async def generator():
        queue = _active_runs[run_id]
        sent = 0
        while True:
            while sent < len(queue):
                yield {"data": json.dumps(queue[sent], default=str)}
                sent += 1
                if queue[sent - 1].get("type") in ("done", "error"):
                    _active_runs.pop(run_id, None)
                    return
            await asyncio.sleep(0.1)

    return EventSourceResponse(generator())


# ── Audit log stream (live) ───────────────────────────────────────────────────

@app.get("/api/audit/stream")
async def audit_stream():
    async def generator():
        q = audit.subscribe()
        # Send buffered history first
        for entry in audit.recent(50):
            yield {"data": json.dumps(entry, default=str)}
        try:
            while True:
                while q:
                    yield {"data": json.dumps(q.pop(0), default=str)}
                await asyncio.sleep(0.05)
        finally:
            audit.unsubscribe(q)

    return EventSourceResponse(generator())


@app.get("/api/audit")
async def get_audit(n: int = 100):
    return audit.recent(n)


# ── Proposals ─────────────────────────────────────────────────────────────────

@app.get("/api/proposals")
async def list_proposals():
    return actions.list_proposals()


@app.get("/api/proposals/{proposal_id}")
async def get_proposal(proposal_id: str):
    p = actions.get_proposal(proposal_id)
    if not p:
        raise HTTPException(404, "Proposal not found")
    return p


@app.post("/api/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str):
    if not graph.is_available():
        raise HTTPException(503, "FalkorDB unavailable — cannot commit without the graph")
    try:
        receipt = actions.commit_mitigation(proposal_id)
        return receipt
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    try:
        return actions.reject_proposal(proposal_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


# ── Outbox ────────────────────────────────────────────────────────────────────

@app.get("/api/outbox")
async def get_outbox(proposal_id: str | None = None):
    return actions.get_outbox(proposal_id)


# ── Seed / reset (dev helper) ─────────────────────────────────────────────────

@app.post("/api/seed")
async def seed_graph(background_tasks: BackgroundTasks, wipe: bool = True):
    """Re-seed the graph (for demo resets)."""
    def _seed():
        cmd = [
            sys.executable, "seed/generate.py",
            "--host", os.getenv("FALKORDB_HOST", "localhost"),
            "--port", os.getenv("FALKORDB_PORT", "6379"),
            "--graph", graph.GRAPH_NAME,
        ]
        if os.getenv("FALKORDB_PASSWORD"):
            cmd.extend(["--password", os.getenv("FALKORDB_PASSWORD")])
        if wipe:
            cmd.append("--wipe")
        subprocess.run(cmd, check=True)
    background_tasks.add_task(_seed)
    return {"status": "seeding started"}


# ── Analysis endpoints (direct, for testing) ──────────────────────────────────

@app.get("/api/analysis/blast-radius/{node_id}")
async def blast_radius(node_id: str):
    if not graph.is_available():
        raise HTTPException(503, "FalkorDB unavailable")
    return analysis.get_blast_radius(node_id)


@app.get("/api/analysis/at-risk/{node_id}")
async def at_risk(node_id: str):
    if not graph.is_available():
        raise HTTPException(503, "FalkorDB unavailable")
    return analysis.find_at_risk_orders(node_id)


@app.get("/api/analysis/choke-points")
async def choke_points():
    if not graph.is_available():
        raise HTTPException(503, "FalkorDB unavailable")
    return analysis.find_choke_points()


@app.get("/api/analysis/pagerank")
async def pagerank():
    if not graph.is_available():
        raise HTTPException(503, "FalkorDB unavailable")
    return analysis.rank_critical_suppliers()


@app.get("/api/analysis/clusters")
async def clusters():
    if not graph.is_available():
        raise HTTPException(503, "FalkorDB unavailable")
    return analysis.find_dependency_clusters()
