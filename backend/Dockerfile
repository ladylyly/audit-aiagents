FROM rust:1.81-bookworm AS zkp-builder

WORKDIR /build
COPY tools/zkp-backend /build/tools/zkp-backend
WORKDIR /build/tools/zkp-backend
RUN cargo build --release --bin zkp-cli


FROM node:20-bookworm-slim AS tool-node-deps

WORKDIR /app/backend/integrations/technical_verifier_tools
COPY backend/integrations/technical_verifier_tools/package.json ./
COPY backend/integrations/technical_verifier_tools/package-lock.json ./
RUN npm ci


FROM node:20-bookworm-slim AS node-runtime


FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
RUN ln -s /usr/local/bin/node /usr/local/bin/nodejs

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY contracts /app/contracts
COPY data /app/data

COPY --from=tool-node-deps /app/backend/integrations/technical_verifier_tools/node_modules /app/backend/integrations/technical_verifier_tools/node_modules
COPY --from=zkp-builder /build/tools/zkp-backend/target/release/zkp-cli /app/tools/zkp-backend/target/release/zkp-cli

EXPOSE 7002

CMD ["python", "-m", "backend.api.server"]
