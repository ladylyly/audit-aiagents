#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
AGENT_ENV="$ROOT_DIR/backend/.env"
OUT_ENV="$ROOT_DIR/contracts/deploy_stack/.env.truffle"

if [[ ! -f "$AGENT_ENV" ]]; then
  echo "backend/.env not found at $AGENT_ENV" >&2
  exit 1
fi

rpc="$(grep -E '^RPC_HTTPS_URL=' "$AGENT_ENV" | tail -n1 | cut -d'=' -f2-)"
pk="$(grep -E '^DEPLOYER_PRIVATE_KEY=' "$AGENT_ENV" | tail -n1 | cut -d'=' -f2-)"

if [[ -n "$pk" && "$pk" != 0x* ]]; then
  pk="0x$pk"
fi

if [[ -z "$rpc" || -z "$pk" ]]; then
  echo "Missing RPC_HTTPS_URL or DEPLOYER_PRIVATE_KEY in backend/.env" >&2
  exit 1
fi

cat > "$OUT_ENV" <<ENV
SEPOLIA_RPC_URL=$rpc
PRIVATE_KEY=$pk
ENV

echo "Wrote $OUT_ENV"
