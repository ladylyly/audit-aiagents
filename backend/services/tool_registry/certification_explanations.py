from typing import Any, Dict

from backend.integrations.llm_client import LLMClient


def explain_findings(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    findings = [f for f in (tool_input.get("findings") or []) if isinstance(f, dict)]
    target = [f for f in findings if f.get("status") in {"fail", "uncertain"}]
    if not target:
        return {"findings": []}

    return LLMClient().enrich_certification_findings(
        findings=[
            {
                "cid": finding.get("cid"),
                "certificationId": finding.get("certificationId"),
                "displayName": finding.get("displayName"),
                "status": finding.get("status"),
                "findingType": finding.get("findingType"),
                "failureType": finding.get("failureType"),
                "reason": finding.get("reason"),
                "evidencePointers": finding.get("evidencePointers") or [],
            }
            for finding in target
        ],
        context={
            "rootCid": tool_input.get("rootCid"),
            "summary": tool_input.get("summary") or {},
        },
    )
