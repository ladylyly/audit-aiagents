import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from backend.paths import BACKEND_ENV_PATH


_CID_V0_RE = re.compile(r"\b(Qm[1-9A-HJ-NP-Za-km-z]{44,})\b")
_CID_V1_RE = re.compile(r"\b(bafy[0-9a-z]{20,})\b", re.IGNORECASE)


def extract_cid_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    m0 = _CID_V0_RE.search(text)
    if m0:
        return m0.group(1)
    m1 = _CID_V1_RE.search(text)
    if m1:
        return m1.group(1)
    return None


@dataclass(frozen=True)
class LLMClientConfig:
    model: str
    temperature: float = 0.2


class LLMClient:
    """
    OpenAI client used for orchestration planning, explanation text, and report Q&A.
    The orchestrator checks any planning output before it is used.
    """

    def __init__(self, config: Optional[LLMClientConfig] = None):
        load_dotenv(BACKEND_ENV_PATH)

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
        self.config = config or LLMClientConfig(model=model, temperature=temperature)

        # Import OpenAI here so deterministic paths still work without the package installed.
        from openai import OpenAI  # type: ignore

        self.client = OpenAI(api_key=api_key)

    # ------------------------------------------------------------------
    # Orchestration planning
    # ------------------------------------------------------------------

    def plan_orchestration(
        self,
        *,
        root_cid: Optional[str],
        user_prompt: Optional[str],
        available_tools: List[Dict[str, Any]],
        policy: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = self._build_plan_prompt(
            root_cid=root_cid,
            user_prompt=user_prompt,
            available_tools=available_tools,
            policy=policy,
        )
        plan = self._parse_json_object(self._call_llm(prompt))
        if not isinstance(plan, dict):
            raise ValueError("LLM plan must be a JSON object")
        return plan

    def plan_explanation_tools(
        self,
        *,
        root_cid: str,
        candidates: List[Dict[str, Any]],
        deterministic_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = self._build_explanation_plan_prompt(
            root_cid=root_cid,
            candidates=candidates,
            deterministic_summary=deterministic_summary,
        )
        plan = self._parse_json_object(self._call_llm(prompt))
        if not isinstance(plan, dict):
            raise ValueError("LLM explanation plan must be a JSON object")
        if not isinstance(plan.get("selections"), list):
            raise ValueError("LLM explanation plan must include selections[]")
        return plan

    # ------------------------------------------------------------------
    # Explanation enrichment
    # ------------------------------------------------------------------

    def diagnose_technical_failures(
        self,
        *,
        failures: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = f"""
You are a technical audit diagnosis module.
Explain deterministic verification failures without changing their truth value.

Return only JSON with this exact shape:
{{
  "diagnoses": [
    {{
      "failure_ref": 0,
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "explanation": "string",
      "remediation": ["string", "string"],
      "confidence": 0.0
    }}
  ]
}}

Rules:
- Keep explanations grounded in provided failures and context.
- Never claim deterministic checks passed if they failed.
- "confidence" is optional; if present it must be 0..1.

FAILURES:
{json.dumps(failures)}

CONTEXT:
{json.dumps(context)}
""".strip()

        raw = self._parse_json_object(self._call_llm(prompt))
        diagnoses = raw.get("diagnoses") if isinstance(raw, dict) else None
        return {"diagnoses": self._validate_technical_diagnoses(diagnoses)}

    def enrich_compliance_findings(
        self,
        *,
        findings: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = f"""
You are an assistant for compliance audit explanation enrichment.
Do not alter compliance truth values. Add interpretation only for failed/uncertain rules.

Return only JSON with this exact shape:
{{
  "rules": [
    {{
      "id": "rule-id",
      "llmExplanation": "string",
      "missingEvidenceSummary": "string",
      "recommendedNextEvidence": ["string"],
      "managementImpact": "string",
      "confidence": 0.0
    }}
  ]
}}

FINDINGS:
{json.dumps(findings)}

CONTEXT:
{json.dumps(context)}
""".strip()

        raw = self._parse_json_object(self._call_llm(prompt))
        rules = raw.get("rules") if isinstance(raw, dict) else None
        return {"rules": self._validate_compliance_rules(rules)}

    def enrich_esg_assessment(
        self,
        *,
        verdict: str,
        scores: Dict[str, Any],
        narrative_seed: str,
        findings: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = f"""
You are an assistant for ESG explanation enrichment.
Do not alter deterministic ESG verdicts or scores.

Return only JSON with this exact shape:
{{
  "llmExplanation": "string",
  "primaryDrivers": ["string"],
  "recommendedActions": ["string"],
  "confidence": 0.0
}}

VERDICT: {json.dumps(verdict)}
SCORES: {json.dumps(scores)}
NARRATIVE_SEED: {json.dumps(narrative_seed)}
FINDINGS: {json.dumps(findings)}
CONTEXT: {json.dumps(context)}
""".strip()

        raw = self._parse_json_object(self._call_llm(prompt))
        return self._validate_esg_enrichment(raw)

    def enrich_certification_findings(
        self,
        *,
        findings: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = f"""
You are an assistant for certification audit explanation enrichment.
Do not alter deterministic statuses.

Return only JSON with this exact shape:
{{
  "findings": [
    {{
      "cid": "Qm...",
      "certificationId": "id",
      "llmExplanation": "string",
      "recommendedEvidence": ["string"],
      "recommendedActions": ["string"],
      "confidence": 0.0
    }}
  ]
}}

FINDINGS:
{json.dumps(findings)}

CONTEXT:
{json.dumps(context)}
""".strip()

        raw = self._parse_json_object(self._call_llm(prompt))
        items = raw.get("findings") if isinstance(raw, dict) else None
        return {"findings": self._validate_certification_findings(items)}

    def summarize_domain_assessment(
        self,
        *,
        domain: str,
        supply_chain_profile: Dict[str, Any],
        domain_status: Dict[str, Any],
        domain_result: Dict[str, Any],
        explanation: Dict[str, Any],
    ) -> str:
        prompt = self._build_domain_summary_prompt(
            domain=domain,
            supply_chain_profile=supply_chain_profile,
            domain_status=self._compact_domain_summary_status(domain, domain_status),
            domain_result=self._compact_domain_summary_result(domain, domain_result),
            explanation=self._compact_domain_summary_explanation(domain, explanation),
        )
        return self._call_llm(prompt).strip()

    # Report summaries and Q&A

    def summarize(self, result_bundle: Dict[str, Any]) -> str:
        prompt = self._build_summary_prompt(result_bundle)
        return self._call_llm(prompt).strip()

    def ask_about_report(self, report: Any, question: str) -> str:
        """Answer a question about a completed audit report."""
        return self._ask_with_openai(report, question)

    def ask_executive_summary(self, report: Any, question: str) -> str:
        """
        Generate the executive summary text.

        Uses `OPENAI_API_KEY_SUMMARY` first and falls back to `OPENAI_API_KEY`.
        """
        summary_openai_key = os.getenv("OPENAI_API_KEY_SUMMARY")
        if summary_openai_key:
            try:
                return self._ask_with_openai_key(
                    api_key=summary_openai_key,
                    report=report,
                    question=question,
                )
            except Exception:
                pass

        return self._ask_with_openai(report, question)

    # Prompt builders

    def _build_plan_prompt(
        self,
        *,
        root_cid: Optional[str],
        user_prompt: Optional[str],
        available_tools: List[Dict[str, Any]],
        policy: Dict[str, Any],
    ) -> str:
        return f"""
You are the orchestrator-planning module for a supply-chain multi-agent system.

You must output ONLY valid JSON (no markdown, no commentary).

Goal:
- Plan which tools to call given the user request (often a root VC CID).
- Never skip mandatory technical verification steps unless policy explicitly allows.
- Prefer minimal, safe plans.

Inputs:
- rootCid (optional): {json.dumps(root_cid)}
- userPrompt (optional): {json.dumps(user_prompt)}
- availableTools: {json.dumps(available_tools)}
- policy: {json.dumps(policy)}

Output JSON schema:
{{
  "rootCid": string|null,
  "actions": [
    {{
      "tool": "build_graph" | "fetch_vcs_for_graph" | "run_technical_verification",
      "options": object
    }}
  ],
  "route": [
    {{
      "agent": "compliance" | "cert" | "esg",
      "rationale": string
    }}
  ],
  "notes": string
}}

Rules:
- If rootCid is missing, try extracting it from userPrompt.
- If still missing, produce an empty actions list and explain in notes.
- If policy.strict == true, actions MUST include build_graph and run_technical_verification.
- Do not invent tools not listed in availableTools.
""".strip()

    def _build_explanation_plan_prompt(
        self,
        *,
        root_cid: str,
        candidates: List[Dict[str, Any]],
        deterministic_summary: Dict[str, Any],
    ) -> str:
        return f"""
You are the stage-2 explanation planning module for a supply-chain multi-agent system.

You must output ONLY valid JSON (no markdown, no commentary).

Goal:
- Choose which explanation tools should run after deterministic audit.
- Only choose from candidate tools provided.
- Do not invent tools.

Inputs:
- rootCid: {json.dumps(root_cid)}
- candidates: {json.dumps(candidates)}
- deterministicSummary: {json.dumps(deterministic_summary)}

Output JSON schema:
{{
  "selections": [
    {{
      "tool": string,
      "selected": boolean,
      "rationale": string,
      "confidence": number,
      "skip_reason": string
    }}
  ],
  "notes": string
}}

Rules:
- Every tool in candidates should appear in selections exactly once.
- confidence must be between 0 and 1.
- If selected is false, provide skip_reason.
- Keep rationale concise and grounded in deterministicSummary.
""".strip()

    def _build_summary_prompt(self, result_bundle: Dict[str, Any]) -> str:
        return f"""
You are an assistant that writes a concise orchestration summary for a supply-chain audit.
Be factual. Mention whether technical verification succeeded and the main failure codes if not.
Also mention routing suggestions if present.

Return plain text only.

DATA (JSON):
{json.dumps(result_bundle)}
""".strip()

    def _build_domain_summary_prompt(
        self,
        *,
        domain: str,
        supply_chain_profile: Dict[str, Any],
        domain_status: Dict[str, Any],
        domain_result: Dict[str, Any],
        explanation: Dict[str, Any],
    ) -> str:
        domain_instructions = self._domain_summary_guidance(domain)
        return f"""
You are writing one domain-level summary for a supply-chain audit report.

Your job:
- Based on the deterministic audit output for this domain and the overall supply-chain context,
  explain the most important highlights, anomalies, weak points, or review signals the user should be aware of.
- Give likely reasons only when they are grounded in the provided data.
- If the domain passed, explain the most important positive result plainly and concisely.
- If the domain is failed or uncertain, explain what stands out and why it matters.

Rules:
- Do not change or reinterpret deterministic truth values.
- Do not invent missing evidence, countries, causes, or certificates.
- Mention concrete drivers when they are present in the input, such as country context, certificate scope mismatch,
  missing evidence, repeated uncertain rules, or score imbalances.
- Use "review" only when the input genuinely contains unresolved uncertainty or explicitly uncertain outcomes.
- If evaluation completed and the input shows a mix of passing and failing outcomes without unresolved uncertainty,
  describe that as a partial pass, partial validation, or mixed result rather than as uncertainty.
- Write plain text only.
- Write one short paragraph of 3 sentences.
- No bullets, no markdown, no headings, no labels.
- Do not end with an ellipsis or an unfinished sentence.

Preferred sentence structure:
1. State the most important overall outcome in this domain.
2. Describe the main anomaly, weak point, or eyebrow-raising pattern and, if grounded in the input, the likely reason for it.
3. State why that matters for the user or what deserves follow-up attention.

Domain-specific guidance:
{domain_instructions}

DOMAIN: {json.dumps(domain)}
SUPPLY_CHAIN_PROFILE: {json.dumps(supply_chain_profile)}
DOMAIN_STATUS: {json.dumps(domain_status)}
DOMAIN_RESULT: {json.dumps(domain_result)}
EXISTING_EXPLANATION: {json.dumps(explanation)}
""".strip()

    def _compact_domain_summary_result(self, domain: str, domain_result: Dict[str, Any]) -> Dict[str, Any]:
        if domain != "compliance":
            return domain_result

        compact_regulations = self._compact_compliance_regulations(domain_result.get("regulations") or [])

        summary = domain_result.get("summary") or {}
        coverage = domain_result.get("coverage") or {}

        return {
            "status": domain_result.get("status"),
            "message": domain_result.get("message"),
            "summary": {
                "pass": summary.get("pass"),
                "fail": summary.get("fail"),
                "uncertain": summary.get("uncertain"),
                "not_applicable": summary.get("not_applicable"),
            },
            "coverage": {
                "nodesEvaluated": coverage.get("nodesEvaluated"),
                "nodesWithEvidence": coverage.get("nodesWithEvidence"),
                "totalNodes": coverage.get("totalNodes"),
            },
            "regulations": compact_regulations,
        }

    def _compact_domain_summary_status(self, domain: str, domain_status: Dict[str, Any]) -> Dict[str, Any]:
        if domain != "compliance":
            return domain_status

        summary = domain_status.get("summary") or {}
        observations = [
            " ".join(str(item).split())
            for item in (domain_status.get("observations") or [])[:6]
            if isinstance(item, str) and item.strip()
        ]
        detail = [
            " ".join(str(item).split())
            for item in (domain_status.get("detail") or [])[:6]
            if isinstance(item, str) and item.strip()
        ]

        return {
            "state": domain_status.get("state"),
            "score": domain_status.get("score"),
            "findings": domain_status.get("findings"),
            "summary": {
                "pass": summary.get("pass"),
                "fail": summary.get("fail"),
                "uncertain": summary.get("uncertain"),
                "not_applicable": summary.get("not_applicable"),
                "applicable": summary.get("applicable"),
                "total": summary.get("total"),
            },
            "detail": detail,
            "observations": observations,
        }

    def _compact_domain_summary_explanation(self, domain: str, explanation: Dict[str, Any]) -> Dict[str, Any]:
        if domain != "compliance":
            return explanation

        rules = [rule for rule in (explanation.get("rules") or []) if isinstance(rule, dict)]
        compact_rules = []
        for rule in rules[:12]:
            compact_rules.append(
                {
                    "id": rule.get("id"),
                    "llmExplanation": rule.get("llmExplanation"),
                    "missingEvidenceSummary": rule.get("missingEvidenceSummary"),
                    "managementImpact": rule.get("managementImpact"),
                }
            )

        return {"rules": compact_rules}

    def _compact_compliance_regulations(self, regulations: Any) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}

        for regulation in regulations or []:
            if not isinstance(regulation, dict):
                continue
            compact = self._compact_compliance_regulation(regulation)
            group_key = compact.get("id") or compact.get("shortName") or compact.get("title") or "regulation"
            existing = grouped.get(group_key)
            if existing is None:
                grouped[group_key] = compact
                continue
            self._merge_compact_compliance_regulation(existing, compact)

        return list(grouped.values())[:6]

    def _compact_compliance_regulation(self, regulation: Dict[str, Any]) -> Dict[str, Any]:
        regulation_meta = regulation.get("regulation") or {}
        summary = regulation.get("summary") or {}
        chapters = [chapter for chapter in (regulation.get("chapters") or []) if isinstance(chapter, dict)]

        failed_rules: List[Dict[str, Any]] = []
        uncertain_rules: List[Dict[str, Any]] = []
        for chapter in chapters:
            for rule in chapter.get("rules") or []:
                if not isinstance(rule, dict):
                    continue
                status = str(rule.get("status") or "")
                if status == "fail":
                    failed_rules.append(rule)
                elif status == "uncertain":
                    uncertain_rules.append(rule)

        representative_failures = []
        for rule in failed_rules[:2]:
            signal = self._format_compliance_rule_signal(rule)
            if signal:
                representative_failures.append(signal)

        representative_uncertainties = []
        for rule in uncertain_rules[:2]:
            signal = self._format_compliance_rule_signal(rule)
            if signal:
                representative_uncertainties.append(signal)

        return {
            "id": regulation_meta.get("id"),
            "shortName": regulation_meta.get("shortName"),
            "title": regulation_meta.get("title") or regulation_meta.get("citation"),
            "status": regulation.get("status"),
            "message": regulation.get("message"),
            "summary": {
                "pass": summary.get("pass"),
                "fail": summary.get("fail"),
                "uncertain": summary.get("uncertain"),
                "not_applicable": summary.get("not_applicable"),
                "applicable": summary.get("applicable"),
            },
            "topFailures": representative_failures,
            "topUncertainties": representative_uncertainties,
        }

    def _merge_compact_compliance_regulation(
        self,
        target: Dict[str, Any],
        incoming: Dict[str, Any],
    ) -> None:
        target_summary = target.get("summary") or {}
        incoming_summary = incoming.get("summary") or {}
        for key in ["pass", "fail", "uncertain", "not_applicable", "applicable"]:
            target_summary[key] = int(target_summary.get(key) or 0) + int(incoming_summary.get(key) or 0)
        target["summary"] = target_summary

        status_priority = {"fail": 3, "uncertain": 2, "not_applicable": 1, "pass": 0}
        target_status = str(target.get("status") or "")
        incoming_status = str(incoming.get("status") or "")
        if status_priority.get(incoming_status, -1) > status_priority.get(target_status, -1):
            target["status"] = incoming_status

        target_failures = list(target.get("topFailures") or [])
        for item in incoming.get("topFailures") or []:
            if item not in target_failures:
                target_failures.append(item)
        target["topFailures"] = target_failures[:3]

        target_uncertainties = list(target.get("topUncertainties") or [])
        for item in incoming.get("topUncertainties") or []:
            if item not in target_uncertainties:
                target_uncertainties.append(item)
        target["topUncertainties"] = target_uncertainties[:3]

        existing_message = " ".join(str(target.get("message") or "").split())
        incoming_message = " ".join(str(incoming.get("message") or "").split())
        if not existing_message and incoming_message:
            target["message"] = incoming_message

    def _format_compliance_rule_signal(self, rule: Dict[str, Any]) -> str:
        article = rule.get("articleRef") or rule.get("id")
        reason = " ".join(str(rule.get("reason") or "").strip().split())
        if not article and not reason:
            return ""
        if article and reason:
            return f"{article}: {reason}"
        return str(article or reason)

    def _domain_summary_guidance(self, domain: str) -> str:
        if domain == "technical":
            return """
- Prioritize whether the trust chain is intact.
- Focus on signatures, zero-knowledge proofs, anchors, provenance continuity, and governance consistency.
- If there is an anomaly, explain whether it is a hard verification failure or a narrower review signal.
- If the domain passed, emphasize that no deterministic technical failure was recorded and what that means for trust in the credential chain.
""".strip()

        if domain == "compliance":
            return """
- Think like a regulatory analyst reviewing structured rule outcomes.
- Treat each regulation as its own analytical unit.
- Write one sentence per regulation in scope, using the compact regulation summaries in the input rather than raw rule dumps.
- Prioritize repeated failed or uncertain rules, concentration within a regulation, and missing-evidence patterns.
- Mention whether the issue looks like one isolated article, a cluster of unresolved obligations, or a broad review-heavy result.
- If grounded in the input, point to the regulation or article families that dominate the uncertainty or non-compliance.
- When a regulation is mostly unresolved because applicability or evidence is missing, say that clearly instead of calling it a hard failure.
""".strip()

        if domain == "certification":
            return """
- Focus on certificate scope, expiry, suspension, missing matches, and whether any missing certification blocks approval.
- Prioritize the most consequential certification gap rather than listing every certificate.
- If grounded in the input, explain whether the issue is a scope mismatch, missing VC evidence, expiry, suspension, or incomplete renewal evidence.
- Make clear why the certification problem matters for the audited supply chain.
""".strip()

        if domain == "esg":
            return """
- Think in data-analytics terms over environmental, social, and governance signals.
- Prioritize score imbalance, the weakest sub-score, repeated flags, and any notable concentration of risk.
- If grounded in the input, mention what appears to drive the weak score, such as country risk, missing coverage, social incidents, or governance gaps.
- If the domain passed, still mention the most interesting residual pattern, such as an imbalance between sub-scores or a near-threshold weak area.
""".strip()

        return """
- Prioritize the most important signal in this domain and why it matters.
- Avoid repeating low-value details that are already obvious from the raw data.
""".strip()

    # Report Q&A helpers

    def _ask_with_openai(self, report: Any, question: str) -> str:
        prompt = f"""You are an expert supply-chain auditor assistant.
Answer the user's question based solely on the report data below.
Be concise, factual, and reference specific fields or failure codes where relevant.

REPORT (JSON):
{json.dumps(report)}

USER QUESTION:
{question}

Return plain text only."""
        return self._call_llm(prompt).strip()

    def _ask_with_openai_key(self, *, api_key: str, report: Any, question: str) -> str:
        prompt = f"""You are an expert supply-chain auditor assistant.
Answer the user's question based solely on the report data below.
Be concise, factual, and reference specific fields or failure codes where relevant.

REPORT (JSON):
{json.dumps(report)}

USER QUESTION:
{question}

Return plain text only."""

        from openai import OpenAI  # type: ignore

        model = os.getenv("OPENAI_MODEL_SUMMARY") or self.config.model
        client = OpenAI(api_key=api_key)
        resp = client.responses.create(
            model=model,
            temperature=self.config.temperature,
            input=prompt,
        )
        return resp.output_text.strip()

    # Transport and parsing

    def _call_llm(self, prompt: str) -> str:
        resp = self.client.responses.create(
            model=self.config.model,
            temperature=self.config.temperature,
            input=prompt,
        )
        return resp.output_text

    def _parse_json_object(self, text: str) -> Any:
        if not text:
            raise ValueError("Empty LLM response")
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("LLM did not return a JSON object")
        candidate = text[start : end + 1]
        return json.loads(candidate)

    # Validation helpers

    def _validate_technical_diagnoses(self, diagnoses: Any) -> List[Dict[str, Any]]:
        if not isinstance(diagnoses, list):
            return []

        validated: List[Dict[str, Any]] = []
        allowed_severity = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

        for item in diagnoses:
            if not isinstance(item, dict):
                continue
            failure_ref = item.get("failure_ref")
            severity = item.get("severity")
            explanation = item.get("explanation")
            remediation = item.get("remediation")
            confidence = item.get("confidence")

            if not isinstance(failure_ref, int):
                continue
            if severity not in allowed_severity:
                continue
            if not isinstance(explanation, str) or not explanation.strip():
                continue
            if not isinstance(remediation, list):
                continue

            remediation_items = [str(x).strip() for x in remediation if isinstance(x, str) and x.strip()]
            if not remediation_items:
                continue

            validated_item: Dict[str, Any] = {
                "failure_ref": failure_ref,
                "severity": severity,
                "explanation": explanation.strip(),
                "remediation": remediation_items[:5],
            }
            clamped_confidence = self._clamp_confidence(confidence)
            if clamped_confidence is not None:
                validated_item["confidence"] = clamped_confidence
            validated.append(validated_item)

        return validated

    def _validate_compliance_rules(self, rules: Any) -> List[Dict[str, Any]]:
        if not isinstance(rules, list):
            return []

        validated: List[Dict[str, Any]] = []
        for item in rules:
            if not isinstance(item, dict):
                continue
            rule_id = item.get("id")
            explanation = item.get("llmExplanation")
            if not isinstance(rule_id, str) or not rule_id.strip():
                continue
            if not isinstance(explanation, str) or not explanation.strip():
                continue

            validated_item: Dict[str, Any] = {
                "id": rule_id.strip(),
                "llmExplanation": explanation.strip(),
                "missingEvidenceSummary": self._clean_optional_text(item.get("missingEvidenceSummary")),
                "recommendedNextEvidence": self._clean_string_list(item.get("recommendedNextEvidence"), limit=6),
                "managementImpact": self._clean_optional_text(item.get("managementImpact")),
            }
            clamped_confidence = self._clamp_confidence(item.get("confidence"))
            if clamped_confidence is not None:
                validated_item["confidence"] = clamped_confidence
            validated.append(validated_item)

        return validated

    def _validate_esg_enrichment(self, raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            return {"llmExplanation": None, "primaryDrivers": [], "recommendedActions": []}

        out: Dict[str, Any] = {
            "llmExplanation": self._clean_optional_text(raw.get("llmExplanation")),
            "primaryDrivers": self._clean_string_list(raw.get("primaryDrivers"), limit=6),
            "recommendedActions": self._clean_string_list(raw.get("recommendedActions"), limit=8),
        }
        clamped_confidence = self._clamp_confidence(raw.get("confidence"))
        if clamped_confidence is not None:
            out["confidence"] = clamped_confidence
        return out

    def _validate_certification_findings(self, items: Any) -> List[Dict[str, Any]]:
        if not isinstance(items, list):
            return []

        validated: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = item.get("cid")
            cert_id = item.get("certificationId")
            explanation = item.get("llmExplanation")

            if not isinstance(cid, str) or not cid.strip():
                continue
            if not isinstance(cert_id, str) or not cert_id.strip():
                continue
            if not isinstance(explanation, str) or not explanation.strip():
                continue

            validated_item: Dict[str, Any] = {
                "cid": cid.strip(),
                "certificationId": cert_id.strip(),
                "llmExplanation": explanation.strip(),
                "recommendedEvidence": self._clean_string_list(item.get("recommendedEvidence"), limit=6),
                "recommendedActions": self._clean_string_list(item.get("recommendedActions"), limit=6),
            }
            clamped_confidence = self._clamp_confidence(item.get("confidence"))
            if clamped_confidence is not None:
                validated_item["confidence"] = clamped_confidence
            validated.append(validated_item)

        return validated

    def _clean_optional_text(self, value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None

    def _clean_string_list(self, value: Any, *, limit: int) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(x).strip() for x in value if isinstance(x, str) and x.strip()][:limit]

    def _clamp_confidence(self, value: Any) -> Optional[float]:
        if not isinstance(value, (int, float)):
            return None
        return max(0.0, min(1.0, float(value)))
