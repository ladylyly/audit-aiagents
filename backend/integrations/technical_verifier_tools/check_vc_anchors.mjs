import { Contract, JsonRpcProvider, WebSocketProvider, keccak256, toUtf8Bytes } from "ethers";

const ABI = [
  {
    inputs: [],
    name: "getVcHash",
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
    if (!cid || !productContract) {
      failed.push({ cid: cid || null, reason: "Missing cid or productContract" });
      continue;
    }

    try {
      const contract = new Contract(productContract, ABI, provider);
      const onChainVcHash = await contract.getVcHash();
      const localVcHash = keccak256(toUtf8Bytes(cid));

      const onChainNorm = String(onChainVcHash).toLowerCase().replace(/^0x/, "");
      const localNorm = String(localVcHash).toLowerCase().replace(/^0x/, "");

      checked += 1;
      if (onChainNorm !== localNorm) {
        failed.push({ cid, productContract, reason: "Hash mismatch", expected: localNorm, actual: onChainNorm });
      }
    } catch (err) {
      failed.push({ cid, productContract, reason: err?.message || String(err) });
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

