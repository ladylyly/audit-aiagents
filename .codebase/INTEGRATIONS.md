# Integrations

## Runtime

- The frontend talks to the backend through the `/api/*` HTTP interface.
- In the Docker review setup, the frontend reaches the backend through the Nginx proxy.

## External Services

- IPFS data is fetched through public HTTP gateways by the backend.
- Pinata is used by the VC-DAG generation scripts when publishing generated VC JSON to IPFS.
- OpenAI is used by the backend LLM client for orchestration and report Q&A.
- Sepolia RPC access is used for contract interaction and technical verification.

## Local Tooling

- Node-based VC-DAG generation and verification scripts are in `backend/integrations/technical_verifier_tools/`.
- The Rust `zkp-cli` binary is in `tools/zkp-backend/target/release/zkp-cli`.
- Contract deployment and clone generation are handled from `contracts/deploy_stack/`.

## Contracts and Data Shapes

- Tool contracts and schemas are stored under `contracts/tools/` and `contracts/schemas/`.
- The frontend depends on the persisted backend report JSON shape exposed by the API.
