import { Contract, JsonRpcProvider, WebSocketProvider } from "ethers";

const ABI = [
  {
    inputs: [],
    name: "priceCommitment",
    outputs: [{ internalType: "bytes32", name: "", type: "bytes32" }],
    stateMutability: "view",
    type: "function",
  },
  {
    inputs: [],
    name: "getPriceCommitment",
    outputs: [{ internalType: "bytes32", name: "", type: "bytes32" }],
    stateMutability: "view",
    type: "function",
  },
];

function parseJsonStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => {
      try {
        resolve(JSON.parse(data || "{}"));
      } catch (e) {
        reject(e);
      }
    });
  });
}

function createProvider(rpcUrl) {
  const value = String(rpcUrl || "").toLowerCase();
  if (value.startsWith("ws://") || value.startsWith("wss://")) {
    return new WebSocketProvider(rpcUrl);
  }
  return new JsonRpcProvider(rpcUrl);
}

function destroyProvider(provider) {
  try {
    if (provider && typeof provider.destroy === "function") {
      provider.destroy();
    }
  } catch {
    // no-op
  }
}

function normalizeHex(value) {
  if (value === undefined || value === null) return null;
  return String(value).toLowerCase().replace(/^0x/, "");
}

async function readOnChainPriceCommitment(contract) {
  try {
    return await contract.priceCommitment();
  } catch {
    return await contract.getPriceCommitment();
  }
}

const input = await parseJsonStdin();
const rpcUrl = input?.rpcUrl;
const nodes = Array.isArray(input?.nodes) ? input.nodes : [];

if (!rpcUrl) {
  process.stdout.write(JSON.stringify({ skipped: true, verified: null, reason: "rpcUrl not provided" }));
  process.exit(0);
}

const provider = createProvider(rpcUrl);
const failed = [];
let checked = 0;

try {
  for (const node of nodes) {
    const cid = node?.cid;
    const productContract = node?.productContract;
    const vcPriceCommitment = node?.vcPriceCommitment;

    if (!cid || !productContract || !vcPriceCommitment) {
      failed.push({
        cid: cid || null,
        productContract: productContract || null,
        reason: "Missing cid, productContract, or vcPriceCommitment",
      });
      continue;
    }

    try {
      const contract = new Contract(productContract, ABI, provider);
      const onChainPriceCommitment = await readOnChainPriceCommitment(contract);

      const onChainNorm = normalizeHex(onChainPriceCommitment);
      const localNorm = normalizeHex(vcPriceCommitment);

      checked += 1;
      if (onChainNorm !== localNorm) {
        failed.push({
          cid,
          productContract,
          reason: "Price commitment mismatch",
          expected: localNorm,
          actual: onChainNorm,
        });
      }
    } catch (err) {
      failed.push({
        cid,
        productContract,
        reason: err?.message || String(err),
      });
    }
  }
} finally {
  destroyProvider(provider);
}

process.stdout.write(
  JSON.stringify({
    skipped: false,
    verified: failed.length === 0 && checked > 0,
    checked,
    total: nodes.length,
    failed,
  })
);
