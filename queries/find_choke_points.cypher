// find_choke_points.cypher
// Betweenness centrality across all supply-chain node labels.
// Nodes with high betweenness are bridges; their failure cuts the most flows.

CALL algo.betweenness({
  nodeLabels: ['Supplier', 'Port', 'Factory'],
  relationshipTypes: ['SUPPLIES', 'SHIPS_VIA', 'ROUTES_TO', 'SUB_SUPPLIES']
})
YIELD node, score
RETURN
  labels(node)[0]  AS node_type,
  node.id          AS node_id,
  node.name        AS node_name,
  node.country     AS country,
  node.status      AS status,
  round(score * 10000) / 10000.0  AS betweenness_score
ORDER BY betweenness_score DESC
LIMIT 15
