# SupplyShock ⚡

**AI-powered supply-chain disruption mitigation.**  
An agent that turns a supply-chain disruption into a verified, human-approved mitigation — fully powered by FalkorDB graph traversal and algorithms.

---

## Rule 3 (Kill-Switch)

**Without FalkorDB there is no answer, not a degraded one.**  
If the database is unreachable, the agent returns:
```json
{"error": "FalkorDB unavailable — cannot analyse disruption without the graph."}
```
No hallucinated numbers. No partial results. The API returns HTTP 503 for all write operations.

---

## MCP Tool Catalogue

All tools are registered on the MCP server (`app/mcp_server.py`). The agent calls them by name; the registry dispatches to the underlying Cypher-backed Python functions.

### Analysis tools (read-only)

| Tool | Technique | Cypher file |
|---|---|---|
| `get_blast_radius(node_id)` | Multi-hop traversal (up to 6 hops) | `queries/get_blast_radius.cypher` |
| `find_at_risk_orders(node_id)` | Traversal + alternate-source check | `queries/find_at_risk_orders.cypher` |
| `rank_critical_suppliers()` | PageRank (`algo.pageRank`) | `queries/rank_critical_suppliers.cypher` |
| `find_choke_points()` | Betweenness centrality (`algo.betweenness`) | `queries/find_choke_points.cypher` |
| `find_dependency_clusters()` | WCC (`algo.wcc`) | `queries/find_dependency_clusters.cypher` |
| `find_alternate_sources(part, avoid)` | Weighted path, excluding failed node | `queries/find_alternate_sources.cypher` |
| `check_reroute_capacity(factory, qty)` | Max Flow (`algo.maxFlow`) — stretch tool | `queries/check_reroute_capacity.cypher` |

### Simulation tool

| Tool | Purpose |
|---|---|
| `simulate_mitigation(change_set)` | `GRAPH.COPY` → mutate copy → re-run impact → diff → delete copy |

### Action tools (all gated — nothing executes without human approval)

| Tool | Purpose |
|---|---|
| `draft_purchase_order(supplier, part, qty)` | Writes a draft to the outbox |
| `notify_owner(owner, message, evidence_path)` | Drafts a notification with traversal evidence |
| `commit_mitigation(proposal_id)` | POST `/api/proposals/{id}/approve` — mutates live graph |

---

## Architecture

```
 Event (webhook / UI button)
        │
        ▼
 FastAPI backend (app/main.py)
        │
        ├── Event Ingestor  →  marks node as 'disrupted' in FalkorDB
        │
        ├── Agent Orchestrator (app/agent.py)
        │     └── Claude claude-sonnet-4-5 • tool-calling loop • ≤12 steps
        │
        ├── MCP Server (app/mcp_server.py)  ←  named tools, JSON schemas
        │     ├── Analysis  (app/tools/analysis.py)
        │     ├── Simulation (app/tools/simulate.py)   ← GRAPH.COPY
        │     └── Actions   (app/tools/actions.py)     ← outbox + approval gate
        │
        ├── FalkorDB (graph + algorithms)
        │     └── queries/*.cypher  (one file per tool, parameterised only)
        │
        ├── Audit Log (app/audit.py)  →  JSONL on disk + SSE stream
        │
        └── Web UI (web/index.html)
              ├── Cytoscape.js graph canvas
              ├── Live Cypher log (SSE)
              ├── Agent reasoning panel (SSE)
              └── Proposal card + Approve / Reject
```

---

## Planted Surprise (the demo story)

```
SUP-T2-01 (CapTech Asia, tier-2)
    └── SUB_SUPPLIES ──► SUP-01 (ElecCore)   ──► 4 capacitor parts
    └── SUB_SUPPLIES ──► SUP-02 (ChipNation) ──► 5 MCU / wireless parts
    └── SUB_SUPPLIES ──► SUP-03 (PowerFlex)  ──► 3 power module parts
                         All three SHIPS_VIA PORT-01 (Shanghai) ONLY
                                    │
                         PORT-01 closes ◄── THE EVENT
                                    │
                         14 HIGH-priority orders ← fully blocked
                         (no healthy alternate source path exists)
```

The three tier-1 suppliers look independent. They are not.  
`find_dependency_clusters()` (WCC) reveals they all live in the same component.  
`find_choke_points()` (betweenness) identifies PORT-01 as the critical bottleneck.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- An Anthropic API key

### 1. Clone and configure

```bash
git clone https://github.com/yourname/supplyshock
cd supplyshock
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

### 2. Start FalkorDB

```bash
docker compose up falkordb -d
# Verify: docker compose ps
```

### 3. Phase 0 verification (do this before anything else)

```bash
pip install falkordb
python - <<'EOF'
import falkordb
g = falkordb.FalkorDB(host='localhost', port=6379).select_graph('verify')
# Test betweenness
r = g.query("CALL algo.betweenness({nodeLabels:['X']}) YIELD node, score RETURN count(*)")
print("betweenness OK:", r)
EOF
# Also verify GRAPH.COPY via redis-cli:
# redis-cli GRAPH.COPY verify verify2
```

### 4. Seed the graph

```bash
pip install -r requirements.txt
python seed/generate.py --wipe
# Expected output: "14 HIGH-priority at-risk orders"
```

### 5. Run tests (before building anything else)

```bash
pytest tests/test_scenario.py -v
# All tests should pass against the seeded graph
```

### 6. Start the app

```bash
uvicorn app.main:app --reload
# Open http://localhost:8000
```

### 7. Docker (full stack)

```bash
docker compose up --build
```

---

## Demo Script (3 minutes)

1. Open `http://localhost:8000` — show the supply network graph
2. Click **Simulate Port Closure** — PORT-01 turns red, blast radius animates
3. Watch the Cypher log stream queries in real time
4. The reasoning panel narrates each tool call
5. Proposal appears: **14 orders at risk → 0 after reroute**, with cost delta
6. Click **Approve & Commit** — graph turns green, outbox releases the PO
7. **Kill-switch demo:** `docker compose stop falkordb`, click simulate again → agent refuses

---

## Repo Structure

```
supplyshock/
├── docker-compose.yml          FalkorDB v4.3.0 + app container
├── Dockerfile
├── requirements.txt
├── queries/                    One .cypher file per tool (parameterised only)
│   ├── get_blast_radius.cypher
│   ├── find_at_risk_orders.cypher
│   ├── rank_critical_suppliers.cypher
│   ├── find_choke_points.cypher
│   ├── find_dependency_clusters.cypher
│   ├── find_alternate_sources.cypher
│   └── check_reroute_capacity.cypher
├── seed/generate.py            Deterministic, seeded RNG (SEED=42)
├── app/
│   ├── main.py                 FastAPI + SSE endpoints
│   ├── graph.py                FalkorDB client, read/write guards
│   ├── audit.py                Audit log (JSONL + SSE pub/sub)
│   ├── agent.py                Claude tool-calling loop, ≤12 steps
│   ├── mcp_server.py           Tool registry + dispatcher
│   └── tools/
│       ├── analysis.py         Analysis tools (read-only)
│       ├── simulate.py         GRAPH.COPY simulation engine
│       └── actions.py          Outbox + approval gate
├── web/index.html              Four-pane UI (Cytoscape.js)
└── tests/test_scenario.py      Planted scenario + kill-switch assertions
```

---

## Honest Limits

- **Synthetic data.** All nodes and orders are generated by `seed/generate.py`. Actions go to an in-memory sandbox outbox, not a real ERP.
- **CPU-based.** FalkorDB uses GraphBLAS (CPU). No GPU acceleration is claimed.
- **Algorithm versions.** All algorithms (PageRank, betweenness, WCC, max flow) are verified against FalkorDB v4.3.0. Pin the image tag in `docker-compose.yml`; re-verify if you change it.
- **Decision-support prototype.** Centrality and clustering results depend on the planted dataset. This is not an autonomous purchasing system.
- **No authentication.** The approval gate is a single button. Add auth before any production deployment.
