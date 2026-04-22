# Architecture

## Frontend

- `frontend/` is the React UI.
- Local development uses Vite.
- The Docker review setup builds the frontend and serves it with Nginx.
- API calls go through `/api` and are proxied to the backend service.

## Backend

- `backend/api/server.py` is the runtime entrypoint and HTTP API.
- Reports are stored in `data/reports`.
- Stored reports are loaded on demand, not all at startup.
- `backend/agents/orchestrator/` runs graph building and the technical, compliance, certification, and ESG flows.
- `backend/agents/technical_verification/` contains the deterministic verification logic.
- `backend/services/tool_registry/` connects YAML tool contracts to Python implementations.
- `backend/assets/` contains rulepacks, catalogs, lookups, and templates.

## Verification and Generation Tooling

- `backend/integrations/technical_verifier_tools/` contains the Node scripts for VC-DAG generation and verification.
- `tools/zkp-backend/` contains the Rust `zkp-cli` binary.
- `contracts/deploy_stack/` contains the Truffle deployment flow and the generated product clone data used by the generation scripts.

## Docker Review Setup

- `docker-compose.yml` defines the two-service review setup.
- The backend container includes the Python API, the Node tooling, and `zkp-cli`.
- The frontend container serves the built UI with Nginx.
