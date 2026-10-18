// check_reroute_capacity.cypher
// Calculates end-to-end bottleneck capacity from candidate alternate suppliers to target factory.
// Traverses Supplier -> Part -> Product <- Factory along with healthy Port routing.
// Parameters: $factory_id (string), $required_qty (integer)

MATCH (s:Supplier)-[sup:SUPPLIES]->(p:Part)-[:USED_IN]->(prod:Product)<-[:ASSEMBLES]-(f:Factory)
WHERE f.id = $factory_id
  AND s.status <> 'disrupted'
MATCH (s)-[:SHIPS_VIA]->(port:Port)-[route:ROUTES_TO]->(f)
WHERE port.status <> 'disrupted'
WITH s, CASE WHEN sup.capacity < route.capacity THEN sup.capacity ELSE route.capacity END AS flow
RETURN
  s.id           AS supplier_id,
  s.name         AS supplier_name,
  max(flow)      AS maxFlow,
  $required_qty  AS required_qty,
  (max(flow) >= $required_qty) AS can_satisfy
ORDER BY maxFlow DESC
LIMIT 10
