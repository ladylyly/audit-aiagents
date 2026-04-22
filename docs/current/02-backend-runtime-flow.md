# 02 Backend Runtime Flow

## Entry point

- `backend/api/server.py` is the Flask entrypoint.
- It exposes the audit API, stores finished reports, and serves report QA.

## Orchestration

- `backend/agents/orchestrator/orchestrator.py` runs the main flow.
- It builds the graph, fetches the VC payloads, runs technical verification, and then runs compliance, certification, and ESG.
- `backend/agents/technical_verification/` contains the technical verification code used by that flow.

## Shared services

- `backend/services/ipfs_fetcher.py` fetches VC payloads by CID.
- `backend/services/provenance_graph.py` builds the reachable provenance graph from the root CID.
- `backend/services/tool_registry/` connects the active tool contracts to their Python implementations.

## Runtime inputs

- `backend/assets/` holds the certification catalog, compliance rulepacks, and ESG rule files.
- `data/reports/` stores finished reports.
- Reports are loaded from disk on demand.
