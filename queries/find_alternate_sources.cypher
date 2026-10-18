// find_alternate_sources.cypher
// Finds the cheapest viable alternate supplier for a part, excluding the failed node.
// Returns candidates ordered by total cost (SUPPLIES.cost + ROUTES_TO.cost).
// Parameters: $part_sku (string), $avoid_node_id (string)

MATCH (s:Supplier)-[sup:SUPPLIES]->(p:Part)
WHERE p.sku = $part_sku
  AND s.id <> $avoid_node_id
  AND s.status <> 'disrupted'
OPTIONAL MATCH (s)-[sv:SHIPS_VIA]->(port:Port)-[rt:ROUTES_TO]->(f:Factory)
WHERE port.status <> 'disrupted'
WITH
  s,
  p,
  sup.cost            AS supply_cost,
  sup.lead_time_days  AS supply_lead,
  port.id             AS port_id,
  port.name           AS port_name,
  sv.transit_days     AS sea_days,
  rt.transit_days     AS land_days,
  rt.cost             AS route_cost,
  f.id                AS factory_id,
  f.name              AS factory_name
RETURN
  s.id                                  AS supplier_id,
  s.name                                AS supplier_name,
  s.country                             AS country,
  s.tier                                AS tier,
  supply_cost,
  supply_lead,
  port_id,
  port_name,
  sea_days,
  land_days,
  coalesce(route_cost, 0)               AS route_cost,
  (supply_cost + coalesce(route_cost,0)) AS total_cost,
  (supply_lead + coalesce(sea_days,0) + coalesce(land_days,0)) AS total_lead_days,
  factory_id,
  factory_name
ORDER BY total_cost ASC, total_lead_days ASC
LIMIT 5
