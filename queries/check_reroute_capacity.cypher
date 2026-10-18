// check_reroute_capacity.cypher
// Uses FalkorDB Max Flow to verify alternate routes can carry required volume.
// Parameters: $factory_id (string), $required_qty (integer)

// First, collect candidate alternate suppliers with their capacity
MATCH (s:Supplier)-[sup:SUPPLIES]->(p:Part)-[:USED_IN]->(:Product)<-[:ASSEMBLES]-(f:Factory)
WHERE f.id = $factory_id
  AND s.status <> 'disrupted'
WITH s, sum(sup.capacity) AS total_capacity

CALL algo.maxFlow({
  sourceNodeIds: [s.id],
  targetNodeIds: [$factory_id],
  weightProperty: 'capacity',
  relationshipTypes: ['SUPPLIES', 'SHIPS_VIA', 'ROUTES_TO']
})
YIELD maxFlow
RETURN
  s.id        AS supplier_id,
  s.name      AS supplier_name,
  maxFlow,
  $required_qty AS required_qty,
  (maxFlow >= $required_qty) AS can_satisfy
