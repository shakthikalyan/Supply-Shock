// find_dependency_clusters.cypher
// Weakly Connected Components among suppliers to reveal hidden concentration.
// Suppliers in the same component share upstream dependencies (via SUB_SUPPLIES).

CALL algo.wcc({
  nodeLabels: ['Supplier'],
  relationshipTypes: ['SUB_SUPPLIES']
})
YIELD node, componentId
WITH componentId, collect(node) AS members
WHERE size(members) > 1
RETURN
  componentId                                     AS cluster_id,
  size(members)                                   AS cluster_size,
  [n IN members | n.name]                         AS supplier_names,
  [n IN members | n.tier]                         AS tiers,
  [n IN members | n.country]                      AS countries
ORDER BY cluster_size DESC
LIMIT 10
