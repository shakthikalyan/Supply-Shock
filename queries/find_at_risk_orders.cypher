// find_at_risk_orders.cypher
// Returns orders where EVERY supply path for at least one required part is disrupted.
// Handles both Port closures and Supplier failures.
// Parameters: $node_id (string) – the disrupted Port or Supplier

MATCH (s:Supplier)
OPTIONAL MATCH (s)-[:SHIPS_VIA]->(port:Port)
WITH s, collect(port.id) AS ports, collect(port.status) AS port_statuses
WHERE (s.id = $node_id OR s.status = 'disrupted')
   OR ($node_id IN ports AND ALL(pid IN ports WHERE pid = $node_id))
WITH collect(s.id) AS blocked_supplier_ids

MATCH (p:Part)<-[:SUPPLIES]-(sup:Supplier)
WITH blocked_supplier_ids, p, collect(sup.id) AS all_suppliers
WHERE ALL(sid IN all_suppliers WHERE sid IN blocked_supplier_ids)
WITH collect(p.sku) AS blocked_skus

MATCH (o:Order)-[:CONTAINS]->(prod:Product)<-[:USED_IN]-(p:Part)
WHERE p.sku IN blocked_skus AND o.priority = 'HIGH'
RETURN DISTINCT
  o.id       AS order_id,
  o.customer AS customer,
  o.value    AS value,
  o.due_date AS due_date,
  o.priority AS priority,
  p.sku      AS blocked_part_sku,
  p.name     AS blocked_part_name
ORDER BY o.value DESC
