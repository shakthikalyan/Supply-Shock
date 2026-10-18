"""
app/tools/simulate.py
Simulation engine:
  1. Copy the live graph with GRAPH.COPY.
  2. Apply the proposed change set.
  3. Re-run find_at_risk_orders on the copy.
  4. Diff against the baseline.
  5. Delete the copy.
  6. Return a SimulationDiff.
"""

import time
import uuid
from typing import Any

from app import audit, graph


def simulate_mitigation(change_set: dict) -> dict:
    """
    change_set schema:
    {
      "disrupted_node_id": str,          # the event node (Port or Supplier)
      "new_supplier_id": str,            # alternate supplier to activate
      "part_sku": str,                   # part being rerouted
      "new_port_id": str | None,         # alternate port (optional)
      "required_qty": int,               # volume needed
    }

    Returns SimulationDiff:
    {
      "sim_graph": str,                  # ephemeral graph name
      "baseline_at_risk": int,
      "simulated_at_risk": int,
      "orders_saved": int,
      "cost_delta": float,
      "new_risks": list[str],            # any new choke points created
      "viable": bool,
    }
    """
    if not graph.is_available():
        raise RuntimeError("FalkorDB is unavailable. Cannot run simulation.")

    disrupted_node_id = change_set.get("disrupted_node_id")
    new_supplier_id   = change_set.get("new_supplier_id")
    part_sku          = change_set.get("part_sku")
    new_port_id       = change_set.get("new_port_id")
    required_qty      = change_set.get("required_qty", 0)

    # Baseline: at-risk orders before the fix
    from app.tools.analysis import find_at_risk_orders
    baseline_rows = find_at_risk_orders(disrupted_node_id)
    baseline_at_risk = len(set(r["order_id"] for r in baseline_rows))

    # Create ephemeral simulation graph
    sim_name = f"sim_{uuid.uuid4().hex[:8]}"
    t0 = time.perf_counter()

    try:
        graph.graph_copy(graph.GRAPH_NAME, sim_name)
        sim_graph = graph.select_graph_by_name(sim_name)

        # 1. Mark disrupted node as mitigated in the copy
        sim_graph.query(
            "MATCH (n {id: $nid}) SET n.status = 'mitigated'",
            {"nid": disrupted_node_id},
        )

        # 2. Add a SUPPLIES edge from the new supplier to the part (if not exists)
        if new_supplier_id and part_sku:
            sim_graph.query(
                "MATCH (s:Supplier {id: $sid}), (p:Part {sku: $sku}) "
                "MERGE (s)-[:SUPPLIES {cost: 0, lead_time_days: 0, share: 1.0, capacity: 9999, status: 'simulated'}]->(p)",
                {"sid": new_supplier_id, "sku": part_sku},
            )

        # 3. If alternate port, add SHIPS_VIA + mark old port as disrupted in copy
        if new_port_id and new_supplier_id:
            sim_graph.query(
                "MATCH (s:Supplier {id: $sid}), (p:Port {id: $pid}) "
                "MERGE (s)-[:SHIPS_VIA {transit_days: 5, status: 'simulated'}]->(p)",
                {"sid": new_supplier_id, "pid": new_port_id},
            )

        # 4. Re-run at-risk query on the simulation graph
        sim_result = sim_graph.ro_query(
            _load_at_risk_cypher(),
            {"node_id": disrupted_node_id},
        )
        sim_cols = [h[1] if isinstance(h, (list, tuple)) else str(h) for h in sim_result.header]
        sim_rows = [dict(zip(sim_cols, r)) for r in sim_result.result_set]
        simulated_at_risk = len(set(r["order_id"] for r in sim_rows))

        # 5. Estimate cost delta (new supplier cost vs. original)
        cost_delta = _estimate_cost_delta(sim_graph, new_supplier_id, part_sku)

        # 6. Detect new single-source risk created by the reroute
        new_risks = _detect_new_risks(sim_graph, new_supplier_id)

    finally:
        graph.graph_delete(sim_name)

    latency_ms = (time.perf_counter() - t0) * 1000

    result = {
        "sim_graph": sim_name,
        "baseline_at_risk": baseline_at_risk,
        "simulated_at_risk": simulated_at_risk,
        "orders_saved": max(0, baseline_at_risk - simulated_at_risk),
        "cost_delta": cost_delta,
        "new_risks": new_risks,
        "viable": simulated_at_risk < baseline_at_risk,
    }

    audit.log_entry(
        tool="simulate_mitigation",
        cypher=None,
        params=change_set,
        result_rows=None,
        latency_ms=latency_ms,
        success=True,
        extra={"simulation_diff": result},
    )

    return result


def _load_at_risk_cypher() -> str:
    from pathlib import Path
    p = Path(__file__).parent.parent.parent / "queries" / "find_at_risk_orders.cypher"
    return p.read_text(encoding="utf-8")


def _estimate_cost_delta(sim_graph, new_supplier_id: str | None, part_sku: str | None) -> float:
    if not new_supplier_id or not part_sku:
        return 0.0
    try:
        result = sim_graph.ro_query(
            "MATCH (s:Supplier {id:$sid})-[r:SUPPLIES]->(p:Part {sku:$sku}) "
            "RETURN r.cost AS cost LIMIT 1",
            {"sid": new_supplier_id, "sku": part_sku},
        )
        rows = result.result_set
        if rows:
            new_cost = rows[0][0] or 0
            return round(float(new_cost) * 1.15, 2)  # 15% premium for urgency
    except Exception:
        pass
    return 0.0


def _detect_new_risks(sim_graph, new_supplier_id: str | None) -> list[str]:
    """Check if rerouting creates a new single point of failure."""
    if not new_supplier_id:
        return []
    try:
        result = sim_graph.ro_query(
            "MATCH (s:Supplier {id:$sid})-[:SUPPLIES]->(p:Part) "
            "WITH p, count(*) AS supplier_count "
            "WHERE supplier_count = 1 "
            "RETURN p.sku AS sku, p.name AS name",
            {"sid": new_supplier_id},
        )
        return [f"{r[1]} ({r[0]}) now single-sourced" for r in result.result_set]
    except Exception:
        return []
