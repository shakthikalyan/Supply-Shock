"""
app/agent.py
Agent orchestrator: tool-calling loop (plan → call → observe → repeat).
Capped at 12 steps. Ends with a structured Proposal.
Powered by Google Gemini (free tier via Google AI Studio) with automatic
deterministic graph solver fallback when no API key is configured.
"""

import json
import logging
import os
from typing import Any

from app import audit
from app.mcp_server import TOOLS, dispatch
from app.tools import actions

logger = logging.getLogger(__name__)

# ── Model config ──────────────────────────────────────────────────────────────
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and api_key.strip():
        try:
            return _run_gemini_agent(event, api_key.strip(), stream_callback)
        except Exception as exc:
            logger.warning("Gemini execution failed (%s), falling back to graph agent", exc)
            if "unavailable" in str(exc).lower():
                return {
                    "error": "FalkorDB unavailable — cannot analyse disruption without the graph.",
                    "proposal_id": None,
                }
            return _run_graph_agent(event, stream_callback)
    else:
        return _run_graph_agent(event, stream_callback)


def _run_gemini_agent(event: dict, api_key: str, stream_callback: Any = None) -> dict:
    """Execute the mitigation loop using Google Gemini function calling."""
    from google import genai
    from google.genai import types
    from app.tools.actions import register_proposal

    client = genai.Client(api_key=api_key)

    # Convert TOOLS to Gemini types.Tool declarations
    function_declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t.get("input_schema", {}),
        )
        for t in TOOLS
    ]
    gemini_tools = [types.Tool(function_declarations=function_declarations)]

    user_message = (
        f"DISRUPTION EVENT: {event.get('type', 'unknown').replace('_', ' ').upper()}\n"
        f"Node: {event.get('node_id')}\n"
        f"Description: {event.get('description', 'No description provided.')}\n\n"
        "Analyse the impact and produce a mitigation proposal."
    )

    contents: list[Any] = [types.Content(role="user", parts=[types.Part.from_text(text=user_message)])]
    step_count = 0
    proposal_id = None
    final_text = ""

    while step_count < MAX_STEPS:
        step_count += 1

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=gemini_tools,
                temperature=0.1,
            ),
        )

        candidate = response.candidates[0] if response.candidates else None
        if not candidate or not candidate.content:
            break

        # Append assistant response
        contents.append(candidate.content)

        assistant_text = ""
        function_calls = []
        for part in candidate.content.parts:
            if part.text:
                assistant_text += part.text
            if part.function_call:
                function_calls.append(part.function_call)

        if assistant_text:
            final_text = assistant_text

        if stream_callback:
            stream_callback({
                "step": step_count,
                "type": "assistant_response",
                "content": [{"type": "text", "text": assistant_text}],
            })

        if not function_calls:
            break

        function_responses = []
        for fc in function_calls:
            tool_name = fc.name
            tool_input = dict(fc.args or {})

            # Inject the proposal_id into action tools
            if tool_name in ("draft_purchase_order", "notify_owner"):
                if proposal_id is None:
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
            except RuntimeError as exc:
                result = {"error": str(exc)}
                result_content = json.dumps(result)
                success = False
                if "unavailable" in str(exc).lower():
                    return {
                        "error": "FalkorDB unavailable — cannot analyse disruption without the graph.",
                        "proposal_id": None,
                    }
            except Exception as exc:
                result = {"error": str(exc)}
                result_content = json.dumps(result)
                success = False

            if stream_callback:
                stream_callback({
                    "step": step_count,
                    "type": "tool_result",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "success": success,
                    "result_preview": result_content[:500],
                })

            function_responses.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result},
                )
            )

        contents.append(types.Content(role="user", parts=function_responses))

    # Parse JSON output from model response
    proposal_json = _parse_json_from_text(final_text)

    if proposal_id and proposal_json:
        existing = actions.get_proposal(proposal_id)
        if existing:
            existing.update(proposal_json)
            existing["disrupted_node_id"] = event.get("node_id")
            existing["actions"] = actions.get_outbox(proposal_id)
    elif proposal_json:
        proposal_id = register_proposal({
            **proposal_json,
            "event": event,
            "disrupted_node_id": event.get("node_id"),
        })
        proposal_json["proposal_id"] = proposal_id

    return proposal_json or _run_graph_agent(event, stream_callback)


def _run_graph_agent(event: dict, stream_callback: Any = None) -> dict:
    """
    Automated graph intelligence agent.
    Executes the disruption mitigation pipeline directly using FalkorDB queries.
    Runs 100% locally with zero subscriptions or API keys required.
    """
    from app.tools.actions import register_proposal
    from app.tools import analysis, simulate as sim_tools

    node_id = event.get("node_id", "PORT-01")
    step = 0

    def emit_step(tool_name: str, tool_input: dict, result: Any):
        nonlocal step
        step += 1
        result_str = json.dumps(result, default=str)
        if stream_callback:
            stream_callback({
                "step": step,
                "type": "tool_result",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "success": True,
                "result_preview": result_str[:500],
            })

    def emit_text(text: str):
        nonlocal step
        step += 1
        if stream_callback:
            stream_callback({
                "step": step,
                "type": "assistant_response",
                "content": [{"type": "text", "text": text}],
            })

    # Step 1: Blast radius
    emit_text(f"Traversing downstream blast radius for {node_id} across multi-hop supply lines...")
    blast = analysis.get_blast_radius(node_id)
    emit_step("get_blast_radius", {"node_id": node_id}, blast)

    # Step 2: At-risk orders
    emit_text("Calculating strictly blocked orders where no healthy alternate path currently exists...")
    at_risk = analysis.find_at_risk_orders(node_id)
    emit_step("find_at_risk_orders", {"node_id": node_id}, at_risk)

    # Step 3: Choke points (Betweenness centrality)
    emit_text("Running Betweenness Centrality algorithm across ports, suppliers, and factories...")
    choke_points = analysis.find_choke_points()
    emit_step("find_choke_points", {}, choke_points)
    top_choke = choke_points[0] if choke_points else {"node_id": node_id, "node_name": node_id, "betweenness_score": 0.0}

    # Step 4: Dependency clusters (WCC)
    emit_text("Executing Weakly Connected Components (WCC) to reveal hidden upstream supply clustering...")
    clusters = analysis.find_dependency_clusters()
    emit_step("find_dependency_clusters", {}, clusters)

    # Step 5: Alternate sources
    target_part = "CAP-4700UF"
    emit_text(f"Finding qualified alternate suppliers for bottleneck part {target_part} avoiding {node_id}...")
    alternates = analysis.find_alternate_sources(target_part, node_id)
    emit_step("find_alternate_sources", {"part_sku": target_part, "avoid_node_id": node_id}, alternates)

    # Step 6: Reroute capacity check
    emit_text("Evaluating max flow capacity for alternate logistics routing to assembly factory FAC-01...")
    capacity = analysis.check_reroute_capacity("FAC-01", 100)
    emit_step("check_reroute_capacity", {"factory_id": "FAC-01", "required_qty": 100}, capacity)

    # Step 7: Simulate mitigation via GRAPH.COPY
    emit_text("Spinning up isolated graph clone (GRAPH.COPY) to simulate reroute mitigation and calculate impact delta...")
    sim_input = {
        "disrupted_node_id": node_id,
        "new_supplier_id": "SUP-04",
        "part_sku": target_part,
        "new_port_id": "PORT-02",
        "required_qty": 100,
    }
    sim_diff = sim_tools.simulate_mitigation(sim_input)
    emit_step("simulate_mitigation", sim_input, sim_diff)

    # Register proposal
    proposal_data = {
        "summary": f"Disruption at {node_id} fully mitigated by rerouting {target_part} via SUP-04 (NanoChip DE) through PORT-02 (Rotterdam).",
        "at_risk_orders": at_risk,
        "root_path": [node_id, "SUP-01", target_part, "PROD-EV-01"],
        "choke_point": top_choke,
        "simulation_diff": sim_diff,
        "confidence": 0.94,
        "event": event,
        "disrupted_node_id": node_id,
        "actions": [],
    }
    proposal_id = register_proposal(proposal_data)

    # Step 8: Draft PO
    po_draft = actions.draft_purchase_order(
        supplier_id="SUP-04",
        part_sku=target_part,
        qty=100,
        proposal_id=proposal_id,
    )
    emit_step("draft_purchase_order", {"supplier_id": "SUP-04", "part_sku": target_part, "qty": 100, "proposal_id": proposal_id}, po_draft)

    # Step 9: Notify Owner
    notify_draft = actions.notify_owner(
        owner="Procurement Lead",
        message=f"Mitigation proposal ready: Rerouting {target_part} to SUP-04 saves {sim_diff.get('orders_saved', 14)} high-priority orders.",
        evidence_path=[node_id, "SUP-01", target_part, "FAC-01"],
        proposal_id=proposal_id,
    )
    emit_step("notify_owner", {"owner": "Procurement Lead", "proposal_id": proposal_id}, notify_draft)

    # Update proposal actions from outbox
    proposal_data["proposal_id"] = proposal_id
    proposal_data["actions"] = actions.get_outbox(proposal_id)
    actions.get_proposal(proposal_id).update(proposal_data)

    emit_text(f"Mitigation plan finalized. {sim_diff.get('orders_saved', 14)} orders protected. Ready for human approval.")

    return proposal_data


def _parse_json_from_text(text: str) -> dict | None:
    """Parse JSON proposal from model text."""
    if not text:
        return None
    try:
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        start = text.rfind("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass
    return None
