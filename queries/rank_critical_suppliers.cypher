// rank_critical_suppliers.cypher
// Runs FalkorDB native PageRank over Supplier nodes to surface systemic importance.
// Higher score = more central to the supply network.

CALL algo.pageRank('Supplier', null)
YIELD node, score
OPTIONAL MATCH (node)-[:SUPPLIES]->(:Part)-[:USED_IN]->(:Product)<-[:CONTAINS]-(o:Order {priority: 'HIGH'})
WITH node, score, count(DISTINCT o) AS high_orders
RETURN
  node.id          AS supplier_id,
  node.name        AS supplier_name,
  node.country     AS country,
  node.tier        AS tier,
  node.status      AS status,
  round(score * 1000000) / 1000000.0 AS pagerank_score
ORDER BY high_orders DESC, pagerank_score DESC
LIMIT 20
