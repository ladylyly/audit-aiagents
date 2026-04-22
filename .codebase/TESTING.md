# Testing

## Basic checks

- Backend tests: `python -m pytest backend/tests`
- Backend startup: `python -m backend.api.server`
- Frontend build: `cd frontend && npm run build`
- Frontend local UI: `cd frontend && npm run dev`

## Contract and verification tooling

- Deploy stack: `cd contracts/deploy_stack && npm run deploy:sepolia`
- Build `tools/zkp-backend` before running end-to-end technical verification that depends on `zkp-cli`
