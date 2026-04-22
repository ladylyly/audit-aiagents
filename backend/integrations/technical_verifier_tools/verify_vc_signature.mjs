import { verifyTypedData, TypedDataEncoder } from "ethers";

function normalizeId(value) {
  return typeof value === "string" ? value.toLowerCase() : value;
}

function extractChainId(identifier) {
  if (!identifier || typeof identifier !== "string") return null;
  const parts = identifier.toLowerCase().split(":");
  if (parts.length < 4) return null;
  const parsed = Number(parts[2]);
  return Number.isFinite(parsed) ? parsed : null;
}

const DEFAULT_CHAIN_ID = (() => {
  const parsed = Number(process.env.VC_CHAIN_ID || process.env.CHAIN_ID);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 11155111;
})();

const BASE_DOMAIN = { name: "VC", version: "1.0" };

const EIP712_TYPES = {
  Credential: [
    { name: "id", type: "string" },
    { name: "@context", type: "string[]" },
    { name: "type", type: "string[]" },
    { name: "schemaVersion", type: "string" },
    { name: "issuer", type: "Party" },
    { name: "holder", type: "Party" },
    { name: "issuanceDate", type: "string" },
    { name: "credentialSubject", type: "CredentialSubject" },
  ],
  Party: [
    { name: "id", type: "string" },
    { name: "name", type: "string" },
  ],
  CredentialSubject: [
    { name: "id", type: "string" },
    { name: "productName", type: "string" },
    { name: "batch", type: "string" },
    { name: "quantity", type: "uint256" },
    { name: "previousCredential", type: "string" },
    { name: "componentCredentials", type: "string[]" },
    { name: "certificateCredential", type: "Certificate" },
    { name: "sellerRailgunAddress", type: "string" },
    { name: "price", type: "string" },
  ],
  Certificate: [
    { name: "name", type: "string" },
    { name: "cid", type: "string" },
  ],
};

function preparePayloadForVerification(vc) {
  const clone = JSON.parse(JSON.stringify(vc || {}));

  delete clone.proof;
  delete clone.proofs;

  if (!clone.credentialSubject || typeof clone.credentialSubject !== "object") {
    clone.credentialSubject = {};
  }

  // Exclude mutable post-signing fields from payload verification.
  delete clone.credentialSubject.vcHash;
  delete clone.credentialSubject.transactionId;
  if (clone.credentialSubject.payment !== undefined) delete clone.credentialSubject.payment;
  if (clone.credentialSubject.delivery !== undefined) delete clone.credentialSubject.delivery;
  if (clone.previousVersion !== undefined) delete clone.previousVersion;

  if (clone.credentialSubject.priceCommitment && typeof clone.credentialSubject.priceCommitment === "object") {
    try {
      clone.credentialSubject.price = JSON.stringify(clone.credentialSubject.priceCommitment);
    } catch {
      clone.credentialSubject.price = String(clone.credentialSubject.priceCommitment);
    }
    delete clone.credentialSubject.priceCommitment;
  }

  if (clone.credentialSubject.price !== undefined && typeof clone.credentialSubject.price !== "string") {
    try {
      clone.credentialSubject.price = JSON.stringify(clone.credentialSubject.price);
    } catch {
      clone.credentialSubject.price = String(clone.credentialSubject.price);
    }
  }

  if (clone.credentialSubject.listing && typeof clone.credentialSubject.listing === "object") {
    clone.credentialSubject.certificateCredential =
      clone.credentialSubject.listing.certificateCredential || { name: "", cid: "" };
    clone.credentialSubject.componentCredentials = clone.credentialSubject.listing.componentCredentials || [];
    clone.credentialSubject.sellerRailgunAddress = clone.credentialSubject.listing.sellerRailgunAddress || "";
    delete clone.credentialSubject.listing;
  }

  if (!clone.credentialSubject.certificateCredential) {
    clone.credentialSubject.certificateCredential = { name: "", cid: "" };
  }
  clone.credentialSubject.certificateCredential.name = String(clone.credentialSubject.certificateCredential.name || "");
  clone.credentialSubject.certificateCredential.cid = String(clone.credentialSubject.certificateCredential.cid || "");

  if (clone.credentialSubject.id == null) clone.credentialSubject.id = String(clone.issuer?.id || "");
  if (clone.credentialSubject.productName == null) clone.credentialSubject.productName = "";
  if (clone.credentialSubject.batch == null) clone.credentialSubject.batch = "";
  if (clone.credentialSubject.quantity == null) clone.credentialSubject.quantity = 0;
  if (clone.credentialSubject.previousCredential == null) clone.credentialSubject.previousCredential = "";
  if (!Array.isArray(clone.credentialSubject.componentCredentials)) clone.credentialSubject.componentCredentials = [];
  clone.credentialSubject.componentCredentials = clone.credentialSubject.componentCredentials
    .filter((x) => x != null)
    .map((x) => String(x));

  if (clone.credentialSubject.price == null) clone.credentialSubject.price = "";
  if (typeof clone.credentialSubject.sellerRailgunAddress !== "string") clone.credentialSubject.sellerRailgunAddress = "";
  if (!clone.schemaVersion) clone.schemaVersion = "1.0";

  if (clone.issuer?.id) clone.issuer.id = normalizeId(clone.issuer.id);
  if (clone.holder?.id) clone.holder.id = normalizeId(clone.holder.id);
  if (clone.credentialSubject?.id) clone.credentialSubject.id = normalizeId(clone.credentialSubject.id);

  return clone;
}

function buildProofArray(vc) {
  if (Array.isArray(vc?.proof)) return vc.proof;
  if (vc?.proofs && typeof vc.proofs === "object") return Object.values(vc.proofs);
  return [];
}

async function verifyProof({ proof, dataToVerify, role, expectedDid, chainId, contractAddress }) {
  const result = {
    matching_vc: false,
    matching_signer: false,
    signature_verified: false,
    recovered_address: null,
    expected_address: null,
    skipped: false,
    error: null,
  };

  if (!proof) {
    result.error = `No ${role} proof provided`;
    return result;
  }

  const verificationMethod = proof.verificationMethod;
  if (!verificationMethod || !verificationMethod.toLowerCase().startsWith("did:ethr:")) {
    result.error = `Invalid verificationMethod in ${role} proof`;
    return result;
  }

  const expectedAddress = verificationMethod.split(":").pop().toLowerCase().replace(/#.*$/, "");
  result.expected_address = expectedAddress;

  if (!expectedDid || !expectedDid.toLowerCase().includes(expectedAddress)) {
    result.error = `DID mismatch for ${role}`;
    return result;
  }
  result.matching_vc = true;

  const effectiveChainId = chainId || DEFAULT_CHAIN_ID;
  const domains = [{ ...BASE_DOMAIN, chainId: effectiveChainId }];
  if (contractAddress) {
    domains.push({ ...BASE_DOMAIN, chainId: effectiveChainId, verifyingContract: contractAddress });
  }

  let lastError = null;
  for (const domain of domains) {
    try {
      const payloadHash = TypedDataEncoder.hash(domain, EIP712_TYPES, dataToVerify);
      if (proof.payloadHash && proof.payloadHash !== payloadHash) {
        lastError = `Payload hash mismatch for ${role}`;
        continue;
      }

      const recovered = verifyTypedData(domain, EIP712_TYPES, dataToVerify, proof.jws);
      result.recovered_address = recovered;
      result.matching_signer = recovered.toLowerCase() === expectedAddress;
      result.signature_verified = result.matching_signer;
      if (result.signature_verified) return result;

      lastError = `Recovered signer mismatch for ${role}`;
    } catch (err) {
      lastError = err?.message || String(err);
    }
  }

  result.error = lastError || `Signature verification failed for ${role}`;
  return result;
}

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

const input = await parseJsonStdin();
const vc = input?.vc;
const contractAddress = input?.contractAddress || null;

try {
  const proofArr = buildProofArray(vc);
  if (!proofArr.length) throw new Error("No proofs found in VC");

  const dataToVerify = preparePayloadForVerification(vc);
  const issuerDid = dataToVerify.issuer?.id?.toLowerCase();
  const holderDid = dataToVerify.holder?.id?.toLowerCase();

  const issuerProof =
    proofArr.find((p) => p?.role === "seller") ||
    proofArr.find((p) => p?.verificationMethod?.toLowerCase?.().includes(issuerDid));

  const holderProof =
    proofArr.find((p) => p?.role === "holder" || p?.role === "buyer") ||
    proofArr.find((p) => p?.verificationMethod?.toLowerCase?.().includes(holderDid));

  const issuerChainId =
    extractChainId(issuerProof?.verificationMethod) || extractChainId(dataToVerify.issuer?.id) || DEFAULT_CHAIN_ID;
  const holderChainId =
    extractChainId(holderProof?.verificationMethod) || extractChainId(dataToVerify.holder?.id) || issuerChainId;

  const issuer = await verifyProof({
    proof: issuerProof,
    dataToVerify,
    role: "issuer",
    expectedDid: dataToVerify.issuer?.id,
    chainId: issuerChainId,
    contractAddress,
  });

  let holder;
  if (!holderProof) {
    holder = {
      matching_vc: true,
      matching_signer: true,
      signature_verified: true,
      recovered_address: null,
      expected_address: null,
      skipped: true,
      error: null,
    };
  } else {
    holder = await verifyProof({
      proof: holderProof,
      dataToVerify,
      role: "holder",
      expectedDid: dataToVerify.holder?.id,
      chainId: holderChainId,
      contractAddress,
    });
  }

  const success = issuer.signature_verified === true && (holder.skipped === true || holder.signature_verified === true);
  process.stdout.write(JSON.stringify({ success, message: "VC verification complete.", issuer, holder }));
} catch (err) {
  process.stdout.write(JSON.stringify({ success: false, message: err?.message || String(err) }));
  process.exitCode = 0;
}

