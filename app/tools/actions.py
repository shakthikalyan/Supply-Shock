"""
app/tools/actions.py
Action tools (all gated — nothing executes without human approval).
Drafts go into an in-memory outbox; commit_mitigation writes to the live graph.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from app import audit, graph

# ── In-memory outbox and proposal store ──────────────────────────────────────
_outbox: dict[str, dict] = {}       # action_id → action dict
_proposals: dict[str, dict] = {}    # proposal_id → proposal dict


# ── Draft actions (write nothing to the graph) ────────────────────────────────

def draft_purchase_order(
    supplier_id: str,
    part_sku: str,
    qty: int,
    proposal_id: str,
) -> dict:
    action_id = str(uuid.uuid4())
    action = {
        "action_id": action_id,
        "type": "purchase_order",
        "proposal_id": proposal_id,
        "supplier_id": supplier_id,
        "part_sku": part_sku,
        "qty": qty,
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _outbox[action_id] = action
    audit.log_entry(
        tool="draft_purchase_order",
        cypher=None,
        params={"supplier_id": supplier_id, "part_sku": part_sku, "qty": qty},
        result_rows=None,
        latency_ms=0.0,
        success=True,
        extra={"action_id": action_id, "status": "draft"},
    )
    return action


def notify_owner(
    owner: str,
    message: str,
    evidence_path: list[str],
    proposal_id: str,
) -> dict:
    action_id = str(uuid.uuid4())
    action = {
        "action_id": action_id,
        "type": "notification",
        "proposal_id": proposal_id,
        "owner": owner,
        "message": message,
        "evidence_path": evidence_path,
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _outbox[action_id] = action
    audit.log_entry(
        tool="notify_owner",
        cypher=None,
        params={"owner": owner},
        result_rows=None,
        latency_ms=0.0,
        success=True,
        extra={"action_id": action_id},
    )
    return action


# ── Proposal registry ─────────────────────────────────────────────────────────

def register_proposal(proposal: dict) -> str:
    proposal_id = str(uuid.uuid4())
    proposal["proposal_id"] = proposal_id
    proposal["status"] = "pending"
    proposal["created_at"] = datetime.now(timezone.utc).isoformat()
    _proposals[proposal_id] = proposal
    return proposal_id


def get_proposal(proposal_id: str) -> dict | None:
    return _proposals.get(proposal_id)


def list_proposals() -> list[dict]:
    return list(_proposals.values())


# ── Commit (requires human approval from the API layer) ──────────────────────

def commit_mitigation(proposal_id: str) -> dict:
    """
    Called only after human approval.
    1. Mutates the live graph: sets disrupted node status to 'mitigated',
       adds new SUPPLIES edge if the proposal includes a reroute.
    2. Releases all draft outbox items for the proposal.
    3. Returns a commit receipt.
    """
    proposal = _proposals.get(proposal_id)
    if not proposal:
        raise ValueError(f"Unknown proposal_id: {proposal_id}")
    if proposal.get("status") == "committed":
        return {"already_committed": True, "proposal_id": proposal_id}

    if not graph.is_available():
        raise RuntimeError("FalkorDB unavailable. Cannot commit mitigation.")

    writes = []

    # Mark the disrupted event node as mitigated
    disrupted_id = proposal.get("disrupted_node_id")
    if disrupted_id:
        graph.write_query(
            "MATCH (n {id: $nid}) SET n.status = 'mitigated'",
            {"nid": disrupted_id},
            tool_name="commit_mitigation:set_mitigated",
        )
        writes.append(f"set {disrupted_id} status=mitigated")

    # Add new SUPPLIES edge from alternate supplier
    for action in proposal.get("actions", []):
        if action.get("type") == "purchase_order":
            sup_id   = action.get("supplier_id")
            part_sku = action.get("part_sku")
            qty      = action.get("qty", 0)
            if sup_id and part_sku:
                graph.write_query(
                    "MATCH (s:Supplier {id:$sid}), (p:Part {sku:$sku}) "
                    "MERGE (s)-[r:SUPPLIES]->(p) "
                    "ON CREATE SET r.cost=0, r.lead_time_days=14, r.share=1.0, "
                    "              r.capacity=$qty, r.status='mitigated' "
                    "ON MATCH  SET r.status='mitigated', r.capacity=$qty",
                    {"sid": sup_id, "sku": part_sku, "qty": qty},
                    tool_name="commit_mitigation:add_supplies",
                )
                writes.append(f"added SUPPLIES {sup_id}→{part_sku}")

    # Release outbox items
    released = []
    for action_id, action in _outbox.items():
        if action.get("proposal_id") == proposal_id:
            action["status"] = "released"
            released.append(action_id)

    proposal["status"] = "committed"
    proposal["committed_at"] = datetime.now(timezone.utc).isoformat()

    receipt = {
        "proposal_id": proposal_id,
        "committed": True,
        "writes": writes,
        "released_actions": released,
        "committed_at": proposal["committed_at"],
    }
    audit.log_entry(
        tool="commit_mitigation",
        cypher=None,
        params={"proposal_id": proposal_id},
        result_rows=None,
        latency_ms=0.0,
        success=True,
        extra={"receipt": receipt},
    )
    return receipt


def reject_proposal(proposal_id: str) -> dict:
    proposal = _proposals.get(proposal_id)
    if not proposal:
        raise ValueError(f"Unknown proposal_id: {proposal_id}")
    proposal["status"] = "rejected"
    # Clean up outbox
    for action in _outbox.values():
        if action.get("proposal_id") == proposal_id:
            action["status"] = "cancelled"
    return {"proposal_id": proposal_id, "status": "rejected"}


def get_outbox(proposal_id: str | None = None) -> list[dict]:
    if proposal_id:
        return [a for a in _outbox.values() if a.get("proposal_id") == proposal_id]
    return list(_outbox.values())
