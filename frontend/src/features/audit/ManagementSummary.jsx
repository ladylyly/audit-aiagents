import { useState, useRef, useEffect } from "react";

// key={reportId} on this component (set by parent) resets all state on report switch.
function InlineChat({ record, isDemo, reportId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [open, setOpen]         = useState(true);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(e) {
    e.preventDefault();
    const q = input.trim();
    if (!q || loading) return;

    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setLoading(true);

    try {
      const body = isDemo
        ? { reportData: record?.result ?? record, question: q }
        : { reportId, question: q };

      const res  = await fetch("/api/qa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "No response from server");
      setMessages((m) => [...m, { role: "assistant", text: data.answer ?? data.response ?? JSON.stringify(data) }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "assistant", text: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(e); }
  }

  return (
    <div className="inline-chat">
      {/* Header row with label + close toggle */}
      <div className="inline-chat-header">
        <span className="inline-chat-label" style={{ marginBottom: 0 }}>Ask the Report</span>
        <button
          className="domain-detail-close"
          type="button"
          onClick={() => setOpen((v) => !v)}
          title={open ? "Hide chat" : "Show chat"}
          style={{ fontSize: "0.75rem" }}
        >
          {open ? "▲ Hide" : "▼ Show"}
        </button>
      </div>

      {open && (
        <>
          {messages.length > 0 && (
            <div className="inline-chat-messages">
              {messages.map((m, i) => (
                <div key={i} className={`inline-chat-msg ${m.role}`}>{m.text}</div>
              ))}
              {loading && <div className="inline-chat-msg thinking">Analysing report…</div>}
              <div ref={bottomRef} />
            </div>
          )}

          <form className="inline-chat-input-row" onSubmit={handleSend}>
            <textarea
              className="inline-chat-input"
              rows={3}
              placeholder={isDemo ? "Ask about compliance, certifications, ESG scores, action items…" : "Ask a question about this report…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button
              className="btn btn-primary inline-chat-send-btn"
              type="submit"
              disabled={loading || !input.trim()}
            >
              {loading ? "…" : "Send"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}

function scoreBand(score) {
  if (!Number.isFinite(score)) return "pending";
  if (score >= 85) return "pass";
  if (score >= 55) return "uncertain";
  return "fail";
}

function countLeafClaimFields(value) {
  if (Array.isArray(value)) {
    return value.reduce((total, item) => total + countLeafClaimFields(item), 0);
  }
  if (value && typeof value === "object") {
    return Object.values(value).reduce((total, item) => total + countLeafClaimFields(item), 0);
  }
  return 1;
}

function overallVerdict(domainStatus) {
  const domains = Object.values(domainStatus ?? {});
  const states = domains.map((d) => d?.state);
  const scores = domains
    .map((d) => d?.score)
    .filter((score) => Number.isFinite(score));

  if (states.includes("running")) return "running";
  if (scores.length === 0) return "pending";
  if (scores.length < domains.length) return "pending";

  const averageScore = scores.reduce((sum, score) => sum + score, 0) / scores.length;
  return scoreBand(averageScore);
}

function verdictLabel(v) {
  if (v === "pass")      return "Overall: Compliant";
  if (v === "fail")      return "Overall: Non-Compliant";
  if (v === "uncertain") return "Overall: Review Required";
  if (v === "running")   return "Audit in Progress";
  return "Pending";
}

function DomainScoreCell({ label, domain }) {
  const score    = domain?.score    ?? null;
  const findings = domain?.findings ?? 0;
  const band     = scoreBand(score);

  return (
    <div className="domain-score-cell">
      <div className="domain-score-label">{label}</div>
      <div className={`domain-score-value ${band}`}>
        {score !== null ? `${score}` : "—"}
        {score !== null && <span style={{ fontSize: "1rem", fontWeight: 600 }}>/100</span>}
      </div>
      {score !== null && (
        <div className="domain-score-bar-track">
          <div className={`domain-score-bar-fill ${band}`} style={{ width: `${score}%` }} />
        </div>
      )}
      <div className={`domain-score-status ${band}`}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor", display: "inline-block", flexShrink: 0 }} />
        {band === "pass" ? "Pass" : band === "fail" ? "Fail" : band === "uncertain" ? "Review" : band === "running" ? "Running" : "Pending"}
      </div>
      <div className="domain-findings-count">
        {findings === 0 ? "No findings" : `${findings} finding${findings > 1 ? "s" : ""}`}
      </div>
    </div>
  );
}

function buildExecutiveSummaryContext(record) {
  const result = record?.result ?? {};
  const bundle = result?.result_bundle ?? {};
  const domainStatus = bundle?.domainStatus ?? {};
  const profile = bundle?.supplyChainProfile ?? {};
  const technical = bundle?.domainResults?.technical ?? {};
  const compliance = bundle?.domainResults?.compliance ?? {};
  const certification = bundle?.domainResults?.certification ?? {};
  const esg = bundle?.domainResults?.esg ?? {};

  const topDomainIssues = Object.entries(domainStatus)
    .map(([domain, data]) => ({
      domain,
      state: data?.state,
      findings: data?.findings ?? 0,
      detail: (data?.detail ?? [])[0] ?? null,
      observation: (data?.observations ?? [])[0] ?? null,
    }))
    .sort((a, b) => (b.findings ?? 0) - (a.findings ?? 0))
    .slice(0, 4);

  return {
    entity: result?.entity ?? "Supplier Entity",
    auditDate: result?.auditDate ?? null,
    rootCid: record?.rootCid ?? null,
    overallSuccess: result?.success ?? null,
    supplyChainProfile: {
      nodeCount: profile?.nodeCount ?? bundle?.graph?.chainLength ?? null,
      edgeCount: profile?.edgeCount ?? null,
      countries: profile?.countries ?? [],
      countryCodes: profile?.countryCodes ?? [],
      materials: profile?.topMaterials ?? [],
      facilityRoles: profile?.facilityRoles ?? [],
      stageMix: profile?.stageMix ?? {},
      hasConflictMineralsClaims: profile?.hasConflictMineralsClaims ?? false,
    },
    domainStatus: Object.fromEntries(
      Object.entries(domainStatus).map(([domain, data]) => [
        domain,
        {
          state: data?.state ?? "pending",
          score: data?.score ?? null,
          findings: data?.findings ?? 0,
          detail: (data?.detail ?? []).slice(0, 3),
          observations: (data?.observations ?? []).slice(0, 3),
        },
      ]),
    ),
    topDomainIssues,
    technical: {
      success: technical?.success ?? null,
      failureCodes: (technical?.failures ?? []).map((f) => f?.code).filter(Boolean).slice(0, 10),
      claims: (technical?.claims ?? []).slice(0, 8),
    },
    compliance: {
      status: compliance?.status ?? null,
      summary: compliance?.summary ?? {},
      failedRules: (compliance?.rules ?? []).filter((r) => r?.status === "fail").slice(0, 8).map((r) => ({
        articleRef: r?.articleRef ?? r?.id,
        title: r?.title,
        reason: r?.reason,
      })),
    },
    certification: {
      status: certification?.status ?? null,
      summary: certification?.summary ?? {},
      failedFindings: (certification?.findings ?? []).filter((f) => f?.status === "fail").slice(0, 8).map((f) => ({
        certification: f?.displayName ?? f?.certificationId,
        reason: f?.reason,
      })),
    },
    esg: {
      status: esg?.status ?? null,
      verdict: esg?.verdict ?? null,
      scores: esg?.scores ?? {},
      flags: (esg?.flags ?? []).slice(0, 8),
      topFindings: (esg?.findings ?? []).slice(0, 8).map((f) => ({
        id: f?.id,
        category: f?.category,
        status: f?.status,
        detail: f?.detail,
      })),
    },
  };
}

function isStaleExecutiveSummary(summary, record) {
  if (!summary || !String(summary).trim()) return true;

  const result = record?.result ?? {};
  const bundle = result?.result_bundle ?? {};
  const profile = bundle?.supplyChainProfile ?? {};
  const domainStatus = bundle?.domainStatus ?? {};
  const hasRichContext =
    Boolean(bundle?.claims?.length) ||
    Boolean(profile?.nodeCount) ||
    Object.keys(domainStatus).length > 0;

  if (!hasRichContext) return false;

  const normalized = String(summary).toLowerCase().replace(/\s+/g, " ").trim();
  return [
    "supplier entity",
    "auditdate is null",
    "no vc claims",
    "no technical, compliance, certification, or esg findings",
  ].some((marker) => normalized.includes(marker));
}

function generatePDF(record, entity, auditDate, verdict, domainStatus, executiveSummaryText) {
  const domainLabels = { technical: "Technical", compliance: "Compliance", certification: "Certification", esg: "ESG" };
  const domainsHtml = Object.entries(domainStatus).map(([key, d]) => `
    <tr>
      <td>${domainLabels[key] ?? key}</td>
      <td>${d.score != null ? `${d.score}/100` : "—"}</td>
      <td style="color:${scoreBand(d.score) === "pass" ? "#16a34a" : scoreBand(d.score) === "fail" ? "#dc2626" : "#7c3aed"}">${scoreBand(d.score) === "pass" ? "PASS" : scoreBand(d.score) === "fail" ? "FAIL" : scoreBand(d.score) === "uncertain" ? "REVIEW" : "PENDING"}</td>
      <td>${(d.findings ?? 0) === 0 ? "None" : `${d.findings} finding(s)`}</td>
    </tr>`).join("");

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Audit Report — ${entity}</title>
  <style>
    body { font-family: "Segoe UI", Arial, sans-serif; font-size: 13px; color: #0f172a; margin: 40px; }
    h1 { font-size: 20px; margin-bottom: 4px; }
    h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.1em; color: #64748b; margin: 24px 0 8px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }
    .meta { font-size: 11px; color: #64748b; margin-bottom: 24px; }
    .verdict { display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 24px;
      background: ${verdict === "pass" ? "#dcfce7" : verdict === "fail" ? "#fee2e2" : "#ede9fe"};
      color: ${verdict === "pass" ? "#16a34a" : verdict === "fail" ? "#dc2626" : "#7c3aed"}; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th { text-align: left; padding: 6px 8px; background: #f1f5f9; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; }
    td { padding: 8px 8px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
    .narrative { line-height: 1.7; white-space: pre-wrap; }
    @media print { body { margin: 20px; } }
  </style>
</head>
<body>
  <h1>${entity}</h1>
  <div class="meta">Management Summary Report &nbsp;·&nbsp; Audit date: ${auditDate} &nbsp;·&nbsp; Root CID: ${record?.rootCid ?? "—"}</div>
  <div class="verdict">Overall: ${verdict === "pass" ? "Compliant" : verdict === "fail" ? "Non-Compliant" : verdict === "uncertain" ? "Review Required" : verdict}</div>
  <h2>Domain Scores</h2>
  <table>
    <thead><tr><th>Domain</th><th>Score</th><th>Status</th><th>Findings</th></tr></thead>
    <tbody>${domainsHtml}</tbody>
  </table>
  <h2>Executive Summary</h2>
  <div class="narrative">${executiveSummaryText ?? "No summary available."}</div>
</body>
</html>`;

  const win = window.open("", "_blank");
  win.document.write(html);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 400);
}

async function downloadJSON(record, reportId, isDemo = false) {
  let exportPayload = record?.result ?? record;

  if (reportId && !isDemo) {
    try {
      const res = await fetch(`/api/report/${reportId}?full=1`);
      if (res.ok) {
        const data = await res.json();
        exportPayload = data?.result ?? data ?? exportPayload;
      }
    } catch {
      // Fall back to the currently loaded compact payload.
    }
  }

  const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url;
  a.download = `audit-report-${reportId ?? "export"}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ManagementSummary({ record, isDemo, reportId }) {
  const bundle       = record?.result?.result_bundle ?? {};
  const graph        = bundle?.graph ?? {};
  const profile      = bundle?.supplyChainProfile ?? {};
  const vcsByCid     = bundle?.vcsByCid ?? {};
  const graphNodes   = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const domainStatus = record?.result?.result_bundle?.domainStatus ?? {};
  const verdict      = overallVerdict(domainStatus);
  const entity       = record?.result?.entity ?? "Supplier Entity";
  const auditDate    = record?.result?.auditDate ?? record?.result?.timestamp ?? new Date().toISOString().slice(0, 10);
  const rootCid      = record?.rootCid ?? "—";
  const [generatedSummary, setGeneratedSummary] = useState(null);
  const [summaryStatus, setSummaryStatus] = useState("idle");

  const findings = [];
  const actions  = [];
  const domainLabels = { technical: "Technical", compliance: "Compliance", certification: "Certification", esg: "ESG" };

  Object.entries(domainStatus).forEach(([key, domain]) => {
    const label = domainLabels[key] ?? key;
    if (domain.state === "pass" && (domain.findings ?? 0) === 0) {
      findings.push({ type: "pass", text: `${label}: All checks passed` });
    }
    (domain.observations ?? []).forEach((obs) => findings.push({ type: "warning", text: `${label}: ${obs}` }));
    if (domain.state === "fail") {
      (domain.detail ?? []).slice(0, 3).forEach((d) => findings.push({ type: "fail", text: `${label}: ${d}` }));
    }
    (domain.actions ?? []).forEach((a) => actions.push(a));
  });

  if (actions.length === 0) {
    Object.values(domainStatus).forEach((domain) => {
      (domain.observations ?? []).forEach((obs) => actions.push({ text: obs, deadline: null }));
    });
  }

  useEffect(() => {
    let cancelled = false;

    async function generateExecutiveSummary() {
      const persistedSummary = record?.result?.executive_summary;
      if (persistedSummary && String(persistedSummary).trim()) {
        setGeneratedSummary(String(persistedSummary));
        setSummaryStatus("idle");
        return;
      }

      if (!record || record?.status === "running" || isDemo) {
        setGeneratedSummary(null);
        setSummaryStatus("idle");
        return;
      }

      const prompt = [
        "Write a professional executive summary for this supply chain audit report.",
        "Structure it as a short paragraph of 4 to 6 sentences following this order:",
        "1. Open with the supplier or entity name and the overall audit outcome (passed, failed, or requires review), mentioning the supply chain size (nodes, countries) if available.",
        "2. Summarise the technical verification outcome in one sentence — state whether the credential chain is intact or not, and name any critical failure if present.",
        "3. Summarise the compliance outcome — name the most important regulation findings, failed or uncertain articles, or state that compliance passed.",
        "4. Summarise certification and ESG outcomes briefly in one or two sentences — include specific certificate names or ESG sub-scores if available.",
        "5. Close with a concrete action or recommendation based on the most urgent finding, or confirm no immediate action is required.",
        "Rules: use the entity name from the data; be specific and reference actual finding codes, regulation names, certificate names, or scores from the report; do not invent details not present in the data; write plain prose, no bullets or headings.",
      ].join(" ");

      setSummaryStatus("loading");
      try {
        const compactSummaryContext = buildExecutiveSummaryContext(record);
        const res = await fetch("/api/qa", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reportId,
            reportData: compactSummaryContext,
            question: prompt,
            mode: "executive_summary",
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error ?? "Could not generate summary");
        if (!cancelled) setGeneratedSummary(data.answer ?? null);
      } catch {
        if (!cancelled) setGeneratedSummary(null);
      } finally {
        if (!cancelled) setSummaryStatus("idle");
      }
    }

    generateExecutiveSummary();
    return () => {
      cancelled = true;
    };
  }, [record, isDemo, reportId]);

  const narrative =
    (generatedSummary && generatedSummary.trim()) ||
    (record?.result?.executive_summary && String(record.result.executive_summary).trim()) ||
    (record?.result?.llm_summary && String(record.result.llm_summary).trim()) ||
    "LLM executive summary not possible.";
  const hasRealSummary =
    Boolean(generatedSummary && generatedSummary.trim()) ||
    Boolean(record?.result?.executive_summary && String(record.result.executive_summary).trim()) ||
    Boolean(record?.result?.llm_summary && String(record.result.llm_summary).trim());

  const auditedVcCount =
    Number.isFinite(profile?.nodeCount) ? profile.nodeCount
      : Number.isFinite(graph?.chainLength) ? graph.chainLength
        : graphNodes.length > 0 ? graphNodes.length
          : null;
  const vcClaimCount = (() => {
    const entries = Object.values(vcsByCid).filter(Boolean);
    if (entries.length === 0) return null;

    const total = entries.reduce((sum, entry) => {
      const vc = entry?.vc ?? entry;
      const claims = vc?.credentialSubject?.claims;
      if (!claims || typeof claims !== "object") return sum;
      return sum + countLeafClaimFields(claims);
    }, 0);

    return total;
  })();
  const countriesCovered = (() => {
    if (Array.isArray(profile?.countries) && profile.countries.length > 0) return profile.countries.length;
    if (Array.isArray(profile?.countryCodes) && profile.countryCodes.length > 0) return profile.countryCodes.length;
    return null;
  })();

  return (
    <div className="mgmt-summary">
      {/* Header */}
      <div className="mgmt-summary-header">
        <div>
          <div className="mgmt-summary-title">Management Summary Report</div>
          <div className="mgmt-summary-entity">{entity}</div>
          <div className="mgmt-summary-meta">
            <span className="mgmt-meta-item">Audit date: <strong>{auditDate}</strong></span>
            <span className="mgmt-meta-item">
              Root CID:&nbsp;
              <strong className="mgmt-root-cid">{rootCid}</strong>
            </span>
            {isDemo && <span className="mgmt-meta-item" style={{ color: "#d97706", fontWeight: 600 }}>★ Demo data</span>}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8, flexShrink: 0 }}>
          <div className={`mgmt-verdict ${verdict}`}>{verdictLabel(verdict)}</div>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              className="btn btn-secondary"
              style={{ padding: "5px 12px", fontSize: "0.75rem" }}
              onClick={() => generatePDF(record, entity, auditDate, verdict, domainStatus, narrative)}
            >
              ↓ PDF
            </button>
            <button
              className="btn btn-secondary"
              style={{ padding: "5px 12px", fontSize: "0.75rem" }}
              onClick={() => downloadJSON(record, reportId, isDemo)}
            >
              ↓ JSON
            </button>
          </div>
        </div>
      </div>

      <div className="mgmt-kpi-grid">
        <div className="mgmt-kpi-cell">
          <div className="mgmt-kpi-label">VCs Audited</div>
          <div className="mgmt-kpi-value">{auditedVcCount ?? "—"}</div>
        </div>
        <div className="mgmt-kpi-cell">
          <div className="mgmt-kpi-label">Claims in VCs</div>
          <div className="mgmt-kpi-value">{vcClaimCount ?? "—"}</div>
        </div>
        <div className="mgmt-kpi-cell">
          <div className="mgmt-kpi-label">Countries Covered</div>
          <div className="mgmt-kpi-value">{countriesCovered ?? "—"}</div>
        </div>
      </div>

      {/* Domain scores */}
      <div className="domain-score-grid">
        <DomainScoreCell label="Technical"     domain={domainStatus.technical} />
        <DomainScoreCell label="Compliance"    domain={domainStatus.compliance} />
        <DomainScoreCell label="Certification" domain={domainStatus.certification} />
        <DomainScoreCell label="ESG"           domain={domainStatus.esg} />
      </div>

      {/* Narrative + findings sidebar */}
      <div className="mgmt-body">
        <div className="mgmt-narrative">
          <div className="mgmt-narrative-label">Executive Summary</div>
          <div className="mgmt-narrative-text">{narrative}</div>
          {summaryStatus === "loading" && !hasRealSummary && (
            <div className="mgmt-narrative-text" style={{ color: "var(--muted)", fontStyle: "italic", marginTop: 8 }}>
              Refining summary from full report data…
            </div>
          )}

          {/* key=reportId forces a full remount (clearing history) when the report changes */}
          <InlineChat key={reportId} record={record} isDemo={isDemo} reportId={reportId} />
        </div>

        <div className="mgmt-sidebar-panels">
          {findings.length > 0 && (
            <div className="mgmt-findings-panel">
              <div className="mgmt-narrative-label">Key Findings</div>
              <div className="mgmt-scroll-list">
                {findings.map((f, i) => (
                  <div key={i} className="finding-item">
                    <span className={`finding-badge ${f.type}`}>
                      {f.type === "pass" ? "Pass" : f.type === "fail" ? "Fail" : f.type === "warning" ? "Note" : "Info"}
                    </span>
                    <span className="finding-text">{f.text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {actions.length > 0 && (
            <div className="mgmt-actions-panel">
              <div className="mgmt-narrative-label">Action Items</div>
              <div className="mgmt-scroll-list">
                {actions.map((a, i) => (
                  <div key={i} className="action-item">
                    <span className="action-arrow">→</span>
                    <div>
                      <div>{typeof a === "string" ? a : a.text}</div>
                      {a.deadline && <div className="action-deadline">Due: {a.deadline}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {findings.length === 0 && actions.length === 0 && (
            <div style={{ padding: "20px", color: "var(--muted)", fontSize: "0.82rem" }}>
              {record?.status === "running" ? "Collecting results…" : "No findings available."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
