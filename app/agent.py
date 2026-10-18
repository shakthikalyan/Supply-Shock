"""
app/agent.py
Agent orchestrator: tool-calling loop (plan → call → observe → repeat).
Capped at 12 steps. Ends with a structured Proposal.
Uses Anthropic Claude with the MCP tool catalogue.
"""

import json
import os
from typing import Any, Generator

import anthropic

from app import audit
from app.mcp_server import TOOLS, dispatch
from app.tools import actions

# ── Model config ──────────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-5"
MAX_STEPS = 12

SYSTEM_PROMPT = """You are SupplyShock, a supply-chain disruption analyst powered by FalkorDB graph intelligence.

## Rules you MUST follow — no exceptions:
1. Never state a number that didn't come from a tool result.
2. Always call simulate_mitigation before drafting any action.
3. Cite the traversal path (list of node IDs) for every claim you make.
4. Prefer fixes that reduce risk without creating new single points of failure.
5. If find_at_risk_orders returns 0 rows, state that no orders are at risk and stop.
6. If any tool raises a RuntimeError containing "unavailable", stop immediately and return:
   {"error": "FalkorDB unavailable — cannot analyse disruption without the graph."}

## Workflow for a port/supplier closure event:
1. get_blast_radius — understand full downstream impact
2. find_at_risk_orders — identify truly blocked orders (no healthy alternate)
3. find_choke_points — confirm the structural bottleneck
4. find_dependency_clusters — reveal any hidden concentration
5. find_alternate_sources — for each blocked part, find the best reroute
6. check_reroute_capacity — confirm the alternate can carry the volume
7. simulate_mitigation — prove the fix works before proposing
8. draft_purchase_order + notify_owner — prepare the actions

## Output format (final message must be valid JSON):
{
  "summary": "one-sentence narrative",
  "at_risk_orders": [{"order_id": ..., "customer": ..., "value": ..., "priority": ...}],
  "root_path": ["NODE-A", "NODE-B", ...],
  "choke_point": {"node_id": ..., "node_name": ..., "betweenness_score": ...},
  "actions": [{"type": "purchase_order"|"notification", ...}],
  "simulation_diff": {"baseline_at_risk": ..., "simulated_at_risk": ..., "orders_saved": ..., "cost_delta": ..., "viable": ...},
  "confidence": 0.0-1.0
}
"""


def run_agent(
    event: dict,
    stream_callback: Any = None,
) -> dict:
    """
    Run the agent loop for a supply-chain disruption event.

    event = {
        "type": "port_closure" | "supplier_failure",
        "node_id": str,          # e.g. "PORT-01"
        "description": str,
    }

    stream_callback(step_dict) is called after each tool use.
    Returns the final Proposal dict.
    """
    from app.tools.actions import register_proposal

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    user_message = (
        f"DISRUPTION EVENT: {event.get('type', 'unknown').replace('_', ' ').upper()}\n"
        f"Node: {event.get('node_id')}\n"
        f"Description: {event.get('description', 'No description provided.')}\n\n"
        "Analyse the impact and produce a mitigation proposal."
    )

    messages = [{"role": "user", "content": user_message}]
    step_count = 0
    proposal_id = None

    while step_count < MAX_STEPS:
        step_count += 1

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Append assistant response
        messages.append({"role": "assistant", "content": response.content})

        if stream_callback:
            stream_callback({
                "step": step_count,
                "type": "assistant_response",
                "stop_reason": response.stop_reason,
                "content": [
                    {"type": b.type, "text": getattr(b, "text", None),
                     "name": getattr(b, "name", None)}
                    for b in response.content
                ],
            })

        # Stop if no tool calls
        if response.stop_reason == "end_turn":
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input

            # Inject the proposal_id into action tools
            if tool_name in ("draft_purchase_order", "notify_owner"):
                if proposal_id is None:
                    # Register a placeholder proposal
                    proposal_id = register_proposal({
                        "event": event,
                        "disrupted_node_id": event.get("node_id"),
                        "actions": [],
                    })
                tool_input = {**tool_input, "proposal_id": proposal_id}

            try:
                result = dispatch(tool_name, tool_input)
                result_content = json.dumps(result, default=str)
                success = True
                error_str = None
            except RuntimeError as exc:
                result_content = json.dumps({"error": str(exc)})
                success = False
                error_str = str(exc)
                # Kill-switch: graph unavailable
                if "unavailable" in str(exc).lower():
                    return {
                        "error": "FalkorDB unavailable — cannot analyse disruption without the graph.",
                        "proposal_id": None,
                    }
            except Exception as exc:
                result_content = json.dumps({"error": str(exc)})
                success = False
                error_str = str(exc)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_content,
            })

            if stream_callback:
                stream_callback({
                    "step": step_count,
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "success": success,
                    "result_preview": result_content[:500],
                })

        messages.append({"role": "user", "content": tool_results})

    # ── Extract final proposal JSON ───────────────────────────────────────────
    proposal_json = _extract_final_json(messages)

    if proposal_id and proposal_json:
        # Update the registered proposal with the full details
        existing = actions.get_proposal(proposal_id)
        if existing:
            existing.update(proposal_json)
            existing["disrupted_node_id"] = event.get("node_id")
            # Attach any drafted actions
            existing["actions"] = actions.get_outbox(proposal_id)
    elif proposal_json:
        proposal_id = register_proposal({
            **proposal_json,
            "event": event,
            "disrupted_node_id": event.get("node_id"),
        })
        proposal_json["proposal_id"] = proposal_id

    return proposal_json or {"error": "Agent did not produce a valid proposal.", "proposal_id": None}


def _extract_final_json(messages: list) -> dict | None:
    """Find the last assistant message and parse the JSON block from it."""
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        for block in (msg.get("content") or []):
            if isinstance(block, dict):
                text = block.get("text", "")
            else:
                text = getattr(block, "text", "")
            if not text:
                continue
            # Try to extract a JSON block
            try:
                # Look for a ```json block or bare JSON object
                if "```json" in text:
                    start = text.index("```json") + 7
                    end = text.index("```", start)
                    return json.loads(text[start:end].strip())
                # Bare JSON object
                start = text.rfind("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    return json.loads(text[start:end])
            except (ValueError, json.JSONDecodeError):
                continue
    return None
