from typing import Any, Dict, List

from backend.integrations.llm_client import LLMClient


def _status_rank(status: str) -> int:
    return {
        "fail": 0,
        "uncertain": 1,
        "pass": 2,
        "not_applicable": 3,
    }.get(status or "uncertain", 1)


def _sample_node_outcomes(node_outcomes: List[Dict[str, Any]], *, limit: int = 3) -> Dict[str, Any]:
    counts = {"fail": 0, "uncertain": 0, "pass": 0, "not_applicable": 0}
    samples: List[Dict[str, Any]] = []

    for item in node_outcomes:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "uncertain")
        if status not in counts:
            status = "uncertain"
        counts[status] += 1
        if status in {"fail", "uncertain"} and len(samples) < limit:
            samples.append(
                {
                    "nodeCid": item.get("nodeCid"),
                    "nodeIndex": item.get("nodeIndex"),
                    "status": status,
                    "reason": item.get("reason"),
                }
            )

    return {"counts": counts, "samples": samples}


def _sample_regulation_rules(regulation: Dict[str, Any], *, limit: int = 6) -> List[Dict[str, Any]]:
    rules = [rule for rule in (regulation.get("rules") or []) if isinstance(rule, dict)]
    non_pass = [rule for rule in rules if rule.get("status") in {"fail", "uncertain"}]
    ordered = sorted(non_pass, key=lambda rule: (_status_rank(str(rule.get("status"))), str(rule.get("id") or "")))

    sampled: List[Dict[str, Any]] = []
    for rule in ordered[:limit]:
        node_summary = _sample_node_outcomes(rule.get("nodeOutcomes") or [])
        sampled.append(
            {
                "id": rule.get("id"),
                "articleRef": rule.get("articleRef"),
                "paragraphRef": rule.get("paragraphRef"),
                "title": rule.get("title"),
                "status": rule.get("status"),
                "reason": rule.get("reason"),
                "encodable": rule.get("encodable"),
                "encodabilityReason": rule.get("encodabilityReason"),
                "evidencePointers": [
                    pointer
                    for pointer in (rule.get("evidencePointers") or [])
                    if isinstance(pointer, str)
                ][:4],
                "nodeOutcomeSummary": node_summary,
            }
        )
    return sampled


def _sample_regulation_nodes(
    node_results: List[Dict[str, Any]],
    *,
    regulation_id: str,
    limit: int = 4,
) -> Dict[str, Any]:
    relevant = [
        item
        for item in node_results
        if isinstance(item, dict) and str(item.get("regulationId") or "") == regulation_id
    ]
    counts = {"fail": 0, "uncertain": 0, "pass": 0, "not_applicable": 0}
    samples: List[Dict[str, Any]] = []

    for item in relevant:
        status = str(item.get("status") or "uncertain")
        if status not in counts:
            status = "uncertain"
        counts[status] += 1
        if status in {"fail", "uncertain"} and len(samples) < limit:
            summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
            samples.append(
                {
                    "nodeCid": item.get("cid"),
                    "nodeIndex": item.get("nodeIndex"),
                    "status": status,
                    "summary": {
                        "pass": summary.get("pass", 0),
                        "fail": summary.get("fail", 0),
                        "uncertain": summary.get("uncertain", 0),
                    },
                }
            )

    return {"counts": counts, "samples": samples}


def _build_regulation_findings(tool_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    regulations = [r for r in (tool_input.get("regulations") or []) if isinstance(r, dict)]
    node_results = [r for r in (tool_input.get("nodeResults") or []) if isinstance(r, dict)]
    target_regulations = [r for r in regulations if r.get("status") in {"fail", "uncertain"}]

    findings: List[Dict[str, Any]] = []
    for regulation in sorted(target_regulations, key=lambda item: _status_rank(str(item.get("status")))):
        regulation_id = str(regulation.get("id") or "")
        short_name = regulation.get("shortName") or regulation_id or "Regulation"
        summary = regulation.get("summary") if isinstance(regulation.get("summary"), dict) else {}
        sampled_rules = _sample_regulation_rules(regulation)
        node_summary = _sample_regulation_nodes(node_results, regulation_id=regulation_id)

        findings.append(
            {
                "id": short_name,
                "regulationId": regulation_id or None,
                "title": regulation.get("title"),
                "status": regulation.get("status"),
                "reason": regulation.get("message") or regulation.get("applicabilityExplanation"),
                "regulationSummary": {
                    "pass": summary.get("pass", 0),
                    "fail": summary.get("fail", 0),
                    "uncertain": summary.get("uncertain", 0),
                    "not_applicable": summary.get("not_applicable", 0),
                },
                "sampledRules": sampled_rules,
                "nodeCoverageSummary": node_summary,
            }
        )

    return findings


def _build_compact_context(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    regulations = [r for r in (tool_input.get("regulations") or []) if isinstance(r, dict)]
    non_pass_regulations = [r for r in regulations if r.get("status") in {"fail", "uncertain"}]

    return {
        "rootCid": tool_input.get("rootCid"),
        "summary": tool_input.get("summary") or {},
        "graphSummary": tool_input.get("graphSummary") or {},
        "regulationCount": len(regulations),
        "nonPassRegulations": [
            {
                "id": regulation.get("id"),
                "shortName": regulation.get("shortName"),
                "status": regulation.get("status"),
            }
            for regulation in non_pass_regulations
        ],
    }


def explain_findings(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    regulation_findings = _build_regulation_findings(tool_input)
    if regulation_findings:
        return LLMClient().enrich_compliance_findings(
            findings=regulation_findings,
            context=_build_compact_context(tool_input),
        )

    rules = [r for r in (tool_input.get("rules") or []) if isinstance(r, dict)]
    target_rules = [r for r in rules if r.get("status") in {"fail", "uncertain"}]
    if not target_rules:
        return {"rules": []}

    return LLMClient().enrich_compliance_findings(
        findings=[
            {
                "id": rule.get("id"),
                "articleRef": rule.get("articleRef"),
                "paragraphRef": rule.get("paragraphRef"),
                "title": rule.get("title"),
                "status": rule.get("status"),
                "reason": rule.get("reason"),
                "encodable": rule.get("encodable"),
                "encodabilityReason": rule.get("encodabilityReason"),
                "nodeOutcomeSummary": _sample_node_outcomes(rule.get("nodeOutcomes") or []),
                "evidencePointers": [
                    pointer
                    for pointer in (rule.get("evidencePointers") or [])
                    if isinstance(pointer, str)
                ][:4],
                "escalation": rule.get("escalation"),
            }
            for rule in target_rules
        ],
        context=_build_compact_context(tool_input),
    )
