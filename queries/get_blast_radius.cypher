// get_blast_radius.cypher
// Traversal from a disrupted node (Port, Supplier, or Part).
// Uses undirected connection to capture upstream suppliers and downstream factories.
// Parameters: $node_id (string)

MATCH path = (start)-[*1..4]-(affected)
WHERE start.id = $node_id
RETURN DISTINCT
  start.id                              AS source_id,
  start.name                            AS source_name,
  labels(affected)                      AS affected_labels,
  coalesce(affected.id, affected.sku)   AS affected_id,
  affected.name                         AS affected_name,
  length(path)                          AS hops,
  [r IN relationships(path) | type(r)]  AS edge_types
ORDER BY hops, affected_name
