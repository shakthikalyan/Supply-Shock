"""
app/tools/analysis.py
Analysis tools – all read-only, each backed by a .cypher file.
"""

from app import graph


def get_blast_radius(node_id: str) -> list[dict]:
    """
    Multi-hop traversal from a disrupted node.
    Returns every downstream node reachable within 6 hops.
    """
    return graph.read_query(
        "get_blast_radius.cypher",
        params={"node_id": node_id},
        tool_name="get_blast_radius",
    )


def find_at_risk_orders(node_id: str) -> list[dict]:
    """
    Returns orders where EVERY supply path is disrupted.
    Only orders with no healthy alternate source are included.
    """
    return graph.read_query(
        "find_at_risk_orders.cypher",
        params={"node_id": node_id},
        tool_name="find_at_risk_orders",
    )


def rank_critical_suppliers() -> list[dict]:
    """PageRank over Supplier nodes to surface systemic importance."""
    return graph.read_query(
        "rank_critical_suppliers.cypher",
        tool_name="rank_critical_suppliers",
    )


def find_choke_points() -> list[dict]:
    """Betweenness centrality to find nodes whose failure cuts the most flows."""
    return graph.read_query(
        "find_choke_points.cypher",
        tool_name="find_choke_points",
    )


def find_dependency_clusters() -> list[dict]:
    """WCC to reveal hidden supplier concentration."""
    return graph.read_query(
        "find_dependency_clusters.cypher",
        tool_name="find_dependency_clusters",
    )


def find_alternate_sources(part_sku: str, avoid_node_id: str) -> list[dict]:
    """
    Weighted shortest-path alternate suppliers for a part,
    excluding the failed node.
    """
    return graph.read_query(
        "find_alternate_sources.cypher",
        params={"part_sku": part_sku, "avoid_node_id": avoid_node_id},
        tool_name="find_alternate_sources",
    )


def check_reroute_capacity(factory_id: str, required_qty: int) -> list[dict]:
    """Max flow check: can alternate suppliers carry the required volume?"""
    return graph.read_query(
        "check_reroute_capacity.cypher",
        params={"factory_id": factory_id, "required_qty": required_qty},
        tool_name="check_reroute_capacity",
    )


def get_graph_snapshot() -> dict:
    """
    Returns a lightweight snapshot of the graph for the UI canvas:
    all nodes and edges with their current status.
    """
    nodes_q = """
    MATCH (n)
    RETURN
      labels(n)[0]  AS label,
      CASE
        WHEN n.id IS NOT NULL THEN n.id
        WHEN n.sku IS NOT NULL THEN n.sku
        ELSE toString(id(n))
      END AS node_id,
      n.name   AS name,
      n.status AS status,
      n.country AS country,
      n.tier   AS tier
    LIMIT 500
    """
    edges_q = """
    MATCH (a)-[r]->(b)
    RETURN
      type(r) AS rel_type,
      CASE WHEN a.id IS NOT NULL THEN a.id WHEN a.sku IS NOT NULL THEN a.sku ELSE toString(id(a)) END AS source,
      CASE WHEN b.id IS NOT NULL THEN b.id WHEN b.sku IS NOT NULL THEN b.sku ELSE toString(id(b)) END AS target,
      r.status AS status
    LIMIT 1000
    """
    nodes = graph.raw_read(nodes_q, tool_name="graph_snapshot_nodes")
    edges = graph.raw_read(edges_q, tool_name="graph_snapshot_edges")
    return {"nodes": nodes, "edges": edges}
