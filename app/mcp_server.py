"""
app/mcp_server.py
MCP tool registry.  Each tool is a named, typed callable with a JSON schema.
The agent calls these by name; the registry dispatches to the underlying Python functions.
"""

from typing import Any

from app.tools import analysis, simulate as sim_tools, actions

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    # ── Analysis ─────────────────────────────────────────────────────────────
    {
        "name": "get_blast_radius",
        "description": (
            "Multi-hop traversal from a disrupted Port, Supplier, or Part. "
            "Returns every downstream node reachable within 6 hops."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "ID of the disrupted node (e.g. PORT-01)"}
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "find_at_risk_orders",
        "description": (
            "Returns orders where EVERY supply path is disrupted. "
            "Orders with a healthy alternate source are excluded — this is the real insight."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "ID of the disrupted node"}
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "rank_critical_suppliers",
        "description": "PageRank over Supplier nodes to surface systemic importance.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_choke_points",
        "description": "Betweenness centrality — nodes whose failure cuts the most supply flows.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_dependency_clusters",
        "description": "WCC community detection — reveals hidden supplier concentration.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_alternate_sources",
        "description": (
            "Weighted shortest-path alternate suppliers for a part, "
            "excluding the failed node and disrupted ports."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "part_sku":       {"type": "string"},
                "avoid_node_id":  {"type": "string"},
            },
            "required": ["part_sku", "avoid_node_id"],
        },
    },
    {
        "name": "check_reroute_capacity",
        "description": (
            "Max Flow from alternate suppliers to the target factory. "
            "Rejects reroutes that exist on the map but can't carry the required volume."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "factory_id":   {"type": "string"},
                "required_qty": {"type": "integer"},
            },
            "required": ["factory_id", "required_qty"],
        },
    },
    # ── Simulation ────────────────────────────────────────────────────────────
    {
        "name": "simulate_mitigation",
        "description": (
            "Copies the live graph, applies the proposed change set, re-runs "
            "find_at_risk_orders, and returns a diff: orders_saved, cost_delta, new_risks. "
            "MUST be called before drafting any action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "disrupted_node_id": {"type": "string"},
                "new_supplier_id":   {"type": "string"},
                "part_sku":          {"type": "string"},
                "new_port_id":       {"type": "string"},
                "required_qty":      {"type": "integer"},
            },
            "required": ["disrupted_node_id"],
        },
    },
    # ── Actions (gated) ───────────────────────────────────────────────────────
    {
        "name": "draft_purchase_order",
        "description": "Write a draft PO to the outbox. Does NOT execute until approved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "supplier_id": {"type": "string"},
                "part_sku":    {"type": "string"},
                "qty":         {"type": "integer"},
                "proposal_id": {"type": "string"},
            },
            "required": ["supplier_id", "part_sku", "qty", "proposal_id"],
        },
    },
    {
        "name": "notify_owner",
        "description": "Draft a notification that includes the traversal evidence path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "owner":         {"type": "string"},
                "message":       {"type": "string"},
                "evidence_path": {"type": "array", "items": {"type": "string"}},
                "proposal_id":   {"type": "string"},
            },
            "required": ["owner", "message", "evidence_path", "proposal_id"],
        },
    },
]

# ── Dispatcher ────────────────────────────────────────────────────────────────

def dispatch(tool_name: str, tool_input: dict) -> Any:
    """
    Dispatch a tool call by name.
    Returns the tool result or raises RuntimeError if the graph is unavailable.
    """
    match tool_name:
        case "get_blast_radius":
            return analysis.get_blast_radius(**tool_input)
        case "find_at_risk_orders":
            return analysis.find_at_risk_orders(**tool_input)
        case "rank_critical_suppliers":
            return analysis.rank_critical_suppliers()
        case "find_choke_points":
            return analysis.find_choke_points()
        case "find_dependency_clusters":
            return analysis.find_dependency_clusters()
        case "find_alternate_sources":
            return analysis.find_alternate_sources(**tool_input)
        case "check_reroute_capacity":
            return analysis.check_reroute_capacity(**tool_input)
        case "simulate_mitigation":
            return sim_tools.simulate_mitigation(tool_input)
        case "draft_purchase_order":
            return actions.draft_purchase_order(**tool_input)
        case "notify_owner":
            return actions.notify_owner(**tool_input)
        case _:
            raise ValueError(f"Unknown tool: {tool_name}")
