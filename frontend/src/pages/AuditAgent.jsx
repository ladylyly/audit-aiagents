import { useState, useEffect, useRef, useCallback } from "react";
import ProvenanceGraphPanel from "../features/audit/ProvenanceGraphPanel.jsx";
import ManagementSummary from "../features/audit/ManagementSummary.jsx";
import DomainSummariesSection from "../features/audit/DomainSummariesSection.jsx";

const POLL_INTERVAL_MS = 2500;

const TECHNICAL_STEP_ORDER = [
  "signature",
  "zkp",
  "current_anchor",
  "provenance",
  "governance",
  "chain_anchors",
];

// ─────────────────────────────────────────────────────────────────────────────
// Demo Dataset A — ACME Components GmbH: mostly passing, two minor findings
// ─────────────────────────────────────────────────────────────────────────────
const DEMO_A = {
  reportId: "demo-a",
  rootCid: "bafybeig6xv5nwphfmvcnektpnojts33jqcuam7bmye2pb54adnrtccjlsu",
  status: "done",
  result: {
    success: true,
    entity: "ACME Components GmbH",
    auditDate: "2026-03-11",
    llm_summary:
      "ACME Components GmbH has passed all critical technical verification checks for the Q1 2026 supply chain audit cycle. Cryptographic signatures on all submitted Verifiable Credentials are valid. Zero-knowledge proof verification confirms regulatory compliance without exposing proprietary data.\n\nTwo minor observations were raised under CSDDD Article 7 regarding disclosure completeness for Tier-2 subcontractors. This must be addressed in the next reporting period. ESG performance is strong on environmental metrics (87/100) but the most recent social audit report is overdue and must be submitted before 30 April 2026 to maintain certification status.",
    result_bundle: {
      technical: {
        success: true,
        claims: ["Signature valid", "ZKP verified", "Anchor confirmed"],
        failures: [],
        evidence: {
          stepStatus: {
            signature:      { label: "Signature Verification",  status: "passed", detail: "Ed25519 signature valid — issuer DID confirmed" },
            zkp:            { label: "Zero-Knowledge Proof",     status: "passed", detail: "zk-SNARK proof verified against public parameters" },
            current_anchor: { label: "On-Chain Anchor",          status: "passed", detail: "CID anchored on Ethereum mainnet — block 19,842,017" },
            provenance:     { label: "Provenance Chain",         status: "passed", detail: "Full DAG traversal complete — 12 nodes, no gaps" },
            governance:     { label: "Governance Rules",         status: "passed", detail: "Schema v2.1 compliant — all required fields present" },
            chain_anchors:  { label: "Historical Anchors",       status: "passed", detail: "3 historical anchors verified — no revocations found" },
          },
        },
      },
      domainStatus: {
        technical: {
          state: "pass", score: 100, findings: 0,
          detail: ["Signature valid", "ZKP verified", "Anchor confirmed", "Provenance chain intact"],
        },
        compliance: {
          state: "pass", score: 91, findings: 2,
          detail: ["CSDDD Art. 7 — Tier-2 disclosure gap", "CSDDD Art. 9 — passed"],
          observations: ["Article 7 requires full Tier-2 subcontractor disclosure by next reporting period"],
          actions: [{ text: "Submit complete Tier-2 supplier disclosure under CSDDD Art. 7", deadline: "30 Jun 2026" }],
          articles: [
            { id: "Art. 5",  title: "Due Diligence Policy",      status: "pass",    detail: "Policy document up to date and publicly available on company website." },
            { id: "Art. 7",  title: "Supply Chain Transparency", status: "warning", detail: "Tier-2 subcontractor disclosure incomplete — 3 of 12 suppliers missing from registry. Must be resolved before next reporting period." },
            { id: "Art. 9",  title: "Remediation Measures",      status: "pass",    detail: "Corrective action process documented and tested in Q4 2025." },
            { id: "Art. 13", title: "Reporting Obligations",     status: "pass",    detail: "Annual sustainability report submitted on time. All required disclosures present." },
            { id: "Art. 17", title: "Complaints Procedure",      status: "pass",    detail: "Grievance mechanism active and accessible to external parties via supplier portal." },
          ],
        },
        certification: {
          state: "pass", score: 96, findings: 0,
          detail: ["ISO 14001:2015 — valid until Dec 2026", "SA8000:2014 — valid until Jun 2026"],
          certifications: [
            { name: "ISO 14001:2015", title: "Environmental Management System", status: "pass", validUntil: "Dec 2026", issuedBy: "TÜV SÜD",        detail: "No non-conformances found in latest surveillance audit (Oct 2025)." },
            { name: "SA8000:2014",    title: "Social Accountability",           status: "pass", validUntil: "Jun 2026", issuedBy: "Bureau Veritas",  detail: "Social audit completed March 2025. All criteria met. Next audit scheduled Apr 2026." },
          ],
        },
        esg: {
          state: "uncertain", score: 82, findings: 1,
          detail: ["Environmental score: 87/100", "Social audit report overdue", "Governance score: 82/100"],
          observations: ["Social audit documentation is overdue — must be submitted before 30 Apr 2026"],
          actions: [{ text: "Upload updated social audit report to supplier portal", deadline: "30 Apr 2026" }],
          breakdown: { environmental: 87, social: 71, governance: 82 },
          items: [
            { category: "Environmental", title: "Carbon Emissions Reporting",  status: "pass",    detail: "Scope 1 & 2 emissions reported. 12% YoY reduction achieved." },
            { category: "Environmental", title: "Waste Management",            status: "pass",    detail: "ISO 14001 compliant waste management programme active." },
            { category: "Social",        title: "Social Audit Documentation",  status: "warning", detail: "Most recent SA8000 social audit report was due Jan 2026. Upload required before 30 Apr 2026." },
            { category: "Social",        title: "Worker Health & Safety",      status: "pass",    detail: "Zero lost-time incidents recorded in 2025. Safety management system active." },
            { category: "Governance",    title: "Anti-Bribery & Corruption",   status: "pass",    detail: "ABC policy signed and distributed to all staff. Annual training completed." },
            { category: "Governance",    title: "Board Oversight of ESG",      status: "pass",    detail: "ESG committee established at board level. Quarterly reporting in place." },
          ],
        },
      },
    },
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Demo Dataset B — Balkan Parts d.o.o.: multiple failures across domains
// ─────────────────────────────────────────────────────────────────────────────
const DEMO_B = {
  reportId: "demo-b",
  rootCid: "bafybeihdwdcefgh4c5mvv6dxcurx6bq2yjkqpddtyjnwnktl7ia3h3xrfa",
  status: "done",
  result: {
    success: false,
    entity: "Balkan Parts d.o.o.",
    auditDate: "2026-03-11",
    llm_summary:
      "Balkan Parts d.o.o. has failed multiple critical compliance and certification checks in this audit cycle. The technical verification of the root Verifiable Credential was successful, confirming data integrity. However, significant regulatory non-conformances were identified.\n\nCompliance assessment found that no documented due diligence policy exists (CSDDD Art. 5) and the supplier registry is not maintained (Art. 7), making it impossible to verify the supply chain. Both the ISO 14001:2015 and SA8000:2014 certificates have either expired or been suspended. ESG performance is critically low on social metrics. Immediate corrective action is required before this supplier can be approved for continued use.",
    result_bundle: {
      technical: {
        success: true,
        claims: ["Signature valid", "ZKP verified"],
        failures: [],
        evidence: {
          stepStatus: {
            signature:      { label: "Signature Verification",  status: "passed", detail: "Ed25519 signature valid — issuer DID confirmed" },
            zkp:            { label: "Zero-Knowledge Proof",     status: "passed", detail: "zk-SNARK proof verified" },
            current_anchor: { label: "On-Chain Anchor",          status: "passed", detail: "CID anchored on Ethereum mainnet — block 19,891,204" },
            provenance:     { label: "Provenance Chain",         status: "passed", detail: "DAG traversal complete — 7 nodes" },
            governance:     { label: "Governance Rules",         status: "failed", detail: "Schema v2.1 validation failed — 2 required fields missing: 'dueDiligencePolicy', 'supplierRegistry'" },
            chain_anchors:  { label: "Historical Anchors",       status: "passed", detail: "1 historical anchor verified" },
          },
        },
      },
      domainStatus: {
        technical: {
          state: "pass", score: 88, findings: 1,
          detail: ["Governance schema validation failed — 2 required fields missing"],
        },
        compliance: {
          state: "fail", score: 38, findings: 4,
          detail: ["Art. 5 — No due diligence policy", "Art. 7 — Supplier registry missing", "Art. 17 — No complaints procedure"],
          actions: [
            { text: "Establish and publish a CSDDD-compliant due diligence policy (Art. 5)", deadline: "30 Apr 2026" },
            { text: "Set up and populate supplier registry with all Tier-1 and Tier-2 suppliers (Art. 7)", deadline: "30 Apr 2026" },
            { text: "Implement accessible grievance mechanism for workers and external parties (Art. 17)", deadline: "30 May 2026" },
          ],
          articles: [
            { id: "Art. 5",  title: "Due Diligence Policy",      status: "fail",    detail: "No documented due diligence policy found. Policy must be established, approved by management, and published before next audit." },
            { id: "Art. 7",  title: "Supply Chain Transparency", status: "fail",    detail: "Supplier registry not maintained. Unable to verify any Tier-1 or Tier-2 suppliers. Full registry required." },
            { id: "Art. 9",  title: "Remediation Measures",      status: "warning", detail: "Remediation process exists on paper but has not been tested or exercised in the past 24 months. Evidence of a live test required." },
            { id: "Art. 13", title: "Reporting Obligations",     status: "pass",    detail: "Annual sustainability report submitted. Disclosure content adequate for current requirements." },
            { id: "Art. 17", title: "Complaints Procedure",      status: "fail",    detail: "No accessible grievance mechanism identified for workers or external parties. Required under Art. 17(2)." },
          ],
        },
        certification: {
          state: "fail", score: 31, findings: 2,
          detail: ["ISO 14001:2015 — certificate expired", "SA8000:2014 — certificate suspended"],
          actions: [
            { text: "Schedule ISO 14001:2015 re-certification audit with TÜV SÜD", deadline: "30 Apr 2026" },
            { text: "Submit corrective action plan for SA8000 working hours non-conformance", deadline: "30 May 2026" },
          ],
          certifications: [
            { name: "ISO 14001:2015", title: "Environmental Management System", status: "expired",   validUntil: "Expired 15 Jan 2026", issuedBy: "TÜV SÜD",        detail: "Certificate expired 15 January 2026. Re-certification audit has not been scheduled. Supplier cannot claim ISO 14001 compliance." },
            { name: "SA8000:2014",    title: "Social Accountability",           status: "suspended", validUntil: "Suspended Mar 2026",   issuedBy: "Bureau Veritas",  detail: "Non-conformance detected in working hours monitoring during surveillance audit. Certificate suspended pending corrective action plan submission by 30 May 2026." },
            { name: "ISO 9001:2015",  title: "Quality Management System",      status: "pass",      validUntil: "Aug 2027",             issuedBy: "DNV",             detail: "Valid. No findings in latest audit cycle (Jan 2026)." },
          ],
        },
        esg: {
          state: "fail", score: 44, findings: 3,
          detail: ["Environmental score: 61/100", "Social score: 28/100 — critical", "Governance score: 52/100"],
          actions: [
            { text: "Conduct independent social audit and remediate all non-conformances", deadline: "30 Jun 2026" },
            { text: "Establish board-level ESG oversight and quarterly reporting", deadline: "30 Sep 2026" },
          ],
          breakdown: { environmental: 61, social: 28, governance: 52 },
          items: [
            { category: "Environmental", title: "Carbon Emissions Reporting",   status: "warning", detail: "Scope 1 emissions reported but Scope 2 and 3 data absent. Full reporting required." },
            { category: "Environmental", title: "Waste Management",             status: "warning", detail: "Waste management procedure exists but no third-party verification for the past 2 years." },
            { category: "Social",        title: "Working Hours Compliance",     status: "fail",    detail: "Workers reported systematic overtime exceeding legal limits. Root cause under investigation by Bureau Veritas." },
            { category: "Social",        title: "Freedom of Association",       status: "fail",    detail: "Evidence of restriction of workers' right to organise. Corrective action required immediately." },
            { category: "Social",        title: "Worker Health & Safety",       status: "warning", detail: "2 recordable incidents in 2025. Safety management system exists but requires independent audit." },
            { category: "Governance",    title: "Anti-Bribery & Corruption",   status: "pass",    detail: "ABC policy in place. Annual training completed for all management staff." },
            { category: "Governance",    title: "Board Oversight of ESG",      status: "fail",    detail: "No ESG committee or board-level oversight established. Required for regulatory reporting." },
          ],
        },
      },
    },
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Demo Dataset C — Northstar Cathodes Sp. z o.o.: targeted edge-case review
// ─────────────────────────────────────────────────────────────────────────────
const DEMO_C = {
  reportId: "demo-c",
  rootCid: "bafybeif6hmiddlecasevcgovernance3v7r5z2i5m5kz7lta2acme7demo",
  status: "done",
  result: {
    success: false,
    entity: "Northstar Cathodes Sp. z o.o.",
    auditDate: "2026-03-18",
    llm_summary:
      "Northstar Cathodes Sp. z o.o. sits between the compliant and non-compliant demo scenarios. Core cryptographic checks passed: signatures, zero-knowledge proofs, and on-chain anchors all verified successfully. However, a targeted provenance anomaly was identified after one precursor VC was re-issued during an internal legal-entity transfer, creating an issuer-holder governance mismatch that requires analyst review.\n\nThis is treated as a middle case because the supplier still maintains an active due diligence programme, valid core certifications, and generally acceptable ESG controls. The open items are concentrated in a few review-heavy areas rather than representing systemic failure: governance continuity in the VC chain, a near-expiry social certificate, and incomplete worker interview evidence for the latest social audit cycle.",
    result_bundle: {
      technical: {
        success: false,
        claims: ["Signature valid", "ZKP verified", "Anchor confirmed", "Provenance path intact"],
        failures: [{ code: "GOVERNANCE_REVIEW_REQUIRED", reason: "Mid-chain issuer-holder relationship changed after legal-entity transfer; provenance remains connected but governance consistency requires review." }],
        evidence: {
          stepStatus: {
            signature:      { label: "Signature Verification",  status: "passed", detail: "All VC signatures valid — no post-signature mutations detected" },
            zkp:            { label: "Zero-Knowledge Proof",     status: "passed", detail: "zk-SNARK proof verified against disclosed public inputs" },
            current_anchor: { label: "On-Chain Anchor",          status: "passed", detail: "Root VC CID anchored on Ethereum mainnet — block 19,861,244" },
            provenance:     { label: "Provenance Chain",         status: "passed", detail: "Full DAG traversal complete — 14 nodes, no missing links" },
            governance:     { label: "Governance Rules",         status: "failed", detail: "1 issuer-holder continuity mismatch detected after subsidiary transfer on precursor cathode VC" },
            chain_anchors:  { label: "Historical Anchors",       status: "passed", detail: "4 historical anchors verified — no revocations found" },
          },
        },
      },
      domainStatus: {
        technical: {
          state: "uncertain", score: 74, findings: 1,
          detail: ["Signatures valid", "ZKP verified", "Anchors confirmed", "Governance continuity review required on 1 VC re-issuance event"],
          observations: ["A legal-entity transfer preserved provenance but changed the expected issuer-holder chain on one intermediate VC."],
          actions: [{ text: "Review and attest the legal-entity transfer for the precursor cathode VC", deadline: "15 May 2026" }],
        },
        compliance: {
          state: "pass", score: 84, findings: 1,
          detail: ["CSDDD Art. 5 — passed", "CSDDD Art. 7 — disclosure complete", "CSDDD Art. 9 — remediation drill evidence overdue"],
          observations: ["The due diligence framework is in place, but the annual remediation tabletop exercise evidence has not yet been uploaded."],
          actions: [{ text: "Upload 2026 remediation drill evidence under CSDDD Art. 9", deadline: "31 May 2026" }],
          articles: [
            { id: "Art. 5",  title: "Due Diligence Policy",      status: "pass",    detail: "Policy approved by management and published in January 2026." },
            { id: "Art. 7",  title: "Supply Chain Transparency", status: "pass",    detail: "Tier-1 and Tier-2 supplier registry complete for the audited cathode line." },
            { id: "Art. 9",  title: "Remediation Measures",      status: "warning", detail: "Corrective action process exists and is assigned, but evidence of the 2026 remediation drill is still pending upload." },
            { id: "Art. 13", title: "Reporting Obligations",     status: "pass",    detail: "Annual sustainability report submitted on time with all mandatory disclosures." },
            { id: "Art. 17", title: "Complaints Procedure",      status: "pass",    detail: "Whistleblower and supplier grievance channels remain active and externally accessible." },
          ],
        },
        certification: {
          state: "uncertain", score: 79, findings: 1,
          detail: ["ISO 14001:2015 — valid until Nov 2026", "SA8000:2014 — valid but renewal audit evidence incomplete"],
          observations: ["The social certification is still valid, but the renewal package is missing worker interview annexes from the latest surveillance cycle."],
          actions: [{ text: "Submit SA8000 surveillance annexes to complete the renewal package", deadline: "20 May 2026" }],
          certifications: [
            { name: "ISO 14001:2015", title: "Environmental Management System", status: "pass", validUntil: "Nov 2026", issuedBy: "TÜV Rheinland", detail: "Valid. Surveillance audit closed with no major non-conformances in February 2026." },
            { name: "SA8000:2014",    title: "Social Accountability",           status: "warning", validUntil: "Valid until Jul 2026", issuedBy: "Bureau Veritas", detail: "Certificate remains active, but the renewal file lacks worker interview annexes and corrective action closure notes from the latest surveillance audit." },
          ],
        },
        esg: {
          state: "uncertain", score: 71, findings: 2,
          detail: ["Environmental score: 82/100", "Social score: 63/100 — review", "Governance score: 68/100"],
          observations: ["No critical ESG breach was identified, but the supplier needs stronger evidence for worker interview coverage and board review of the legal-entity transfer."],
          actions: [
            { text: "Upload worker interview coverage summary for the March 2026 social audit", deadline: "20 May 2026" },
            { text: "Record board oversight minutes for the subsidiary transfer affecting VC governance", deadline: "31 May 2026" },
          ],
          breakdown: { environmental: 82, social: 63, governance: 68 },
          items: [
            { category: "Environmental", title: "Carbon Emissions Reporting",  status: "pass",    detail: "Scope 1 and 2 emissions reported with plant-level metering. Reduction trajectory remains on plan." },
            { category: "Environmental", title: "Waste Management",            status: "pass",    detail: "Hazardous waste manifests reconciled and verified during the latest audit cycle." },
            { category: "Social",        title: "Worker Interview Coverage",   status: "warning", detail: "Interview annexes from the latest SA8000 surveillance cycle are incomplete, limiting verification depth." },
            { category: "Social",        title: "Worker Health & Safety",      status: "pass",    detail: "No lost-time incidents reported in the last 12 months. Safety committee minutes available." },
            { category: "Governance",    title: "Corporate Structure Change",  status: "warning", detail: "A March 2026 subsidiary transfer was recorded in the VCs but board oversight evidence has not yet been attached." },
            { category: "Governance",    title: "Anti-Bribery & Corruption",   status: "pass",    detail: "ABC controls remain active and annual attestations were completed for all management staff." },
          ],
        },
      },
    },
  },
};

const DEMOS = { A: DEMO_A, B: DEMO_B, C: DEMO_C };

// ── Helpers ───────────────────────────────────────────────────────────────────
function hasRootFetchFailure(record) {
  const errorText = String(record?.error ?? "");
  const technicalFailures = record?.result?.result_bundle?.technical?.failures ?? [];
  return (
    errorText.includes("Failed to fetch root CID") ||
    technicalFailures.some((failure) => failure?.code === "ROOT_VC_FETCH_FAILED")
  );
}

function deriveTechnicalChecks(record) {
  const rootFetchFailed = hasRootFetchFailure(record);
  const progressSteps = record?.progress?.steps ?? {};
  const finalSteps    = record?.result?.result_bundle?.technical?.evidence?.stepStatus ?? {};
  const stepsSource   = record?.status === "done" && Object.keys(finalSteps).length > 0 ? finalSteps : progressSteps;

  if (rootFetchFailed) {
    return [
      {
        key: "root_fetch",
        label: "Root VC fetch",
        status: "failed",
        detail: record?.error ?? "Root VC CID could not be fetched from IPFS.",
      },
      {
        key: "signature",
        label: "Signature verification",
        status: "blocked",
        detail: "Could not run signature verification because the root VC CID could not be fetched.",
      },
      {
        key: "zkp",
        label: "ZKP verification",
        status: "blocked",
        detail: "Could not run ZKP verification because the root VC CID could not be fetched.",
      },
      {
        key: "price_commitment_anchor",
        label: "Price commitment anchor",
        status: "blocked",
        detail: "Could not run anchor verification because the root VC CID could not be fetched.",
      },
      {
        key: "current_anchor",
        label: "Current VC hash anchor",
        status: "blocked",
        detail: "Could not run anchor verification because the root VC CID could not be fetched.",
      },
      {
        key: "provenance",
        label: "Provenance continuity",
        status: "blocked",
        detail: "Could not build the provenance graph because the root VC CID could not be fetched.",
      },
      {
        key: "governance",
        label: "Governance consistency",
        status: "blocked",
        detail: "Could not run governance verification because the root VC CID could not be fetched.",
      },
      {
        key: "chain_anchors",
        label: "Chain-wide anchors",
        status: "blocked",
        detail: "Could not run chain-wide anchor verification because the root VC CID could not be fetched.",
      },
    ];
  }

  return TECHNICAL_STEP_ORDER.map((key) => {
    const step = stepsSource[key];
    if (!step) {
      return {
        key, label: key,
        status: record?.status === "running" && key === "signature" ? "running" : "pending",
        detail: record?.status === "running" && key === "signature" ? "Starting verification" : null,
      };
    }
    return { key, label: step.label ?? key, status: step.status ?? "pending", detail: step.detail ?? null };
  });
}

function overallTopbarState(record) {
  if (!record) return null;
  if (record.status === "running") return "running";
  if (record.status === "error")   return "fail";
  const domainStatus = record?.result?.result_bundle?.domainStatus ?? {};
  const domains = Object.values(domainStatus);
  if (domains.length === 0) return null;
  const states = domains.map((d) => d?.state).filter(Boolean);
  if (states.includes("running")) return "running";
  const scores = domains.map((d) => d?.score).filter((s) => Number.isFinite(s));
  if (scores.length === 0 || scores.length < domains.length) return null;
  const avg = scores.reduce((sum, s) => sum + s, 0) / scores.length;
  if (avg >= 85) return "pass";
  if (avg >= 55) return "uncertain";
  return "fail";
}

function graphPayloadFromStoredGraph(rootCid, graph) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph?.edges) ? graph.edges : [];
  return {
    graph,
    view: {
      nodes: nodes
        .filter((n) => typeof n?.cid === "string" && n.cid)
        .map((n) => ({
          id: n.cid,
          cid: n.cid,
          label: n.cid.length > 12 ? `${n.cid.slice(0, 12)}...` : n.cid,
          issuerAddress: n.issuerAddress ?? null,
          holderAddress: n.holderAddress ?? null,
          productContract: n.productContract ?? null,
        })),
      edges: edges
        .filter((e) => typeof e?.from === "string" && typeof e?.to === "string" && e.from && e.to)
        .map((e) => ({
          id: `${e.from}->${e.to}`,
          source: e.from,
          target: e.to,
      })),
      rootCid: rootCid ?? null,
    },
  };
}

function VCDetailDrawer({ cid, vc, onClose }) {
  const [copyState, setCopyState] = useState("idle");
  const hasVc = Boolean(cid && vc);

  async function handleCopy() {
    if (!hasVc || typeof navigator === "undefined" || !navigator.clipboard?.writeText) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(vc, null, 2));
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 1500);
    } catch {
      setCopyState("error");
      window.setTimeout(() => setCopyState("idle"), 1500);
    }
  }

  if (!hasVc) {
    return (
      <div className="vc-detail-panel vc-detail-empty">
        <div className="vc-detail-empty-title">Select a VC in the provenance graph</div>
        <div className="vc-detail-empty-text">
          Click a CID in the provenance graph to inspect the complete VC JSON.
        </div>
      </div>
    );
  }

  return (
    <div className="vc-detail-panel">
      <div className="vc-detail-header">
        <div>
          <div className="vc-detail-label">Selected VC</div>
          <div className="vc-detail-cid">{cid}</div>
        </div>
        <div className="vc-detail-actions">
          <button className="btn btn-secondary vc-detail-btn" type="button" onClick={handleCopy}>
            {copyState === "copied" ? "Copied" : copyState === "error" ? "Copy failed" : "Copy JSON"}
          </button>
          <button className="btn btn-secondary vc-detail-btn" type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
      <pre className="vc-detail-json">{JSON.stringify(vc, null, 2)}</pre>
    </div>
  );
}

function VCDetailStatus({ cid, loading, error, onClose }) {
  if (loading) {
    return (
      <div className="vc-detail-panel vc-detail-empty">
        <div className="vc-detail-empty-title">Loading VC JSON</div>
        <div className="vc-detail-empty-text">
          Fetching the full credential payload for {cid}.
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="vc-detail-panel vc-detail-empty">
        <div className="vc-detail-header">
          <div>
            <div className="vc-detail-label">Selected VC</div>
            <div className="vc-detail-cid">{cid}</div>
          </div>
          <div className="vc-detail-actions">
            <button className="btn btn-secondary vc-detail-btn" type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div className="vc-detail-empty-title">VC JSON unavailable</div>
        <div className="vc-detail-empty-text">{error}</div>
      </div>
    );
  }

  return null;
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function AuditAgent() {
  const [cid,            setCid]            = useState("");
  const [reportId,       setReportId]       = useState(null);
  const [record,         setRecord]         = useState(null);
  const [isSwitchingReport, setIsSwitchingReport] = useState(false);
  const [reports,        setReports]        = useState([]);
  const [submitError,    setSubmitError]    = useState(null);
  const [submitting,     setSubmitting]     = useState(false);
  const [graphPayload,   setGraphPayload]   = useState(null);
  const [graphLoading,   setGraphLoading]   = useState(false);
  const [graphError,     setGraphError]     = useState(null);
  const [isDemo,         setIsDemo]         = useState(false);
  const [demoKey,        setDemoKey]        = useState("A");      // "A" | "B" | "C"
  const [activeTab,      setActiveTab]      = useState("workspace");
  const [selectedVcCid,  setSelectedVcCid]  = useState(null);
  const [vcDetailCache,  setVcDetailCache]  = useState({});
  const [vcDetailLoading, setVcDetailLoading] = useState(false);
  const [vcDetailError,  setVcDetailError]  = useState(null);
  const pollRef = useRef(null);
  const graphRequestRef = useRef(null);
  const reportsRequestRef = useRef(false);
  const terminalRefreshRef = useRef(null);
  const vcRequestRef = useRef(null);

  const loadReports = useCallback(async () => {
    if (reportsRequestRef.current) return;
    reportsRequestRef.current = true;
    try {
      const res = await fetch("/api/reports");
      if (!res.ok) return;
      const data = await res.json();
      setReports(Array.isArray(data.reports) ? data.reports : []);
    } catch { /* ignore */ }
    finally {
      reportsRequestRef.current = false;
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const poll = useCallback(async (id) => {
    try {
      const res  = await fetch(`/api/report/${id}`);
      if (!res.ok) return;
      const data = await res.json();
      setRecord(data);
      setIsSwitchingReport(false);
      if (data.status === "done" || data.status === "error") {
        const refreshKey = `${id}:${data.status}`;
        stopPolling();
        if (terminalRefreshRef.current !== refreshKey) {
          terminalRefreshRef.current = refreshKey;
          loadReports();
        }
      }
    } catch {
      setIsSwitchingReport(false);
      /* keep polling */
    }
  }, [loadReports, stopPolling]);

  useEffect(() => { loadReports(); }, [loadReports]);

  useEffect(() => {
    if (!reportId || isDemo) return;
    stopPolling();
    poll(reportId);
    pollRef.current = setInterval(() => poll(reportId), POLL_INTERVAL_MS);
    return stopPolling;
  }, [reportId, poll, stopPolling, isDemo]);

  async function handleRun(e) {
    e.preventDefault();
    const trimmed = cid.trim();
    if (!trimmed) return;
    setIsDemo(false);
    setIsSwitchingReport(false);
    setSelectedVcCid(null);
    setVcDetailCache({});
    setVcDetailLoading(false);
    setVcDetailError(null);
    setActiveTab("workspace");
    setSubmitError(null);
    setSubmitting(true);
    setRecord(null);
    setReportId(null);
    setGraphPayload(null);
    graphRequestRef.current = null;
    terminalRefreshRef.current = null;
    stopPolling();
    try {
      const res  = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rootCid: trimmed }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to start audit");
      setReportId(data.reportId);
      setCid("");
      loadReports();
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  function handleLoadDemo(key) {
    stopPolling();
    const k = key ?? demoKey;
    setIsDemo(true);
    setIsSwitchingReport(false);
    setDemoKey(k);
    setRecord(DEMOS[k]);
    setReportId(DEMOS[k].reportId);
    setSelectedVcCid(null);
    setVcDetailCache({});
    setVcDetailLoading(false);
    setVcDetailError(null);
    setActiveTab("workspace");
    setGraphPayload(null);
    graphRequestRef.current = null;
    terminalRefreshRef.current = null;
    setSubmitError(null);
  }

  function handleSwitchDemo(key) {
    setIsSwitchingReport(false);
    setDemoKey(key);
    setRecord(DEMOS[key]);
    setReportId(DEMOS[key].reportId);
    setSelectedVcCid(null);
    setVcDetailCache({});
    setVcDetailLoading(false);
    setVcDetailError(null);
    graphRequestRef.current = null;
    terminalRefreshRef.current = null;
  }

  async function handleOpenReport(id) {
    stopPolling();
    setIsDemo(false);
    setIsSwitchingReport(true);
    setSelectedVcCid(null);
    setVcDetailCache({});
    setVcDetailLoading(false);
    setVcDetailError(null);
    setReportId(id);
    setRecord(null);
    setGraphPayload(null);
    setGraphError(null);
    graphRequestRef.current = null;
    terminalRefreshRef.current = null;
    await poll(id);
  }

  async function loadGraph(rootCid) {
    if (!rootCid) return;
    if (graphRequestRef.current === rootCid) return;
    graphRequestRef.current = rootCid;
    setGraphLoading(true); setGraphError(null);
    try {
      const res  = await fetch("/api/graph", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rootCid }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to build graph");
      setGraphPayload(data);
    } catch (err) {
      graphRequestRef.current = null;
      setGraphError(err.message); setGraphPayload(null);
    } finally {
      setGraphLoading(false);
    }
  }


  const isRunning      = (record?.status === "running" || submitting) && !isDemo;
  const isDone         = record?.status === "done";
  const isError        = record?.status === "error";
  const topbarState    = overallTopbarState(record);
  const overallSuccess = isDone && topbarState === "pass";
  const bundle         = record?.result?.result_bundle ?? {};
  const domainStatus   = record?.result?.result_bundle?.domainStatus ?? {};
  const domainResults  = bundle?.domainResults ?? {};
  const domainSummaries = bundle?.domainSummaries ?? {};
  const vcsByCid       = bundle?.vcsByCid ?? graphPayload?.vcsByCid ?? {};
  const selectedVc     = selectedVcCid
    ? vcDetailCache?.[selectedVcCid]?.vc ?? vcsByCid?.[selectedVcCid] ?? null
    : null;

  useEffect(() => {
    if (isDemo || !record?.rootCid) return;

    const storedGraph = record?.result?.result_bundle?.graph;
    const storedVcsByCid = record?.result?.result_bundle?.vcsByCid;
    if (
      record?.status === "done" &&
      storedGraph &&
      Array.isArray(storedGraph?.nodes) &&
      Array.isArray(storedGraph?.edges) &&
      storedVcsByCid &&
      typeof storedVcsByCid === "object"
    ) {
      graphRequestRef.current = record.rootCid;
      setGraphPayload({
        ...graphPayloadFromStoredGraph(record.rootCid, storedGraph),
        vcsByCid: storedVcsByCid,
      });
      setGraphLoading(false);
      setGraphError(null);
      return;
    }

    if (record?.status === "done" || record?.status === "running") {
      if (graphPayload?.view?.rootCid === record.rootCid) {
        graphRequestRef.current = record.rootCid;
        return;
      }
      loadGraph(record.rootCid);
    }
  }, [record, isDemo, graphPayload]);

  useEffect(() => {
    if (!selectedVcCid) {
      setVcDetailLoading(false);
      setVcDetailError(null);
      vcRequestRef.current = null;
      return;
    }

    const bundledVc = vcsByCid?.[selectedVcCid];
    if (bundledVc) {
      setVcDetailCache((prev) => (
        prev[selectedVcCid]?.vc === bundledVc
          ? prev
          : { ...prev, [selectedVcCid]: { vc: bundledVc, source: "report_bundle" } }
      ));
      setVcDetailLoading(false);
      setVcDetailError(null);
      vcRequestRef.current = null;
      return;
    }

    if (!record || isDemo) return;
    if (vcDetailCache[selectedVcCid]?.vc) {
      setVcDetailLoading(false);
      setVcDetailError(null);
      vcRequestRef.current = null;
      return;
    }
    if (vcRequestRef.current === selectedVcCid) return;

    let cancelled = false;
    vcRequestRef.current = selectedVcCid;
    setVcDetailLoading(true);
    setVcDetailError(null);

    fetch("/api/vc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cid: selectedVcCid, reportId }),
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to fetch VC JSON");
        return data;
      })
      .then((data) => {
        if (cancelled) return;
        setVcDetailCache((prev) => ({
          ...prev,
          [selectedVcCid]: { vc: data.vc, source: data.source ?? "unknown" },
        }));
        setVcDetailError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setVcDetailError(err.message);
      })
      .finally(() => {
        if (cancelled) return;
        setVcDetailLoading(false);
        vcRequestRef.current = null;
      });

    return () => {
      cancelled = true;
    };
  }, [selectedVcCid, vcsByCid, record, isDemo, reportId, vcDetailCache]);

  const technicalChecks = deriveTechnicalChecks(record);

  return (
    <>
      {/* ── Top bar ── */}
      <nav className="topbar">
        <div className="topbar-brand">
          <div className="topbar-brand-icon">SA</div>
          Supply Chain Audit Agent
        </div>
        <div className="topbar-divider" />
        <div className="topbar-nav">
          <button
            className={`topbar-nav-item ${activeTab === "workspace" ? "active" : ""}`}
            type="button"
            onClick={() => setActiveTab("workspace")}
          >
            Audit Workspace
          </button>
          <button
            className={`topbar-nav-item ${activeTab === "vc-info" ? "active" : ""}`}
            type="button"
            onClick={() => setActiveTab("vc-info")}
          >
            VC Info
          </button>
        </div>
        <div className="topbar-right">
          {topbarState && (
            <span className={`topbar-badge ${topbarState}`}>
              {topbarState === "pass" ? "Compliant" : topbarState === "fail" ? "Non-Compliant" : topbarState === "uncertain" ? "Review Required" : topbarState === "running" ? "Running" : topbarState}
            </span>
          )}
        </div>
      </nav>

      {/* ── Page ── */}
      <div className="page">
        {/* ── Sidebar ── */}
        <aside className="sidebar">
          <div className="panel">
            <div className="panel-heading">New Audit</div>
            <form className="cid-form" onSubmit={handleRun}>
              <label className="field-label" htmlFor="rootCid">Root VC CID</label>
              <input
                id="rootCid"
                className="cid-input"
                type="text"
                placeholder="Qm… or bafy…"
                value={cid}
                onChange={(e) => setCid(e.target.value)}
                disabled={isRunning}
                spellCheck={false}
                autoComplete="off"
              />
              <button className="btn btn-primary" type="submit" disabled={isRunning || !cid.trim()}>
                {isRunning ? "Running…" : "Run Audit"}
              </button>
              <button className="btn btn-demo" type="button" onClick={() => handleLoadDemo("A")} disabled={isRunning}>
                Load demo preview
              </button>
            </form>
            {submitError && <div className="error-text" style={{ marginTop: 8 }}>{submitError}</div>}
          </div>

          <div className="panel">
            <div className="panel-heading">Recent Reports</div>
            <div className="report-list">
              {isDemo && (
                <>
                  <button type="button" className={`report-row ${demoKey === "A" ? "active" : ""}`} onClick={() => handleLoadDemo("A")}>
                    <span className="report-row-cid">{DEMO_A.result.entity}</span>
                    <span className="mini-state demo">Demo A</span>
                  </button>
                  <button type="button" className={`report-row ${demoKey === "B" ? "active" : ""}`} onClick={() => handleLoadDemo("B")}>
                    <span className="report-row-cid">{DEMO_B.result.entity}</span>
                    <span className="mini-state" style={{ background: "#fee2e2", color: "#b91c1c" }}>Demo B</span>
                  </button>
                  <button type="button" className={`report-row ${demoKey === "C" ? "active" : ""}`} onClick={() => handleLoadDemo("C")}>
                    <span className="report-row-cid">{DEMO_C.result.entity}</span>
                    <span className="mini-state" style={{ background: "#fef3c7", color: "#92400e" }}>Demo C</span>
                  </button>
                </>
              )}
              {reports.length === 0 && !isDemo
                ? <div className="report-empty">No reports yet.</div>
                : reports.slice(0, 8).map((item) => (
                    <button key={item.reportId} type="button" className="report-row" onClick={() => handleOpenReport(item.reportId)}>
                      <span className="report-row-cid">{item.rootCid}</span>
                      <span className={`mini-state ${item.status}`}>{item.status}</span>
                    </button>
                  ))
              }
            </div>
          </div>
        </aside>

        {/* ── Main content ── */}
        <main className="main-content">
          {/* Empty state */}
          {!record && !submitting && !isSwitchingReport && (
            <div className="panel" style={{ textAlign: "center", padding: "48px 24px" }}>
              <div style={{ fontSize: "2rem", marginBottom: 12 }}>🔍</div>
              <div className="content-heading" style={{ marginBottom: 8 }}>No audit selected</div>
              <div style={{ color: "var(--muted)", fontSize: "0.85rem", maxWidth: 380, margin: "0 auto 24px" }}>
                Enter a root VC CID to run a live audit, or load a demo to explore the full report layout.
              </div>
              <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
                <button className="btn btn-demo" style={{ width: "auto" }} onClick={() => handleLoadDemo("A")}>
                  Demo A — Mostly passing (ACME Components)
                </button>
                <button className="btn btn-demo" style={{ width: "auto" }} onClick={() => handleLoadDemo("B")}>
                  Demo B — Multiple failures (Balkan Parts)
                </button>
                <button className="btn btn-demo" style={{ width: "auto" }} onClick={() => handleLoadDemo("C")}>
                  Demo C — Review required (Northstar Cathodes)
                </button>
              </div>
            </div>
          )}

          {!record && isSwitchingReport && (
            <div className="panel" style={{ textAlign: "center", padding: "48px 24px" }}>
              <div style={{ fontSize: "1.9rem", marginBottom: 12 }}>⏳</div>
              <div className="content-heading" style={{ marginBottom: 8 }}>Loading selected report…</div>
              <div style={{ color: "var(--muted)", fontSize: "0.85rem", maxWidth: 420, margin: "0 auto" }}>
                Previous report view was cleared. The selected report data will appear as soon as it is fetched.
              </div>
            </div>
          )}

          {/* Demo banner with switcher */}
          {isDemo && (
            <div className="demo-banner">
              <div className="demo-switcher">
                <span className="demo-switcher-label">Demo:</span>
                <button className={`demo-switch-btn ${demoKey === "A" ? "active" : ""}`} onClick={() => handleSwitchDemo("A")}>
                  A — Compliant
                </button>
                <button className={`demo-switch-btn ${demoKey === "B" ? "active" : ""}`} onClick={() => handleSwitchDemo("B")}>
                  B — Non-Compliant
                </button>
                <button className={`demo-switch-btn ${demoKey === "C" ? "active" : ""}`} onClick={() => handleSwitchDemo("C")}>
                  C — Review Required
                </button>
              </div>
              <span style={{ fontSize: "0.78rem", color: "#92400e" }}>
                {demoKey === "A"
                  ? "ACME Components GmbH — 2 minor observations"
                  : demoKey === "B"
                    ? "Balkan Parts d.o.o. — multiple critical failures"
                    : "Northstar Cathodes Sp. z o.o. — targeted governance review with limited follow-up actions"}
              </span>
              <button
                className="btn btn-secondary"
                style={{ padding: "4px 12px", fontSize: "0.75rem" }}
                onClick={() => { setRecord(null); setIsDemo(false); setSelectedVcCid(null); setActiveTab("workspace"); }}
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Status banner (live audits only) */}
          {record && !isDemo && (
            <div className={`status-banner ${record.status} ${isDone ? (overallSuccess ? "success" : "fail") : ""}`}>
              {isRunning && <span className="spinner" />}
              <span>
                {record.status === "running" && `Auditing ${record.rootCid}…`}
                {isDone && (overallSuccess ? "Audit complete — all checks passed." : "Audit complete — issues were found.")}
                {isError && `Error: ${record.error}`}
              </span>
            </div>
          )}

          {/* ── Management Summary ── */}
          {activeTab === "workspace" && record && (isDone || isDemo) && (
            <ManagementSummary record={record} isDemo={isDemo} reportId={reportId} />
          )}

          {activeTab === "workspace" && record && (isDone || isDemo) && (
            <DomainSummariesSection
              domainSummaries={domainSummaries}
              domainStatus={domainStatus}
              domainResults={domainResults}
              technicalChecks={technicalChecks}
            />
          )}

          {activeTab === "vc-info" && (
            <div className="panel">
              <div className="vc-info-header">
                <div>
                  <div className="section-heading" style={{ marginBottom: 6 }}>VC Info</div>
                  <div className="vc-info-subtitle">
                    Click a CID in the provenance graph to inspect the complete VC JSON.
                  </div>
                </div>
              </div>

              {!record && (
                <div className="graph-note">No audit selected yet.</div>
              )}

              {record && isDemo && (
                <div className="graph-note">VC Info is currently available for live reports.</div>
              )}

              {record && !isDemo && (
                <>
                  <ProvenanceGraphPanel
                    graphPayload={graphPayload}
                    loading={graphLoading}
                    error={graphError}
                    selectedCid={selectedVcCid}
                    onNodeSelect={(nextCid) => setSelectedVcCid(nextCid)}
                  />
                  {!graphLoading && !graphError && (
                    <>
                      {selectedVcCid && (vcDetailLoading || vcDetailError) ? (
                        <VCDetailStatus
                          cid={selectedVcCid}
                          loading={vcDetailLoading}
                          error={vcDetailError}
                          onClose={() => setSelectedVcCid(null)}
                        />
                      ) : (
                        <VCDetailDrawer
                          cid={selectedVcCid}
                          vc={selectedVc}
                          onClose={() => setSelectedVcCid(null)}
                        />
                      )}
                    </>
                  )}
                </>
              )}
            </div>
          )}
        </main>
      </div>
    </>
  );
}
