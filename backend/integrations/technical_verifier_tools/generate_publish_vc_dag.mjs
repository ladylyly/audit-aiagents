import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { Wallet, TypedDataEncoder } from "ethers";

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

// ── Wallet registry (populated in main()) ───────────────────────────────────
// issuerKey / holderKey in CHUNK_SPECS:
//   0–14  → ephemeral wallets Eph1..Eph15  (generated at runtime)
//   "deployer" → DEPLOYER_PRIVATE_KEY from .env
//   "issuer"   → ISSUER_PRIVATE_KEY   from .env
const WALLETS = {
  eph: [],
  deployer: null,
  issuer: null,
};

const COMPANY_NAMES = {
  0:  "SQM Chile Lithium S.A.",
  1:  "Kokkola Lithium Oy",
  2:  "Western Areas Nickel Ltd",
  3:  "Harjavalta Nickel Oy",
  4:  "Cobalt Blue Holdings AU",
  5:  "Freeport Cobalt Oy",
  6:  "Mason Graphite Canada Inc",
  7:  "RWI Tantalum Rwanda",
  8:  "Taniobis GmbH",
  9:  "EPCOS Capacitors GmbH",
  10: "Umicore Battery Materials Oy",
  11: "Nouveau Monde Anode Inc",
  12: "Sumitomo Electric Separator",
  13: "Solvay Electrolyte DE GmbH",
  14: "ACC Cell GmbH",
  deployer: "VARTA Battery Pack GmbH",
  issuer:   "BMWi Battery OEM GmbH",
};

function getWallet(key) {
  if (key === "deployer") return WALLETS.deployer;
  if (key === "issuer")   return WALLETS.issuer;
  return WALLETS.eph[key];
}

function getCompanyName(key) {
  return COMPANY_NAMES[key] ?? String(key);
}

// ── 25-node best-case supply chain ───────────────────────────────────────────
//
// Governance invariant: for every (parent → child) edge,
//   parent.issuerKey === child.holderKey  (wallet addresses must match)
//
// Dependencies are resolved bottom-up (leaves first).
// Node 24 is the ROOT.
const CHUNK_SPECS = [
  // ── [0] LITHIUM BRINE EXTRACTION ─────────────────────────────────────────
  {
    chunkName: "Lithium brine extraction",
    issuerKey: 0, holderKey: 0,          // Eph1 self-holds leaf
    facilityRole: "mine",
    materialTags: ["lithium"],
    operationTags: ["upstream", "extraction"],
    certifications: [
      { name: "IRMA",      issuer: "IRMA", certificateCid: "bafy-cert-li-mine-irma",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO",  certificateCid: "bafy-cert-li-mine-iso14001",  validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "IRMA", cid: "bafy-cert-li-mine-irma" },
    country: "Chile", countryCode: "CL", latitude: -22.9, longitude: -68.2,
    energySource: "solar",
    emissionsClaim: "Atacama solar-powered extraction, scope-1 monitored",
    climateClaim: "Net-zero extraction target 2030",
    csdddClaims: { due_diligence_policy_exists: true, code_of_conduct_exists: true },
    dependencies: [],
  },

  // ── [1] LITHIUM CARBONATE PROCESSING ──────────────────────────────────────
  {
    chunkName: "Lithium carbonate processing",
    issuerKey: 0, holderKey: 1,          // Eph1 issues → Eph2 holds (LiOH refinery takes input)
    facilityRole: "processor",
    materialTags: ["lithium"],
    operationTags: ["upstream", "processing"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-li-carb-rmap",    validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-li-carb-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-li-carb-rmap" },
    country: "Chile", countryCode: "CL", latitude: -23.1, longitude: -68.0,
    energySource: "solar",
    emissionsClaim: "Battery-grade Li2CO3, scope-2 tracking active",
    climateClaim: null,
    csdddClaims: { impact_identification_process: true, supply_chain_mapping_completed: true },
    dependencies: [0],
  },

  // ── [2] LITHIUM HYDROXIDE REFINERY ────────────────────────────────────────
  {
    chunkName: "Lithium hydroxide refinery",
    issuerKey: 1, holderKey: 10,         // Eph2 issues → Eph11 holds (cathode company takes LiOH)
    facilityRole: "refiner",
    materialTags: ["lithium"],
    operationTags: ["midstream", "refining"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-li-ref-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-li-ref-iso14001",  validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-li-ref-rmap" },
    country: "Finland", countryCode: "FI", latitude: 60.4, longitude: 25.0,
    energySource: "hydro",
    emissionsClaim: "Nordic hydropower, scope-1 verified",
    climateClaim: "SBTi-aligned target",
    csdddClaims: { prevention_action_plan: true, contractual_assurances_obtained: true },
    dependencies: [1],
  },

  // ── [3] NICKEL MINE ───────────────────────────────────────────────────────
  {
    chunkName: "Nickel mine",
    issuerKey: 2, holderKey: 3,          // Eph3 issues → Eph4 holds (Ni refinery takes ore)
    facilityRole: "mine",
    materialTags: ["nickel"],
    operationTags: ["upstream", "extraction"],
    certifications: [
      { name: "IRMA",            issuer: "IRMA",            certificateCid: "bafy-cert-ni-mine-irma",      validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "The Nickel Mark", issuer: "Nickel Institute", certificateCid: "bafy-cert-ni-mine-nickmark",  validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001",       issuer: "ISO",             certificateCid: "bafy-cert-ni-mine-iso14001",  validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "IRMA", cid: "bafy-cert-ni-mine-irma" },
    country: "Australia", countryCode: "AU", latitude: -31.5, longitude: 121.8,
    energySource: "solar",
    emissionsClaim: "WA solar-hybrid mine, scope-1+2 disclosed",
    climateClaim: "Paris-aligned mine decarbonisation roadmap",
    csdddClaims: { remediation_process: true, complaint_channel_exists: true },
    dependencies: [],
  },

  // ── [4] NICKEL SULFATE REFINERY ───────────────────────────────────────────
  {
    chunkName: "Nickel sulfate refinery",
    issuerKey: 3, holderKey: 10,         // Eph4 issues → Eph11 holds (cathode company takes NiSO4)
    facilityRole: "refiner",
    materialTags: ["nickel"],
    operationTags: ["midstream", "refining"],
    certifications: [
      { name: "RMAP",            issuer: "RMI",            certificateCid: "bafy-cert-ni-ref-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001",       issuer: "ISO",            certificateCid: "bafy-cert-ni-ref-iso14001",  validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-ni-ref-rmap" },
    country: "Finland", countryCode: "FI", latitude: 60.5, longitude: 25.3,
    energySource: "hydro",
    emissionsClaim: "Nordic grid, <50g CO2/kWh",
    climateClaim: "Net-zero refinery 2035",
    csdddClaims: { monitoring_frequency_months: 12, public_due_diligence_statement: true },
    dependencies: [3],
  },

  // ── [5] COBALT MINE ───────────────────────────────────────────────────────
  {
    chunkName: "Cobalt mine",
    issuerKey: 4, holderKey: 5,          // Eph5 issues → Eph6 holds (Co refinery takes ore)
    facilityRole: "mine",
    materialTags: ["cobalt"],
    operationTags: ["upstream", "extraction", "social_risk_heavy"],
    certifications: [
      { name: "IRMA",      issuer: "IRMA", certificateCid: "bafy-cert-co-mine-irma",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "SA8000",    issuer: "SAI",  certificateCid: "bafy-cert-co-mine-sa8000",   validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO",  certificateCid: "bafy-cert-co-mine-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "IRMA", cid: "bafy-cert-co-mine-irma" },
    country: "Australia", countryCode: "AU", latitude: -28.4, longitude: 120.5,
    energySource: "renewable",
    emissionsClaim: "Renewable-powered cobalt extraction, zero PFAS",
    climateClaim: "Scope-3 mapping in progress",
    csdddClaims: { due_diligence_policy_exists: true, code_of_conduct_exists: true },
    dependencies: [],
  },

  // ── [6] COBALT SULFATE REFINERY ───────────────────────────────────────────
  {
    chunkName: "Cobalt sulfate refinery",
    issuerKey: 5, holderKey: 10,         // Eph6 issues → Eph11 holds (cathode company takes CoSO4)
    facilityRole: "refiner",
    materialTags: ["cobalt"],
    operationTags: ["midstream", "refining"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-co-ref-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-co-ref-iso14001",  validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-co-ref-rmap" },
    country: "Finland", countryCode: "FI", latitude: 60.2, longitude: 24.7,
    energySource: "hydro",
    emissionsClaim: "Nordic refinery, <30g CO2/kWh",
    climateClaim: "SBTi-aligned refinery operations",
    csdddClaims: { impact_identification_process: true, supply_chain_mapping_completed: true },
    dependencies: [5],
  },

  // ── [7] NATURAL GRAPHITE MINING ───────────────────────────────────────────
  {
    chunkName: "Natural graphite mining",
    issuerKey: 6, holderKey: 6,          // Eph7 self-holds leaf (mine → processing is same company)
    facilityRole: "mine",
    materialTags: ["graphite"],
    operationTags: ["upstream", "extraction"],
    certifications: [
      { name: "IRMA",      issuer: "IRMA", certificateCid: "bafy-cert-gr-mine-irma",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO",  certificateCid: "bafy-cert-gr-mine-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "IRMA", cid: "bafy-cert-gr-mine-irma" },
    country: "Canada", countryCode: "CA", latitude: 46.5, longitude: -75.5,
    energySource: "hydro",
    emissionsClaim: "Quebec hydro grid, monitored extraction",
    climateClaim: "Carbon-neutral mine cert in progress",
    csdddClaims: { prevention_action_plan: true, contractual_assurances_obtained: true },
    dependencies: [],
  },

  // ── [8] GRAPHITE ANODE PROCESSING ─────────────────────────────────────────
  {
    chunkName: "Graphite anode processing",
    issuerKey: 6, holderKey: 11,         // Eph7 issues → Eph12 holds (anode company takes graphite)
    facilityRole: "processor",
    materialTags: ["graphite"],
    operationTags: ["midstream", "processing"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-gr-proc-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-gr-proc-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-gr-proc-rmap" },
    country: "Canada", countryCode: "CA", latitude: 46.8, longitude: -71.2,
    energySource: "hydro",
    emissionsClaim: "Spherical graphite, scope-2 <20g CO2/kWh",
    climateClaim: "ISO 14064 certified",
    csdddClaims: { remediation_process: true, complaint_channel_exists: true },
    dependencies: [7],
  },

  // ── [9] TANTALUM MINE — 3TG SUBCHAIN START ────────────────────────────────
  {
    chunkName: "Tantalum mine",
    issuerKey: 7, holderKey: 8,          // Eph8 issues → Eph9 holds (smelter takes ore)
    facilityRole: "mine",
    materialTags: ["tantalum"],
    operationTags: ["upstream", "extraction", "social_risk_heavy"],
    certifications: [
      { name: "IRMA",      issuer: "IRMA", certificateCid: "bafy-cert-ta-mine-irma",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "SA8000",    issuer: "SAI",  certificateCid: "bafy-cert-ta-mine-sa8000",   validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO",  certificateCid: "bafy-cert-ta-mine-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "IRMA", cid: "bafy-cert-ta-mine-irma" },
    country: "Rwanda", countryCode: "RW", latitude: -1.9, longitude: 29.9,
    energySource: "hydro",
    emissionsClaim: "ITRI-RMAP audited mine, scope-1 monitored",
    climateClaim: "Scope-1 tracking active",
    csdddClaims: { monitoring_frequency_months: 12, public_due_diligence_statement: true },
    conflictMineralsClaims: {
      origin_country: "RW",
      third_party_audit_exists: true,
      audit_scope_complete: true,
      audit_independence_confirmed: true,
      traceability_system_exists: true,
      chain_of_custody_records: true,
      risk_assessment_exists: true,
    },
    dependencies: [],
  },

  // ── [10] TANTALUM SMELTER — EU CONFLICT MINERALS IMPORTER ────────────────
  {
    chunkName: "Tantalum smelter",
    issuerKey: 8, holderKey: 9,          // Eph9 issues → Eph10 holds (capacitor mfr takes metal)
    facilityRole: "refiner",
    materialTags: ["tantalum"],
    operationTags: ["midstream", "refining"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-ta-smelt-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-ta-smelt-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-ta-smelt-rmap" },
    country: "Germany", countryCode: "DE", latitude: 51.2, longitude: 6.8,
    energySource: "renewable",
    emissionsClaim: "Green-certified smelter, scope-1+2 verified",
    climateClaim: "ETS-compliant operations",
    csdddClaims: { due_diligence_policy_exists: true, code_of_conduct_exists: true },
    // Primary conflict minerals evidence node — full Art 4/5/6/7 obligations
    conflictMineralsClaims: {
      union_importer: true,
      material_type: "tantalum",
      cn_code: "8103 20 00",
      annex_i_threshold_exceeded: true,
      material_form: "metal",
      recycled_metals: false,
      pre_2013_stock_verified: false,
      by_product: false,
      by_product_origin_documented: false,
      compliance_documentation_exists: true,
      recognised_scheme_used: true,
      supply_chain_policy_exists: true,
      oecd_annex_ii_alignment: true,
      senior_management_responsibility_assigned: true,
      record_retention_years: 5,
      supplier_contract_policy_flowdown: true,
      grievance_mechanism_exists: true,
      smelter_refiner_identified: true,
      origin_country: "RW",
      third_party_audit_exists: true,
      risk_assessment_exists: true,
      risk_assessment_reported_to_senior_management: true,
      risk_response_strategy_defined: true,
      risk_management_plan_exists: true,
      risk_mitigation_tracking: true,
      additional_risk_assessments: true,
      stakeholder_consultation_for_mitigation: true,
      oecd_annex_iii_measures_used: true,
      audit_scope_complete: true,
      audit_conformity_objective: true,
      audit_recommendations_provided: true,
      audit_independence_confirmed: true,
      substantive_evidence_of_smelter_refiner_compliance: true,
      audit_reports_shared_with_authorities: true,
      information_shared_with_downstream_purchasers: true,
      public_disclosure_exists: true,
      recycled_source_conclusion_disclosed: true,
      traceability_system_exists: true,
      chain_of_custody_records: true,
    },
    dependencies: [9],
  },

  // ── [11] TANTALUM CAPACITOR MANUFACTURER ─────────────────────────────────
  {
    chunkName: "Tantalum capacitor manufacturer",
    issuerKey: 9, holderKey: 14,         // Eph10 issues → Eph15 holds (cell mfr takes capacitor)
    facilityRole: "manufacturer",
    materialTags: ["tantalum", "battery_component"],
    operationTags: ["downstream", "battery_component"],
    certifications: [
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-ta-cap-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "ISO 14001", cid: "bafy-cert-ta-cap-iso14001" },
    country: "Germany", countryCode: "DE", latitude: 51.3, longitude: 12.4,
    energySource: "renewable",
    emissionsClaim: "German green tariff, scope-2 <50g CO2/kWh",
    climateClaim: "ISO 50001 energy management",
    csdddClaims: { due_diligence_policy_exists: true, code_of_conduct_exists: true },
    dependencies: [10],
  },

  // ── [12] CATHODE PRECURSOR pCAM ───────────────────────────────────────────
  {
    chunkName: "Cathode precursor pCAM",
    issuerKey: 10, holderKey: 10,        // Eph11 self-holds (pCAM → CAM is internal step)
    facilityRole: "processor",
    materialTags: ["battery_precursor"],
    operationTags: ["midstream", "processing"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-pcam-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-pcam-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-pcam-rmap" },
    country: "Finland", countryCode: "FI", latitude: 60.6, longitude: 27.2,
    energySource: "hydro",
    emissionsClaim: "Precursor hydromet processing, Nordic grid",
    climateClaim: "Scope-1+2+3 measured",
    csdddClaims: { impact_identification_process: true, supply_chain_mapping_completed: true },
    dependencies: [2, 4, 6],
  },

  // ── [13] CATHODE ACTIVE MATERIAL CAM ─────────────────────────────────────
  {
    chunkName: "Cathode active material CAM",
    issuerKey: 10, holderKey: 14,        // Eph11 issues → Eph15 holds (cell mfr takes CAM)
    facilityRole: "processor",
    materialTags: ["battery_cathode"],
    operationTags: ["midstream", "processing"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-cam-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-cam-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-cam-rmap" },
    country: "Finland", countryCode: "FI", latitude: 60.7, longitude: 27.5,
    energySource: "hydro",
    emissionsClaim: "NMC811 cathode sintering, renewable grid",
    climateClaim: "Carbon footprint per kWh disclosed",
    csdddClaims: { prevention_action_plan: true, contractual_assurances_obtained: true },
    dependencies: [12],
  },

  // ── [14] ANODE ACTIVE MATERIAL AAM ────────────────────────────────────────
  {
    chunkName: "Anode active material AAM",
    issuerKey: 11, holderKey: 14,        // Eph12 issues → Eph15 holds (cell mfr takes AAM)
    facilityRole: "processor",
    materialTags: ["battery_anode"],
    operationTags: ["midstream", "processing"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-aam-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-aam-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-aam-rmap" },
    country: "Canada", countryCode: "CA", latitude: 47.0, longitude: -71.0,
    energySource: "hydro",
    emissionsClaim: "Spherical graphite anode coating, Quebec grid",
    climateClaim: "LCA-disclosed per kWh",
    csdddClaims: { remediation_process: true, complaint_channel_exists: true },
    dependencies: [8],
  },

  // ── [15] SEPARATOR FILM SUPPLIER (leaf) ───────────────────────────────────
  {
    chunkName: "Separator film supplier",
    issuerKey: 12, holderKey: 14,        // Eph13 issues → Eph15 holds (cell mfr takes separator)
    facilityRole: "processor",
    materialTags: ["battery_component"],
    operationTags: ["midstream", "processing"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-sep-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-sep-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-sep-rmap" },
    country: "Japan", countryCode: "JP", latitude: 34.7, longitude: 135.5,
    energySource: "renewable",
    emissionsClaim: "Ceramic-coated separator, scope-2 tracked",
    climateClaim: "J-Credit participating",
    csdddClaims: { monitoring_frequency_months: 12, public_due_diligence_statement: true },
    dependencies: [],
  },

  // ── [16] CELL ELECTROLYTE AND LiPF6 SALT (leaf) ──────────────────────────
  {
    chunkName: "Cell electrolyte and LiPF6 salt",
    issuerKey: 13, holderKey: 14,        // Eph14 issues → Eph15 holds (cell mfr takes electrolyte)
    facilityRole: "processor",
    materialTags: ["battery_component", "electrolyte"],
    operationTags: ["midstream", "processing"],
    certifications: [
      { name: "RMAP",      issuer: "RMI", certificateCid: "bafy-cert-elec-rmap",     validFrom: "2025-01-01", validUntil: "2026-12-31" },
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-elec-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "RMAP", cid: "bafy-cert-elec-rmap" },
    country: "Germany", countryCode: "DE", latitude: 50.9, longitude: 6.9,
    energySource: "renewable",
    emissionsClaim: "EU-manufactured electrolyte, REACH-compliant",
    climateClaim: "ETS-covered facility",
    csdddClaims: { due_diligence_policy_exists: true, code_of_conduct_exists: true },
    dependencies: [],
  },

  // ── [17] CELL MANUFACTURING ───────────────────────────────────────────────
  {
    chunkName: "Cell manufacturing",
    issuerKey: 14, holderKey: 14,        // Eph15 self-holds (cell → QA is same company)
    facilityRole: "manufacturer",
    materialTags: ["battery_cell", "lithium_ion"],
    operationTags: ["downstream", "manufacturing"],
    certifications: [
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-cell-mfg-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "ISO 14001", cid: "bafy-cert-cell-mfg-iso14001" },
    country: "Germany", countryCode: "DE", latitude: 52.4, longitude: 13.4,
    energySource: "renewable",
    emissionsClaim: "Gigafactory on renewable PPA, scope-1+2 disclosed",
    climateClaim: "EU Battery Regulation DPP-ready",
    csdddClaims: { impact_identification_process: true, supply_chain_mapping_completed: true },
    dependencies: [13, 14, 11, 15, 16],
  },

  // ── [18] CELL QA AND TESTING ──────────────────────────────────────────────
  {
    chunkName: "Cell QA and testing",
    issuerKey: 14, holderKey: "deployer", // Eph15 issues → Deployer holds (module assembler takes cells)
    facilityRole: "manufacturer",
    materialTags: ["battery_cell"],
    operationTags: ["downstream", "quality_assurance"],
    certifications: [
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-cell-qa-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "ISO 14001", cid: "bafy-cert-cell-qa-iso14001" },
    country: "Germany", countryCode: "DE", latitude: 52.5, longitude: 13.4,
    energySource: "renewable",
    emissionsClaim: "Zero-waste QA facility, scope-2 certified",
    climateClaim: "ISO 14064 third-party verified",
    csdddClaims: { prevention_action_plan: true, contractual_assurances_obtained: true },
    dependencies: [17],
  },

  // ── [19] MODULE ASSEMBLY ──────────────────────────────────────────────────
  {
    chunkName: "Module assembly",
    issuerKey: "deployer", holderKey: "deployer",
    facilityRole: "manufacturer",
    materialTags: ["battery_module"],
    operationTags: ["downstream", "assembly"],
    certifications: [
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-mod-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "ISO 14001", cid: "bafy-cert-mod-iso14001" },
    country: "Germany", countryCode: "DE", latitude: 48.8, longitude: 9.2,
    energySource: "renewable",
    emissionsClaim: "Module assembly on renewable grid, scope-3 partial",
    climateClaim: "Science-based target validated",
    csdddClaims: { remediation_process: true, complaint_channel_exists: true },
    dependencies: [18],
  },

  // ── [20] BMS ELECTRONICS (leaf) ───────────────────────────────────────────
  {
    chunkName: "BMS electronics",
    issuerKey: "deployer", holderKey: "deployer",
    facilityRole: "manufacturer",
    materialTags: ["battery_component", "electronics"],
    operationTags: ["downstream", "manufacturing"],
    certifications: [
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-bms-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "ISO 14001", cid: "bafy-cert-bms-iso14001" },
    country: "Germany", countryCode: "DE", latitude: 48.1, longitude: 11.6,
    energySource: "renewable",
    emissionsClaim: "RoHS+REACH-compliant BMS production",
    climateClaim: "German green energy tariff",
    csdddClaims: { monitoring_frequency_months: 6, public_due_diligence_statement: true },
    dependencies: [],
  },

  // ── [21] PACK ASSEMBLY ────────────────────────────────────────────────────
  {
    chunkName: "Pack assembly",
    issuerKey: "deployer", holderKey: "deployer",
    facilityRole: "manufacturer",
    materialTags: ["battery_pack"],
    operationTags: ["downstream", "assembly"],
    certifications: [
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-pack-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "ISO 14001", cid: "bafy-cert-pack-iso14001" },
    country: "Germany", countryCode: "DE", latitude: 48.2, longitude: 11.7,
    energySource: "renewable",
    emissionsClaim: "Pack-level LCA disclosed per kWh capacity",
    climateClaim: "Net-zero assembly hall 2028",
    csdddClaims: { due_diligence_policy_exists: true, code_of_conduct_exists: true },
    dependencies: [19, 20],
  },

  // ── [22] PACK ESG AUDIT ATTESTATION ──────────────────────────────────────
  {
    chunkName: "Pack ESG audit attestation",
    issuerKey: "deployer", holderKey: "issuer", // Deployer issues → Issuer holds (OEM takes audited pack)
    facilityRole: "manufacturer",
    materialTags: ["battery_pack"],
    operationTags: ["downstream", "quality_assurance", "environmental_system"],
    certifications: [
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-esg-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "ISO 14001", cid: "bafy-cert-esg-iso14001" },
    country: "Germany", countryCode: "DE", latitude: 50.1, longitude: 8.7,
    energySource: "renewable",
    emissionsClaim: "Third-party verified scope-1+2+3",
    climateClaim: "CDP A-list supplier",
    csdddClaims: { impact_identification_process: true, supply_chain_mapping_completed: true, contractual_assurances_obtained: true },
    dependencies: [21],
  },

  // ── [23] VEHICLE OEM INTEGRATION ─────────────────────────────────────────
  {
    chunkName: "Vehicle OEM integration",
    issuerKey: "issuer", holderKey: "issuer",
    facilityRole: "manufacturer",
    materialTags: ["battery_pack", "ev_vehicle"],
    operationTags: ["downstream", "oem_integration"],
    certifications: [
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-oem-int-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "ISO 14001", cid: "bafy-cert-oem-int-iso14001" },
    country: "Germany", countryCode: "DE", latitude: 48.3, longitude: 10.9,
    energySource: "renewable",
    emissionsClaim: "OEM assembly on 100% renewable, scope-1 disclosed",
    climateClaim: "EU Green Deal aligned",
    csdddClaims: { prevention_action_plan: true, remediation_process: true, complaint_channel_exists: true },
    dependencies: [22],
  },

  // ── [24] EU BATTERY PASSPORT — ROOT VC ───────────────────────────────────
  {
    chunkName: "EU battery passport",
    issuerKey: "issuer", holderKey: "issuer",
    facilityRole: "manufacturer",
    materialTags: ["battery_pack", "ev_battery"],
    operationTags: ["downstream", "oem_final"],
    certifications: [
      { name: "ISO 14001", issuer: "ISO", certificateCid: "bafy-cert-root-iso14001", validFrom: "2025-01-01", validUntil: "2026-12-31" },
    ],
    certificateCredential: { name: "ISO 14001", cid: "bafy-cert-root-iso14001" },
    country: "Germany", countryCode: "DE", latitude: 52.5, longitude: 13.4,
    energySource: "renewable",
    emissionsClaim: "Full chain LCA completed",
    climateClaim: "CSRD climate transition plan published",
    // Full CSDDD claim set on root — ensures all rules can be satisfied via root evidence
    csdddClaims: {
      due_diligence_policy_exists: true,
      code_of_conduct_exists: true,
      impact_identification_process: true,
      supply_chain_mapping_completed: true,
      prevention_action_plan: true,
      contractual_assurances_obtained: true,
      remediation_process: true,
      complaint_channel_exists: true,
      monitoring_frequency_months: 12,
      public_due_diligence_statement: true,
      climate_transition_plan_exists: true,
      climate_transition_targets_defined: true,
      climate_transition_actions_defined: true,
      climate_transition_investments_defined: true,
      climate_transition_governance_defined: true,
      climate_transition_review_interval_months: 12,
    },
    isRoot: true,  // triggers company + group block for CSDDD Art 2.1.a applicability
    dependencies: [23],
  },
];

// ── Utility helpers ──────────────────────────────────────────────────────────

function parseEnvFile(filePath) {
  const out = {};
  if (!fs.existsSync(filePath)) return out;
  for (const raw of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx < 0) continue;
    out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
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

function ensure0x(key) {
  if (!key) return key;
  return key.startsWith("0x") ? key : `0x${key}`;
}

// ── VC builder ───────────────────────────────────────────────────────────────

function buildVc({
  idx, childCids,
  issuerDid, issuerName,
  holderDid, holderName,
  productContract, productId,
  zkpProof, nowIso,
}) {
  const vcId = `urn:uuid:real-vc-${Date.now()}-${idx + 1}`;
  const batch = `REAL-BATCH-${String(idx + 1).padStart(3, "0")}`;
  const spec = CHUNK_SPECS[idx];

  // Build claims: CSDDD fields + optional conflict_minerals namespace
  const claims = { ...spec.csdddClaims };
  if (spec.conflictMineralsClaims) {
    claims.conflict_minerals = { ...spec.conflictMineralsClaims };
  }

  const credentialSubject = {
    id: holderDid,
    productName: spec.chunkName,
    batch,
    quantity: 1,
    previousCredential: childCids[0] || "",
    componentCredentials: childCids,
    certificateCredential: spec.certificateCredential,
    certifications: spec.certifications,
    facilityRole: spec.facilityRole,
    materialTags: spec.materialTags,
    operationTags: spec.operationTags,
    location: {
      country: spec.country,
      countryCode: spec.countryCode,
      latitude: spec.latitude,
      longitude: spec.longitude,
    },
    energySource: spec.energySource,
    emissionsClaim: spec.emissionsClaim,
    ...(spec.climateClaim != null && { climateClaim: spec.climateClaim }),
    sellerRailgunAddress: "",
    price: JSON.stringify(zkpProof),
    priceCommitment: zkpProof,
    productId: productId || String(idx + 1),
    productContract,
    chainId: "11155111",
    claims,
  };

  // Root node only: add company + group for CSDDD Art 2.1.a applicability
  if (spec.isRoot) {
    credentialSubject.company = {
      establishment: "eu_member_state",
      avg_employee_count: 5000,
      net_turnover_eur_worldwide: 1200000000,
      net_turnover_eur_union: 900000000,
      is_ultimate_parent: true,
      franchise_royalties_eur: 0,
      franchise_royalties_eur_union: 0,
    };
    credentialSubject.group = {
      avg_employee_count: 12000,
      net_turnover_eur_worldwide: 3500000000,
      net_turnover_eur_union: 2800000000,
    };
  }

  return {
    id: vcId,
    "@context": ["https://www.w3.org/ns/credentials/v2"],
    type: ["VerifiableCredential", "BatteryPassportCredential"],
    schemaVersion: "1.0",
    issuer: { id: issuerDid, name: issuerName },
    holder: { id: holderDid, name: holderName },
    issuanceDate: nowIso,
    credentialSubject,
  };
}

// ── Typed-data payload (the subset that is EIP-712 signed) ──────────────────

function buildTypedPayload(vc) {
  return {
    id: vc.id,
    "@context": vc["@context"],
    type: vc.type,
    schemaVersion: vc.schemaVersion,
    issuer: vc.issuer,
    holder: vc.holder,
    issuanceDate: vc.issuanceDate,
    credentialSubject: {
      id: vc.credentialSubject.id,
      productName: vc.credentialSubject.productName,
      batch: vc.credentialSubject.batch,
      quantity: vc.credentialSubject.quantity,
      previousCredential: vc.credentialSubject.previousCredential,
      componentCredentials: vc.credentialSubject.componentCredentials,
      certificateCredential: vc.credentialSubject.certificateCredential,
      sellerRailgunAddress: vc.credentialSubject.sellerRailgunAddress,
      price: vc.credentialSubject.price,
    },
  };
}

// ── IPFS / Pinata ────────────────────────────────────────────────────────────

async function pinJsonToPinata({ jwt, fileName, data }) {
  const form = new FormData();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  form.append("file", blob, fileName);
  form.append("pinataMetadata", JSON.stringify({ name: fileName }));

  const res = await fetch("https://api.pinata.cloud/pinning/pinFileToIPFS", {
    method: "POST",
    headers: { Authorization: `Bearer ${jwt}` },
    body: form,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Pinata upload failed (${res.status}): ${body}`);
  }

  const json = await res.json();
  if (!json?.IpfsHash) throw new Error(`Pinata response missing IpfsHash: ${JSON.stringify(json)}`);
  return json.IpfsHash;
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const repoRoot = path.resolve(scriptDir, "../../..");

  const env = parseEnvFile(path.join(repoRoot, "backend", ".env"));
  const pinataJwt    = must(env, "PINATA_JWT");
  const deployerKey  = ensure0x(must(env, "DEPLOYER_PRIVATE_KEY"));
  const issuerKey    = ensure0x(must(env, "ISSUER_PRIVATE_KEY"));
  const chainId      = Number(envGet(env, "CHAIN_ID", "11155111"));

  // ── Build wallet pool ──────────────────────────────────────────────────────
  for (let i = 0; i < 15; i++) {
    WALLETS.eph.push(Wallet.createRandom());
  }
  WALLETS.deployer = new Wallet(deployerKey);
  WALLETS.issuer   = new Wallet(issuerKey);

  const runId  = `run_${Date.now()}`;
  const outDir = path.join(repoRoot, "data", "generated", "generated_vc_dag", runId);
  fs.mkdirSync(outDir, { recursive: true });

  // Save ephemeral wallet keys for auditability
  const ephWalletsExport = WALLETS.eph.map((w, i) => ({
    ephIndex: i,
    companyName: COMPANY_NAMES[i],
    address: w.address,
    privateKey: w.privateKey,
  }));
  fs.writeFileSync(
    path.join(outDir, "ephemeral_wallets.json"),
    JSON.stringify(ephWalletsExport, null, 2)
  );
  console.log(`Generated 15 ephemeral wallets → ${path.join(outDir, "ephemeral_wallets.json")}`);
  console.log(`  deployer: ${WALLETS.deployer.address} (${COMPANY_NAMES.deployer})`);
  console.log(`  issuer:   ${WALLETS.issuer.address}   (${COMPANY_NAMES.issuer})`);

  // ── Load product clones ────────────────────────────────────────────────────
  const clonesPath = path.join(repoRoot, "contracts", "deploy_stack", "output", "product_clones.json");
  if (!fs.existsSync(clonesPath)) throw new Error(`Missing clone file: ${clonesPath}`);
  const cloneRows = JSON.parse(fs.readFileSync(clonesPath, "utf8"));
  if (!Array.isArray(cloneRows) || cloneRows.length < 25) {
    throw new Error(`Need at least 25 clone entries, found ${Array.isArray(cloneRows) ? cloneRows.length : 0}`);
  }

  const selected = cloneRows.slice(-25);
  const n = CHUNK_SPECS.length; // 25
  if (selected.length !== n) {
    throw new Error(`Expected ${n} clone rows, selected ${selected.length}`);
  }

  const domain      = { name: "VC", version: "1.0", chainId };
  const cidByIndex  = new Map();
  const records     = [];

  // Staggered issuance dates — node 0 (raw material leaf) is oldest, node 24
  // (EU Battery Passport root) is newest. Each step is 1 day apart, spanning
  // ~25 days total. This reflects real supply chain sequencing: raw materials
  // are extracted first, assemblies are issued last.
  const chainEndDate = new Date();
  const MS_PER_DAY = 24 * 60 * 60 * 1000;

  // ── Generate VCs bottom-up ────────────────────────────────────────────────
  for (let i = 0; i < n; i++) {
    const node = selected[i];
    const spec = CHUNK_SPECS[i];

    // Ensure ISO 14001 is applicable on every node by including environmental_system
    if (!spec.operationTags.includes("environmental_system")) {
      spec.operationTags = [...spec.operationTags, "environmental_system"];
    }

    // Resolve child CIDs (all dependencies must already be built)
    const childCids = spec.dependencies.map((dep) => cidByIndex.get(dep));
    const missing = spec.dependencies.filter((dep) => !cidByIndex.has(dep));
    if (missing.length > 0) {
      throw new Error(`Node ${i} missing child CIDs for deps: [${missing}]`);
    }

    // Resolve wallets
    const issuerWallet = getWallet(spec.issuerKey);
    const holderWallet = getWallet(spec.holderKey);
    if (!issuerWallet) throw new Error(`No wallet for issuerKey=${spec.issuerKey} at node ${i}`);
    if (!holderWallet) throw new Error(`No wallet for holderKey=${spec.holderKey} at node ${i}`);

    const issuerDid  = `did:ethr:${chainId}:${issuerWallet.address.toLowerCase()}`;
    const holderDid  = `did:ethr:${chainId}:${holderWallet.address.toLowerCase()}`;
    const issuerName = getCompanyName(spec.issuerKey);
    const holderName = getCompanyName(spec.holderKey);

    const zkpProof = {
      protocol:   "bulletproofs-pedersen",
      version:    "1.0",
      commitment: ensure0x(node.priceCommitment),
      proof:      "placeholder-proof",
      encoding:   "hex",
      proofType:  "zkRangeProof-v1",
    };

    // Node 0 = oldest (raw material leaf), node n-1 = newest (root assembly).
    // Each node is 1 day earlier than the next: node i is (n-1-i) days before chainEndDate.
    const nowIso = new Date(chainEndDate.getTime() - (n - 1 - i) * MS_PER_DAY).toISOString();

    // Build VC (unsigned)
    const vc = buildVc({
      idx: i, childCids,
      issuerDid, issuerName,
      holderDid, holderName,
      productContract: String(node.productAddress),
      productId:       String(node.productId ?? i + 1),
      zkpProof, nowIso,
    });

    // Sign with issuer wallet
    const typedPayload = buildTypedPayload(vc);
    const payloadHash  = TypedDataEncoder.hash(domain, EIP712_TYPES, typedPayload);
    const jws          = await issuerWallet.signTypedData(domain, EIP712_TYPES, typedPayload);

    vc.proof = [{
      type:               "EcdsaSecp256k1Signature2019",
      created:            nowIso,
      proofPurpose:       "assertionMethod",
      verificationMethod: `${issuerDid}#controller`,
      role:               "seller",
      payloadHash,
      jws,
    }];

    // Pin to IPFS
    const fileName = `vc_${String(i + 1).padStart(2, "0")}.json`;
    const cid = await pinJsonToPinata({ jwt: pinataJwt, fileName, data: vc });
    cidByIndex.set(i, cid);

    // Write local copy
    fs.writeFileSync(
      path.join(outDir, `${String(i + 1).padStart(2, "0")}_${cid}.json`),
      JSON.stringify(vc, null, 2)
    );

    records.push({
      index:               i,
      chunkName:           spec.chunkName,
      vcId:                vc.id,
      cid,
      productContract:     node.productAddress,
      productId:           node.productId,
      priceCommitment:     node.priceCommitment,
      zkpCommitment:       zkpProof.commitment,
      issuerAddress:       issuerWallet.address,
      issuerName,
      holderAddress:       holderWallet.address,
      holderName,
      componentCredentials: childCids,
      uploadedAt:          nowIso,
    });

    console.log(
      `[${String(i + 1).padStart(2, "0")}/${n}] ${spec.chunkName.padEnd(38)} ` +
      `issuer=${issuerWallet.address.slice(0, 10)}… cid=${cid}`
    );
  }

  // ── Write manifest ────────────────────────────────────────────────────────
  const rootCid = cidByIndex.get(n - 1);
  const manifest = {
    runId,
    rootCid,
    nodeCount: n,
    wallets: {
      issuerAddress:    WALLETS.issuer.address,
      issuerName:       COMPANY_NAMES.issuer,
      deployerAddress:  WALLETS.deployer.address,
      deployerName:     COMPANY_NAMES.deployer,
      ephemeralCount:   15,
      ephemeralFile:    path.join(outDir, "ephemeral_wallets.json"),
    },
    chainId,
    zkpCommitmentsFile: null,
    createdAt: new Date().toISOString(),
    records: records.sort((a, b) => a.index - b.index),
  };

  fs.writeFileSync(path.join(outDir, "manifest.json"), JSON.stringify(manifest, null, 2));
  fs.writeFileSync(
    path.join(repoRoot, "data", "generated", "latest_vc_dag_manifest.json"),
    JSON.stringify(manifest, null, 2)
  );

  console.log(`\nROOT_CID=${rootCid}`);
  console.log(`MANIFEST=${path.join(outDir, "manifest.json")}`);
  console.log(`EPHEMERAL_WALLETS=${path.join(outDir, "ephemeral_wallets.json")}`);

  // Auto-anchor newly generated VC CIDs on-chain so technical anchor checks
  // are consistent by default for every generator run.
  const anchorScript = path.join(repoRoot, "backend", "integrations", "technical_verifier_tools", "anchor_vc_hashes.mjs");
  console.log("\nRunning automatic on-chain anchor step...");
  const anchorRun = spawnSync(process.execPath, [anchorScript], {
    cwd: repoRoot,
    env: {
      ...process.env,
      VC_DAG_MANIFEST_FILE: path.join(outDir, "manifest.json"),
    },
    stdio: "inherit",
  });
  if (anchorRun.status !== 0) {
    throw new Error(`Automatic anchor step failed (exit code ${anchorRun.status ?? "unknown"})`);
  }
  console.log("Automatic anchor step completed.");
}

main().catch((err) => {
  console.error(err?.stack || String(err));
  process.exit(1);
});
