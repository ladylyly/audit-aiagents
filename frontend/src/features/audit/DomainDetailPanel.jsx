import { useState } from "react";

const STATUS_LABEL = {
  pass:    "Pass",
  fail:    "Fail",
  uncertain: "Review",
  blocked: "Could Not Run",
  not_applicable: "Not Applicable",
  warning: "Note",
  info:    "Info",
  expired: "Expired",
  suspended: "Suspended",
};

function StatusBadge({ status }) {
  const normalized =
    status === "expired" || status === "suspended" ? "fail" : status;
  return (
    <span className={`finding-badge ${normalized}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

function RuleLabel({ rule }) {
  const articleRef = rule?.articleRef || rule?.id || "Rule";
  return rule?.paragraphRef ? `${articleRef} ${rule.paragraphRef}` : articleRef;
}

function RuleRow({ rule }) {
  const rowStatus = rule?.status === "uncertain" ? "warning" : rule?.status === "not_applicable" ? "info" : rule?.status;
  const escalationReason = rule?.escalation?.reason;
  const encodabilityReason = !rule?.encodable && rule?.encodabilityReason ? rule.encodabilityReason : null;
  const evidenceCount = Array.isArray(rule?.evidencePointers) ? rule.evidencePointers.length : 0;

  return (
    <div className={`detail-row ${rowStatus || "info"}`}>
      <div className="detail-row-header">
        <span className="detail-article-id">{RuleLabel({ rule })}</span>
        <span className="detail-article-title">{rule?.title}</span>
        <StatusBadge status={rule?.status} />
      </div>
      {(rule?.reason || escalationReason || encodabilityReason || evidenceCount > 0) && (
        <div className={`detail-row-body ${rule?.status === "fail" ? "fail" : ""}`}>
          {rule?.reason && <div>{rule.reason}</div>}
          {encodabilityReason && <div>Encoding note: {encodabilityReason}</div>}
          {!encodabilityReason && escalationReason && <div>Escalation: {escalationReason}</div>}
          {evidenceCount > 0 && <div>Evidence pointers: {evidenceCount}</div>}
        </div>
      )}
    </div>
  );
}

function ComplianceFallbackArticles({ articles }) {
  if (articles.length === 0) {
    return (
      <div style={{ color: "var(--muted)", fontSize: "0.82rem" }}>
        No article-level data available for this report.
      </div>
    );
  }

  return (
    <>
      {articles.map((a, i) => (
        <div key={i} className={`detail-row ${a.status === "uncertain" ? "warning" : a.status === "not_applicable" ? "info" : a.status}`}>
          <div className="detail-row-header">
            <span className="detail-article-id">{a.id}</span>
            <span className="detail-article-title">{a.title}</span>
            <StatusBadge status={a.status} />
          </div>
          {a.detail && (
            <div className={`detail-row-body ${a.status === "fail" ? "fail" : ""}`}>
              {a.detail}
            </div>
          )}
        </div>
      ))}
    </>
  );
}

// ── Compliance: grouped regulation boxes ─────────────────────────────────────

const REGULATION_DEFS = [
  { id: "eu.directive.2024.1760",  label: "CSDDD",                       fullLabel: "Corporate Sustainability Due Diligence Directive" },
  { id: "eu.regulation.2017.821",  label: "Conflict Minerals Regulation", fullLabel: "EU Conflict Minerals Regulation (2017/821)" },
  { id: "eu.regulation.2023.1542", label: "EU Battery Regulation",        fullLabel: "EU Battery Regulation (2023/1542)" },
];

function worstStatus(statuses) {
  if (statuses.includes("fail"))      return "fail";
  if (statuses.includes("uncertain")) return "uncertain";
  if (statuses.includes("pass"))      return "pass";
  return "not_applicable";
}

function groupRegulations(regulations) {
  const grouped = new Map();
  for (const def of REGULATION_DEFS) {
    grouped.set(def.id, { def, entries: [] });
  }
  for (const reg of regulations) {
    const regulationId = reg?.id ?? reg?.regulation?.id;
    if (grouped.has(regulationId)) {
      grouped.get(regulationId).entries.push(reg);
    }
  }
  return grouped;
}

function summarizeRuleStatuses(rules = []) {
  return rules.reduce(
    (acc, rule) => {
      const status = rule?.status;
      if (status === "pass") acc.pass += 1;
      else if (status === "fail") acc.fail += 1;
      else if (status === "not_applicable") acc.not_applicable += 1;
      else acc.uncertain += 1;
      return acc;
    },
    { pass: 0, fail: 0, uncertain: 0, not_applicable: 0 },
  );
}

function extractLeafRules(entry) {
  const directRules = Array.isArray(entry?.rules) ? entry.rules.filter(Boolean) : [];
  if (directRules.length > 0) return directRules;
  return (entry?.chapters ?? []).flatMap((chapter) => chapter?.rules ?? []).filter(Boolean);
}

function aggregateComplianceEntries(entries) {
  return entries.reduce(
    (acc, entry) => {
      const rules = extractLeafRules(entry);
      if (rules.length > 0) {
        const summary = summarizeRuleStatuses(rules);
        acc.pass += summary.pass;
        acc.fail += summary.fail;
        acc.uncertain += summary.uncertain;
        acc.not_applicable += summary.not_applicable;
        acc.applicable += summary.pass + summary.fail + summary.uncertain;
        acc.total += rules.length;
        return acc;
      }

      const s = entry?.summary ?? {};
      acc.pass += Number(s.pass ?? 0);
      acc.fail += Number(s.fail ?? 0);
      acc.uncertain += Number(s.uncertain ?? 0);
      acc.not_applicable += Number(s.not_applicable ?? 0);
      acc.applicable += Number(s.applicable ?? (Number(s.pass ?? 0) + Number(s.fail ?? 0) + Number(s.uncertain ?? 0)));
      acc.total += Number(s.total ?? 0);
      return acc;
    },
    { pass: 0, fail: 0, uncertain: 0, not_applicable: 0, applicable: 0, total: 0 },
  );
}

function RegulationBox({ def, entries }) {
  const [open, setOpen] = useState(false);

  const hasData = entries.length > 0;
  const aggregated = aggregateComplianceEntries(entries);
  const overallStatus = hasData ? worstStatus(entries.map((r) => r?.status).filter(Boolean)) : "not_applicable";
  const allChapters   = entries.flatMap((r) => r?.chapters ?? []);

  return (
    <div className={`compliance-reg-box ${overallStatus}`}>
      <button
        type="button"
        className="compliance-reg-trigger"
        onClick={() => hasData && setOpen((o) => !o)}
        aria-expanded={open}
        disabled={!hasData}
      >
        <div className="compliance-reg-trigger-left">
          <span className="compliance-reg-label">{def.label}</span>
          <span className="compliance-reg-full-label">{def.fullLabel}</span>
        </div>
        <div className="compliance-reg-trigger-right">
          {hasData ? (
            <div className="compliance-reg-stats">
              <span className="compliance-reg-stat neutral">{aggregated.total} evaluated</span>
              {aggregated.not_applicable > 0 && (
                <span className="compliance-reg-stat muted">{aggregated.not_applicable} N/A</span>
              )}
              <span className="compliance-reg-stat pass">{aggregated.pass} pass</span>
              <span className="compliance-reg-stat fail">{aggregated.fail} fail</span>
              {aggregated.uncertain > 0 && (
                <span className="compliance-reg-stat uncertain">{aggregated.uncertain} review</span>
              )}
            </div>
          ) : (
            <span className="compliance-reg-stat muted">Not evaluated</span>
          )}
          <StatusBadge status={overallStatus} />
          {hasData && <span className={`card-chevron ${open ? "open" : ""}`} style={{ marginLeft: 6 }}>▼</span>}
        </div>
      </button>

      {open && (
        <div className="compliance-reg-body">
          {allChapters.map((chapter, ci) => {
            const chapterStatus =
              chapter?.status === "uncertain" ? "warning"
              : chapter?.status === "not_applicable" ? "info"
              : chapter?.status;
            const chapterSummary = chapter?.summary ?? {};
            return (
              <div key={chapter?.id || ci} className={`compliance-chapter-block ${chapterStatus || "info"}`}>
                <div className="detail-row-header">
                  <span className="detail-article-id">{chapter?.id || "Chapter"}</span>
                  <span className="detail-article-title">{chapter?.title}</span>
                  <StatusBadge status={chapter?.status} />
                </div>
                <div className="detail-row-body">
                  {chapter?.applicabilityExplanation && <div>{chapter.applicabilityExplanation}</div>}
                  <div className="compliance-summary-inline">
                    pass={chapterSummary.pass ?? 0} fail={chapterSummary.fail ?? 0} uncertain={chapterSummary.uncertain ?? 0} not_applicable={chapterSummary.not_applicable ?? 0}
                  </div>
                </div>
                <div className="compliance-rule-list">
                  {(chapter?.rules ?? []).map((rule) => (
                    <RuleRow key={rule?.id || `${rule?.articleRef}-${rule?.paragraphRef}`} rule={rule} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ComplianceDetail({ data }) {
  const regulations = data?.regulations ?? [];
  const articles    = data?.articles    ?? [];

  if (regulations.length === 0 && articles.length === 0 && (data?.detail ?? []).length > 0) {
    return (
      <>
        {(data.detail ?? []).map((line, i) => (
          <div key={i} className="detail-row info">
            <div className="detail-row-body">{line}</div>
          </div>
        ))}
      </>
    );
  }

  if (regulations.length === 0) {
    return <ComplianceFallbackArticles articles={articles} />;
  }

  const grouped = groupRegulations(regulations);

  return (
    <div className="compliance-reg-boxes">
      {REGULATION_DEFS.map((def) => {
        const { entries } = grouped.get(def.id);
        return <RegulationBox key={def.id} def={def} entries={entries} />;
      })}
    </div>
  );
}

// ── Certification: per-certificate status ─────────────────────────────────────
function CertificationDetail({ data, technicalChecks }) {
  const failedTechDetails = (technicalChecks ?? [])
    .filter((s) => (s.status === "failed" || s.status === "blocked") && s.detail)
    .map((s) => s.detail);
  const certs = data?.certifications ?? [];

  if (certs.length === 0 && (data?.detail ?? []).length > 0) {
    return (
      <>
        {(data.detail ?? []).map((line, i) => (
          <div key={i} className="detail-row info">
            <div className="detail-row-body">{line}</div>
          </div>
        ))}
      </>
    );
  }

  if (certs.length === 0) {
    return (
      <div style={{ color: "var(--muted)", fontSize: "0.82rem" }}>
        No certification data available for this report.
      </div>
    );
  }

  return (
    <>
      {certs.map((c, i) => (
        <div key={i} className={`detail-row ${c.status}`}>
          <div className="detail-row-header">
            <div style={{ flex: 1, minWidth: 0 }}>
              <span className="detail-cert-name">{c.name}</span>
              <span className="detail-cert-subtitle">
                {c.status === "pass"
                  ? (c.passingCids?.[0] ?? c.title ?? "Validated VC")
                  : "No validated VC in the supply chain"}
              </span>
            </div>
            <div className="detail-cert-meta">
              {c.status === "pass" && (c.passingNodeCount ?? 0) > 1 && (
                <span>{c.passingNodeCount} passing VCs</span>
              )}
              {c.status !== "pass" && (c.applicableNodeCount ?? 0) > 0 && (
                <span>{c.applicableNodeCount} applicable VCs checked</span>
              )}
            </div>
            <StatusBadge status={c.status} />
          </div>
          {c.detail && (
            <div className={`detail-row-body ${c.status === "fail" || c.status === "expired" || c.status === "suspended" ? "fail" : ""}`}>
              {c.detail}
            </div>
          )}
          {Array.isArray(c.warnings) && c.warnings.length > 0 && (() => {
            const clean = (msg) => {
              const stripped = msg.replace(/^this vc is not technically verifiable\.?\s*/i, "").trim();
              return stripped || msg;
            };
            const counts = new Map();
            for (const w of c.warnings) counts.set(clean(w), (counts.get(clean(w)) || 0) + 1);
            const applicable = c.applicableNodeCount ?? c.warnings.length;
            return Array.from(counts.entries()).map(([reason, n], wi) => {
              const extra = failedTechDetails.filter((d) => d !== reason);
              const suffix = extra.length > 0 ? `; ${extra.join("; ")}` : "";
              const text = n > 1
                ? `${n} of ${applicable} VC${applicable !== 1 ? "s" : ""} carrying this certification cannot be verified — ${reason}${suffix}`
                : `Warning: ${reason}${suffix}`;
              return (
                <div key={wi} className="detail-row-body" style={{ color: "var(--pending)" }}>
                  {text}
                </div>
              );
            });
          })()}
        </div>
      ))}
    </>
  );
}

// ── ESG: E / S / G sub-score breakdown ───────────────────────────────────────
function ESGDetail({ data }) {
  const breakdown = data?.breakdown ?? null;
  const items     = data?.items ?? [];
  const flags     = data?.flags ?? [];
  const verdict   = data?.verdict ?? null;

  if (!breakdown && items.length === 0 && (data?.detail ?? []).length > 0) {
    return (
      <>
        {(data.detail ?? []).map((line, i) => (
          <div key={i} className="detail-row info">
            <div className="detail-row-body">{line}</div>
          </div>
        ))}
      </>
    );
  }

  function scoreClass(score) {
    if (score === null || score === undefined) return "neutral";
    if (score >= 80) return "pass";
    if (score >= 55) return "warning";
    return "fail";
  }

  return (
    <>
      {(verdict || flags.length > 0) && (
        <div className="detail-row info" style={{ marginBottom: "12px" }}>
          <div className="detail-row-header">
            <span className="detail-article-id">Summary</span>
            <span className="detail-article-title">
              {verdict ? `Verdict: ${verdict}` : "ESG summary"}
            </span>
            <StatusBadge status={verdict === "COMPLIANT" ? "pass" : verdict === "NON_COMPLIANT" ? "fail" : "warning"} />
          </div>
          <div className="detail-row-body">
            {flags.length > 0 && <div>Flags: {flags.join(", ")}</div>}
          </div>
        </div>
      )}

      {breakdown && (
        <div className="esg-sub-grid">
          {["environmental", "social", "governance"].map((key) => {
            const val = breakdown[key];
            return (
              <div key={key} className="esg-sub-cell">
                <div className="esg-sub-label">{key.charAt(0).toUpperCase() + key.slice(1)}</div>
                <div className={`esg-sub-score ${val != null ? scoreClass(val) : "neutral"}`}>
                  {val != null ? `${val}` : "—"}
                  {val != null && <span style={{ fontSize: "0.8rem", fontWeight: 600 }}>/100</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {items.map((item, i) => (
        <div key={i} className={`detail-row ${item.status}`}>
          <div className="detail-row-header">
            <span className="detail-article-id">{item.category}</span>
            <span className="detail-article-title">{item.title}</span>
            <StatusBadge status={item.status} />
          </div>
          {item.detail && (
            <div className={`detail-row-body ${item.status === "fail" ? "fail" : ""}`}>
              {item.detail}
            </div>
          )}
        </div>
      ))}

      {!breakdown && items.length === 0 && (
        <div style={{ color: "var(--muted)", fontSize: "0.82rem" }}>
          No ESG breakdown data available for this report.
        </div>
      )}
    </>
  );
}

// ── Technical: verification step list ────────────────────────────────────────
function TechnicalDetail({ checks }) {
  if (!checks || checks.length === 0) {
    return <div style={{ color: "var(--muted)", fontSize: "0.82rem" }}>No technical step data available.</div>;
  }

  return (
    <>
      {checks.map((step) => (
        <div key={step.key} className={`technical-step ${step.status === "blocked" ? "failed" : step.status}`}>
          <div className="technical-step-row">
            <span className={`technical-step-dot ${step.status === "blocked" ? "failed" : step.status}`} />
            <span className="technical-step-label">{step.label}</span>
            <span className="technical-step-status">
              {step.status === "passed"  ? "Passed"  :
               step.status === "failed"  ? "Failed"  :
               step.status === "blocked" ? "Could Not Run" :
               step.status === "skipped" ? "Skipped" :
               step.status === "running" ? "Running" : "Pending"}
            </span>
          </div>
          {step.detail && <div className="technical-step-detail">{step.detail}</div>}
        </div>
      ))}
    </>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────
const DOMAIN_TITLES = {
  compliance:    "Compliance — Regulation and Chapter Breakdown",
  certification: "Certification — Certificate Status",
  esg:           "ESG — Environmental, Social & Governance Breakdown",
  technical:     "Technical — Detailed Verification Steps",
};

export default function DomainDetailPanel({ domain, domainData, onClose, technicalChecks, embedded = false }) {
  if (!domain || !domainData) return null;

  return (
    <div className={`domain-detail-panel ${embedded ? "embedded" : ""}`}>
      {!embedded && (
        <div className="domain-detail-header">
          <span className="domain-detail-title">{DOMAIN_TITLES[domain] ?? domain}</span>
          <button className="domain-detail-close" onClick={onClose} title="Close">✕</button>
        </div>
      )}
      <div className="domain-detail-body">
        {domain === "compliance"    && <ComplianceDetail    data={domainData} />}
        {domain === "certification" && <CertificationDetail data={domainData} technicalChecks={technicalChecks} />}
        {domain === "esg"           && <ESGDetail           data={domainData} />}
        {domain === "technical"     && <TechnicalDetail     checks={technicalChecks} />}
      </div>
    </div>
  );
}
