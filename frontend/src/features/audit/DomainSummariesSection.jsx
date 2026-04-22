import { useState } from "react";
import DomainDetailPanel from "./DomainDetailPanel.jsx";

const DOMAIN_ORDER = ["technical", "compliance", "certification", "esg"];

const DOMAIN_LABELS = {
  technical: "Technical",
  compliance: "Compliance",
  certification: "Certification",
  esg: "ESG",
};

const STATE_LABELS = {
  pass: "Pass",
  fail: "Fail",
  uncertain: "Review",
  partial: "Partial Pass",
  pending: "Pending",
  blocked: "Could Not Run",
};

function hasMixedPassFailWithoutUncertainty(domain) {
  const summary = domain?.summary ?? {};
  const passed = Number(summary?.pass ?? 0);
  const failed = Number(summary?.fail ?? 0);
  const uncertain = Number(summary?.uncertain ?? 0);
  return passed > 0 && failed > 0 && uncertain === 0;
}

function computeDomainSummaryDisplayState(domainKey, domainStatus, domainResult) {
  const score = domainStatus?.score;
  if (!Number.isFinite(score)) return domainStatus?.state ?? "pending";
  if (score >= 85) return "pass";
  if (score <= 54) return "fail";

  const summary = domainStatus?.summary ?? {};
  const passed = Number(summary?.pass ?? 0);
  const failed = Number(summary?.fail ?? 0);
  const uncertain = Number(summary?.uncertain ?? 0);
  const notApplicable = Number(summary?.not_applicable ?? 0);
  const applicable = Number(summary?.applicable ?? passed + failed + uncertain);

  if (domainKey === "compliance") {
    if (uncertain > 0 && uncertain >= failed && uncertain >= Math.max(1, Math.ceil(applicable / 2))) {
      return "uncertain";
    }
    return "partial";
  }

  if (domainKey === "certification") {
    if (hasMixedPassFailWithoutUncertainty(domainStatus)) return "partial";
    if (uncertain > 0) return "uncertain";
    return "partial";
  }

  if (domainKey === "esg") {
    const scores = domainResult?.scores ?? {};
    const subScores = [scores?.E, scores?.S, scores?.G].filter((value) => Number.isFinite(value));
    if (subScores.length === 3) return "partial";
    return domainStatus?.state === "uncertain" || notApplicable > 0 ? "uncertain" : "partial";
  }

  return domainStatus?.state === "uncertain" ? "uncertain" : "partial";
}

function compactText(value, fallback = "") {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text || fallback;
}

function buildFallbackSummary(domain, domainSummaries, domainStatus) {
  const summary = domainSummaries?.[domain];
  if (summary && typeof summary === "object") {
    return {
      domain,
      state: summary.state ?? domainStatus?.[domain]?.state ?? "pending",
      summaryText: compactText(summary.summaryText, "No domain summary available."),
      source: compactText(summary.source, "domain_summary"),
      fallbackReason: compactText(summary.fallbackReason),
    };
  }

  const status = domainStatus?.[domain] ?? {};
  const observations = Array.isArray(status?.observations) ? status.observations : [];
  const detail = Array.isArray(status?.detail) ? status.detail : [];
  return {
    domain,
    state: status?.state ?? "pending",
    summaryText: compactText(observations[0] || detail[0], "No domain summary available."),
    source: "deterministic_fallback",
    fallbackReason: "",
  };
}

export default function DomainSummariesSection({
  domainSummaries,
  domainStatus,
  domainResults,
  technicalChecks,
}) {
  const [activeTab, setActiveTab] = useState(DOMAIN_ORDER[0]);
  const [accordionOpen, setAccordionOpen] = useState(false);

  function handleTabChange(domain) {
    if (domain !== activeTab) {
      setActiveTab(domain);
      setAccordionOpen(false);
    }
  }

  const activeItem = buildFallbackSummary(activeTab, domainSummaries, domainStatus);

  return (
    <div className="panel domain-tabs-panel">
      <div className="panel-heading">Domain Summaries</div>

      {/* Tab bar */}
      <div className="domain-tabs" role="tablist">
        {DOMAIN_ORDER.map((domain) => {
          const itemState = computeDomainSummaryDisplayState(
            domain,
            domainStatus?.[domain],
            domainResults?.[domain],
          );
          const dotState = itemState === "blocked" ? "fail" : itemState;

          return (
            <button
              key={domain}
              role="tab"
              aria-selected={activeTab === domain}
              className={`domain-tab ${activeTab === domain ? "active" : ""}`}
              onClick={() => handleTabChange(domain)}
              type="button"
            >
              <span className={`domain-tab-dot ${dotState}`} />
              <span className="domain-tab-label">{DOMAIN_LABELS[domain]}</span>
              <span className="domain-tab-status">{STATE_LABELS[itemState] ?? itemState}</span>
            </button>
          );
        })}
      </div>

      {/* Active tab content */}
      <div className="domain-tab-content" role="tabpanel">
        {activeItem?.source === "deterministic_fallback" && (
          <div className="domain-summary-note">
            LLM summary unavailable. Showing deterministic fallback.
          </div>
        )}
        <p className="domain-summary-copy">{activeItem?.summaryText}</p>
      </div>

      {/* Accordion: deterministic findings */}
      <div className="domain-accordion">
        <button
          type="button"
          className="domain-accordion-trigger"
          onClick={() => setAccordionOpen((o) => !o)}
          aria-expanded={accordionOpen}
        >
          <span>View deterministic findings</span>
          <span className={`card-chevron ${accordionOpen ? "open" : ""}`}>▼</span>
        </button>
        {accordionOpen && (
          <div className="domain-accordion-body">
            <DomainDetailPanel
              domain={activeTab}
              domainData={domainResults?.[activeTab] ?? domainStatus?.[activeTab]}
              onClose={() => setAccordionOpen(false)}
              technicalChecks={technicalChecks}
              embedded={true}
            />
          </div>
        )}
      </div>
    </div>
  );
}
