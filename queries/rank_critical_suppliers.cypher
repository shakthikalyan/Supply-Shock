// rank_critical_suppliers.cypher
// Runs FalkorDB native PageRank over Supplier nodes to surface systemic importance.
// Higher score = more central to the supply network.

CALL algo.pageRank({
  nodeLabels: ['Supplier'],
  relationshipTypes: ['SUPPLIES', 'SUB_SUPPLIES'],
  maxIterations: 20,
  dampingFactor: 0.85
})
YIELD node, score
RETURN
  node.id          AS supplier_id,
  node.name        AS supplier_name,
  node.country     AS country,
  node.tier        AS tier,
  node.status      AS status,
  round(score, 6)  AS pagerank_score
ORDER BY pagerank_score DESC
LIMIT 20
