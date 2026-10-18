from app.tools.simulate import simulate_mitigation
diff = simulate_mitigation({
    "disrupted_node_id": "PORT-01",
    "new_supplier_id":   "SUP-04",    # NanoChip DE, healthy
    "part_sku":          "CAP-4700UF",
    "new_port_id":       "PORT-02",   # Rotterdam
    "required_qty":      100,
})
print("Simulation diff:", diff)
