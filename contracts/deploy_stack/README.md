# Local Contract Deploy Stack (Sepolia)

This folder is a self-contained Truffle deployment project used by this repository.

## What it deploys
- `ProductEscrow_Initializer`
- `ProductFactory` (pointing to the implementation)

## Prerequisites
- Node.js 18+
- A funded Sepolia deployer account
- `backend/.env` already set with `RPC_HTTPS_URL` and `DEPLOYER_PRIVATE_KEY`

## 1) Create deployment env file
From repo root:

```bash
cd contracts/deploy_stack
cp .env.truffle.example .env.truffle
```

Then set:

```env
SEPOLIA_RPC_URL=<your RPC_HTTPS_URL>
PRIVATE_KEY=<your DEPLOYER_PRIVATE_KEY>
```

## 2) Install dependencies

```bash
npm ci
```

## 3) Deploy to Sepolia

```bash
npm run deploy:sepolia
```

The migration output prints addresses for:
- `Implementation`
- `Factory`

## 4) Put addresses into agent env
Update `backend/.env`:

```env
PRODUCT_IMPLEMENTATION_ADDRESS=0x...
PRODUCT_FACTORY_ADDRESS=0x...
PRODUCT_CONTRACT_ADDRESS=
```

`PRODUCT_CONTRACT_ADDRESS` is the per-VC clone address and is set after creating products from the factory.
