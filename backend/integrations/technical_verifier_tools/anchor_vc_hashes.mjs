import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  Contract,
  JsonRpcProvider,
  Wallet,
  WebSocketProvider,
  id,
  keccak256,
  toUtf8Bytes,
} from "ethers";

const ABI = [
  {
    inputs: [
      { internalType: "uint256", name: "_productId", type: "uint256" },
      { internalType: "bytes32", name: "_memoHash", type: "bytes32" },
      { internalType: "bytes32", name: "_railgunTxRef", type: "bytes32" },
    ],
    name: "recordPrivatePayment",
    outputs: [],
    stateMutability: "nonpayable",
    type: "function",
  },
  {
    inputs: [{ internalType: "string", name: "vcCID", type: "string" }],
    name: "confirmOrder",
    outputs: [],
    stateMutability: "nonpayable",
    type: "function",
  },
  {
    inputs: [],
    name: "getVcHash",
    outputs: [{ internalType: "bytes32", name: "", type: "bytes32" }],
    stateMutability: "view",
    type: "function",
  },
  {
    inputs: [],
    name: "phase",
    outputs: [{ internalType: "enum ProductEscrow_Initializer.Phase", name: "", type: "uint8" }],
    stateMutability: "view",
    type: "function",
  },
  {
    inputs: [],
    name: "owner",
    outputs: [{ internalType: "address", name: "", type: "address" }],
    stateMutability: "view",
    type: "function",
  },
];

function parseEnvFile(filePath) {
  const out = {};
  if (!fs.existsSync(filePath)) return out;
  for (const raw of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx < 0) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    out[key] = value;
  }
  return out;
}

function envGet(env, key, fallback = "") {
  const v = process.env[key] ?? env[key] ?? fallback;
  return typeof v === "string" ? v.trim() : v;
}

function must(env, key) {
  const v = envGet(env, key, "");
  if (!v) throw new Error(`Missing required env var: ${key}`);
  return v;
}

function ensure0x(v) {
  if (!v) return v;
  return v.startsWith("0x") ? v : `0x${v}`;
}

function resolveRpcUrl(env) {
  const rpc = envGet(env, "RPC_HTTPS_URL", "") || envGet(env, "RPC_URL", "") || envGet(env, "RPC_WSS_URL", "");
  if (!rpc) throw new Error("Missing RPC endpoint. Set RPC_HTTPS_URL (preferred), RPC_URL, or RPC_WSS_URL");
  return rpc;
}

function createProvider(rpcUrl) {
  const v = String(rpcUrl || "").toLowerCase();
  if (v.startsWith("ws://") || v.startsWith("wss://")) return new WebSocketProvider(rpcUrl);
  return new JsonRpcProvider(rpcUrl);
}

function normalizeHex(v) {
  return String(v || "").toLowerCase().replace(/^0x/, "");
}

async function main() {
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const repoRoot = path.resolve(scriptDir, "../../..");
  const env = parseEnvFile(path.join(repoRoot, "backend", ".env"));

  const deployerPk = ensure0x(must(env, "DEPLOYER_PRIVATE_KEY"));
  const issuerPk = ensure0x(must(env, "ISSUER_PRIVATE_KEY"));
  const rpcUrl = resolveRpcUrl(env);
  const manifestPathInput = envGet(env, "VC_DAG_MANIFEST_FILE", path.join(repoRoot, "data", "generated", "latest_vc_dag_manifest.json"));
  const manifestPath = path.isAbsolute(manifestPathInput) ? manifestPathInput : path.join(repoRoot, manifestPathInput);

  if (!fs.existsSync(manifestPath)) throw new Error(`Manifest file not found: ${manifestPath}`);
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const records = Array.isArray(manifest.records) ? manifest.records : [];
  if (records.length === 0) throw new Error(`Manifest has no records: ${manifestPath}`);

  const provider = createProvider(rpcUrl);
  try {
    const deployer = new Wallet(deployerPk, provider);
    const issuer = new Wallet(issuerPk, provider);
    if (deployer.address.toLowerCase() === issuer.address.toLowerCase()) {
      throw new Error("DEPLOYER_PRIVATE_KEY and ISSUER_PRIVATE_KEY must be different. Buyer tx must come from non-owner wallet.");
    }

    const receiptRows = [];
    for (const r of records) {
      const cid = String(r.cid || "");
      const productContract = String(r.productContract || "");
      const productId = BigInt(r.productId);
      if (!cid || !productContract || !r.productId) {
        throw new Error(`Record missing cid/productContract/productId: ${JSON.stringify(r)}`);
      }

      const issuerContract = new Contract(productContract, ABI, issuer);
      const deployerContract = new Contract(productContract, ABI, deployer);
      const expected = normalizeHex(keccak256(toUtf8Bytes(cid)));

      const owner = String(await deployerContract.owner()).toLowerCase();
      if (owner !== deployer.address.toLowerCase()) {
        throw new Error(`Deployer is not owner for ${productContract}. Owner=${owner}, deployer=${deployer.address.toLowerCase()}`);
      }

      let paymentTxHash = null;
      let confirmTxHash = null;

      const current = normalizeHex(await deployerContract.getVcHash());
      if (current !== expected) {
        let phase = Number(await deployerContract.phase());
        if (phase === 0) {
          const memoHash = id(`memo:${productContract}:${productId.toString()}:${cid}`);
          const txRef = id(`txref:${productContract}:${productId.toString()}:${cid}`);
          const payTx = await issuerContract.recordPrivatePayment(productId, memoHash, txRef);
          const payRcpt = await payTx.wait();
          paymentTxHash = payRcpt.hash;
          phase = Number(await deployerContract.phase());
        }

        if (phase !== 1) {
          throw new Error(`Cannot call confirmOrder in phase=${phase} for ${productContract}. Expected phase=1 (Purchased).`);
        }

        const confirmTx = await deployerContract.confirmOrder(cid);
        const confirmRcpt = await confirmTx.wait();
        confirmTxHash = confirmRcpt.hash;
      }

      const after = normalizeHex(await deployerContract.getVcHash());
      const anchored = after === expected;
      receiptRows.push({
        cid,
        productContract,
        productId: productId.toString(),
        expectedVcHash: `0x${expected}`,
        actualVcHash: `0x${after}`,
        anchored,
        paymentTxHash,
        confirmTxHash,
      });
      console.log(`anchored productId=${productId.toString()} contract=${productContract} anchored=${anchored}`);
      if (!anchored) throw new Error(`Anchor mismatch after txs for ${productContract}`);
    }

    const outDir = path.dirname(manifestPath);
    const outPath = path.join(outDir, "anchor_receipts.json");
    fs.writeFileSync(
      outPath,
      JSON.stringify(
        {
          anchoredAt: new Date().toISOString(),
          rootCid: manifest.rootCid || null,
          manifestPath,
          deployerAddress: deployer.address,
          issuerAddress: issuer.address,
          entries: receiptRows,
        },
        null,
        2
      )
    );
    console.log(`ANCHOR_RECEIPTS=${outPath}`);
  } finally {
    try {
      if (provider && typeof provider.destroy === "function") provider.destroy();
    } catch {
      // no-op
    }
  }
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
