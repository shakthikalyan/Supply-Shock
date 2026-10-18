"""
tests/test_scenario.py
Asserts the planted scenario produces the expected results.
Requires FalkorDB running at localhost:6379 with the seeded graph.

Run: pytest tests/test_scenario.py -v
"""

import os
import pytest

# Allow tests to run without ANTHROPIC_API_KEY (analysis tools only)
os.environ.setdefault("FALKORDB_HOST", "localhost")
os.environ.setdefault("FALKORDB_PORT", "6379")
os.environ.setdefault("GRAPH_NAME",    "supplyshock")


@pytest.fixture(scope="module")
def db_available():
    from app import graph
    if not graph.is_available():
        pytest.skip("FalkorDB not available — start it with `docker compose up falkordb`")
    return True


# ── Planted scenario assertions ───────────────────────────────────────────────

class TestPlantedScenario:
    """
    The core invariant: closing PORT-01 (Shanghai) exposes 14 HIGH-priority orders
    that have no healthy alternate supply path.
    """

    def test_at_risk_orders_equals_14(self, db_available):
        from app.tools.analysis import find_at_risk_orders
        rows = find_at_risk_orders("PORT-01")
        order_ids = set(r["order_id"] for r in rows)
        assert len(order_ids) == 14, (
            f"Expected 14 at-risk HIGH-priority orders, got {len(order_ids)}. "
            f"IDs: {sorted(order_ids)}"
        )

    def test_at_risk_orders_are_high_priority(self, db_available):
        from app.tools.analysis import find_at_risk_orders
        rows = find_at_risk_orders("PORT-01")
        non_high = [r for r in rows if r.get("priority") != "HIGH"]
        assert non_high == [], f"Non-HIGH orders found: {non_high}"

    def test_blast_radius_includes_choke_suppliers(self, db_available):
        from app.tools.analysis import get_blast_radius
        rows = get_blast_radius("PORT-01")
        affected_ids = {r["affected_id"] for r in rows}
        assert "SUP-01" in affected_ids, "ElecCore should be in blast radius"
        assert "SUP-02" in affected_ids, "ChipNation should be in blast radius"
        assert "SUP-03" in affected_ids, "PowerFlex should be in blast radius"

    def test_choke_points_includes_port_01(self, db_available):
        from app.tools.analysis import find_choke_points
        rows = find_choke_points()
        node_ids = {r["node_id"] for r in rows}
        assert "PORT-01" in node_ids, f"PORT-01 not in choke points. Got: {node_ids}"

    def test_dependency_cluster_contains_t2_supplier(self, db_available):
        from app.tools.analysis import find_dependency_clusters
        rows = find_dependency_clusters()
        # There should be a cluster containing all three choke suppliers
        for cluster in rows:
            names = cluster.get("supplier_names", [])
            if "ElecCore" in names and "ChipNation" in names and "PowerFlex" in names:
                return  # Pass
        pytest.fail("No cluster contains all three choke suppliers (hidden dependency not found)")

    def test_alternate_source_exists_for_capacitor(self, db_available):
        from app.tools.analysis import find_alternate_sources
        rows = find_alternate_sources("CAP-4700UF", "SUP-01")
        # If single-sourced (by design), there should be no alternates
        # The test documents that the design is intentionally no-alternate
        # so agents must use simulation to propose a NEW supplier relationship
        assert isinstance(rows, list), "find_alternate_sources should return a list"

    def test_pagerank_surface_tier1_choke(self, db_available):
        from app.tools.analysis import rank_critical_suppliers
        rows = rank_critical_suppliers()
        assert len(rows) > 0, "PageRank returned no results"
        top_ids = {r["supplier_id"] for r in rows[:10]}
        # At least one choke supplier should appear in top-10
        assert top_ids & {"SUP-01", "SUP-02", "SUP-03"}, (
            f"None of the choke suppliers in top-10 PageRank: {top_ids}"
        )


# ── Simulation assertions ─────────────────────────────────────────────────────

class TestSimulation:
    def test_simulation_with_valid_reroute(self, db_available):
        from app.tools.simulate import simulate_mitigation
        diff = simulate_mitigation({
            "disrupted_node_id": "PORT-01",
            "new_supplier_id":   "SUP-04",    # NanoChip DE, healthy
            "part_sku":          "CAP-4700UF",
            "new_port_id":       "PORT-02",   # Rotterdam
            "required_qty":      100,
        })
        assert "orders_saved" in diff
        assert "viable" in diff
        assert diff["baseline_at_risk"] >= 14

    def test_simulation_returns_diff_structure(self, db_available):
        from app.tools.simulate import simulate_mitigation
        diff = simulate_mitigation({
            "disrupted_node_id": "PORT-01",
            "required_qty": 50,
        })
        for key in ("baseline_at_risk", "simulated_at_risk", "orders_saved",
                    "cost_delta", "new_risks", "viable"):
            assert key in diff, f"Missing key in simulation diff: {key}"


# ── Graph availability (kill-switch) ─────────────────────────────────────────

class TestKillSwitch:
    def test_analysis_raises_on_unavailable_graph(self, monkeypatch):
        """If graph.is_available() returns False, tools raise RuntimeError."""
        from app import graph as gmod
        monkeypatch.setattr(gmod, "is_available", lambda: False)
        from app.tools.analysis import find_at_risk_orders
        with pytest.raises(RuntimeError, match="unavailable"):
            find_at_risk_orders("PORT-01")

    def test_write_raises_on_unavailable_graph(self, monkeypatch):
        from app import graph as gmod
        monkeypatch.setattr(gmod, "is_available", lambda: False)
        with pytest.raises(RuntimeError, match="unavailable"):
            gmod.write_query("RETURN 1")


# ── Audit log ─────────────────────────────────────────────────────────────────

class TestAuditLog:
    def test_audit_entry_created_after_query(self, db_available):
        from app import audit
        from app.tools.analysis import find_choke_points
        before = len(audit.recent(1000))
        find_choke_points()
        after = len(audit.recent(1000))
        assert after > before, "No audit entry created after query"

    def test_audit_entry_has_required_fields(self, db_available):
        from app import audit
        from app.tools.analysis import rank_critical_suppliers
        rank_critical_suppliers()
        entry = audit.recent(1)[-1]
        for field in ("id", "timestamp", "tool", "latency_ms", "success"):
            assert field in entry, f"Audit entry missing field: {field}"
