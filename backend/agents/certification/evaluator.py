from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from backend.paths import CERTIFICATION_ASSETS_DIR


def _get_path(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _normalize_name(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split()) or None


def _normalize_tag(value: Any) -> Optional[str]:
    normalized = _normalize_name(value)
    return normalized.replace(" ", "_") if normalized else None


def _normalize_tags(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        normalized = _normalize_tag(value)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def _load_catalog(path: Optional[str] = None) -> Dict[str, Any]:
    if not path:
        path = os.fspath(CERTIFICATION_ASSETS_DIR / "catalog" / "certifications.v1.yaml")
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _collect_certification_records(vc: Dict[str, Any]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    subject = vc.get("credentialSubject") if isinstance(vc, dict) else None
    if not isinstance(subject, dict):
        return records

    certifications = subject.get("certifications")
    has_explicit_certifications = False
    if isinstance(certifications, list):
        for idx, cert in enumerate(certifications):
            if not isinstance(cert, dict):
                continue
            name = cert.get("name")
            if name is None:
                continue
            has_explicit_certifications = True
            records.append(
                {
                    "path": f"credentialSubject.certifications[{idx}].name",
                    "value": str(name),
                    "details": cert,
                }
            )

    singleton = subject.get("certificateCredential")
    if not has_explicit_certifications and isinstance(singleton, dict) and singleton.get("name") is not None:
        records.append(
            {
                "path": "credentialSubject.certificateCredential.name",
                "value": str(singleton.get("name")),
                "details": singleton,
            }
        )

    subject_claims = subject.get("claims")
    if isinstance(subject_claims, dict):
        claim_certifications = subject_claims.get("certifications")
        if isinstance(claim_certifications, list):
            for idx, cert in enumerate(claim_certifications):
                if not isinstance(cert, dict) or cert.get("name") is None:
                    continue
                records.append(
                    {
                        "path": f"credentialSubject.claims.certifications[{idx}].name",
                        "value": str(cert.get("name")),
                        "details": cert,
                    }
                )

    listing = subject.get("listing")
    if isinstance(listing, dict):
        listing_cert = listing.get("certificateCredential")
        if isinstance(listing_cert, dict) and listing_cert.get("name") is not None:
            records.append(
                {
                    "path": "credentialSubject.listing.certificateCredential.name",
                    "value": str(listing_cert.get("name")),
                    "details": listing_cert,
                }
            )

    return records


def _extract_metadata(vc: Dict[str, Any]) -> Dict[str, Any]:
    subject = vc.get("credentialSubject") if isinstance(vc, dict) else None
    if not isinstance(subject, dict):
        return {"facilityRole": None, "materialTags": [], "operationTags": []}
    return {
        "facilityRole": _normalize_tag(subject.get("facilityRole")),
        "materialTags": _normalize_tags(subject.get("materialTags")),
        "operationTags": _normalize_tags(subject.get("operationTags")),
    }


def _matches_evidence_path(record_path: str, evidence_path: str) -> bool:
    if evidence_path == record_path:
        return True
    if evidence_path.endswith("[*].name"):
        prefix = evidence_path[:-len("[*].name")]
        return record_path.startswith(prefix) and record_path.endswith("].name")
    return False


def _match_records(records: List[Dict[str, Any]], certification: Dict[str, Any]) -> List[Dict[str, Any]]:
    aliases = {_normalize_name(alias) for alias in certification.get("aliases") or []}
    aliases.add(_normalize_name(certification.get("displayName")))
    aliases = {alias for alias in aliases if alias}
    allowed_paths = certification.get("evidencePaths") or []

    matches: List[Dict[str, Any]] = []
    for record in records:
        record_name = _normalize_name(record.get("value"))
        if not record_name or record_name not in aliases:
            continue
        if allowed_paths and not any(_matches_evidence_path(str(record.get("path")), str(path)) for path in allowed_paths):
            continue
        matches.append(record)
    return matches


def _evaluate_applicability(certification: Dict[str, Any], metadata: Dict[str, Any]) -> Tuple[Optional[bool], Optional[str]]:
    role_requirements = [_normalize_tag(value) for value in certification.get("applicableFacilityRoles") or [] if value]
    material_requirements = [_normalize_tag(value) for value in certification.get("applicableMaterialTags") or [] if value]
    operation_requirements = [_normalize_tag(value) for value in certification.get("applicableOperationTags") or [] if value]

    facility_role = metadata.get("facilityRole")
    material_tags = metadata.get("materialTags") or []
    operation_tags = metadata.get("operationTags") or []

    if role_requirements:
        if not facility_role or facility_role == "unknown":
            return None, "Missing facilityRole metadata"
        if facility_role not in role_requirements:
            return False, f"facilityRole={facility_role} is outside certification scope"

    if material_requirements:
        if not material_tags:
            return None, "Missing materialTags metadata"
        if not any(tag in material_tags for tag in material_requirements):
            return False, "materialTags do not match certification scope"

    if operation_requirements:
        if not operation_tags:
            return None, "Missing operationTags metadata"
        if not any(tag in operation_tags for tag in operation_requirements):
            return False, "operationTags do not match certification scope"

    return True, "Certification is applicable to this node"


def _evaluate_technical_credibility(cid: str, technical_result: Optional[Dict[str, Any]]) -> Tuple[Optional[bool], str]:
    if not isinstance(technical_result, dict):
        return None, "Technical verification result missing"

    evidence = technical_result.get("evidence")
    if not isinstance(evidence, dict):
        return None, "Technical verification evidence missing"

    signature_results = _get_path(evidence, "signatures.results")
    if not isinstance(signature_results, dict):
        return None, "Signature verification results missing"

    signature_result = signature_results.get(cid)
    if not isinstance(signature_result, dict):
        return None, "No signature verification result for CID"
    if signature_result.get("success") is not True:
        return False, "VC signature verification failed"

    current_anchor = evidence.get("currentAnchor")
    if isinstance(current_anchor, dict) and current_anchor.get("skipped") is not True:
        current_failures = {
            str(item.get("cid"))
            for item in (current_anchor.get("failed") or [])
            if isinstance(item, dict) and item.get("cid")
        }
        if current_anchor.get("verified") is False and cid in current_failures:
            return False, "Root VC anchor verification failed"
        if current_anchor.get("verified") is None:
            return None, "Root VC anchor result missing"

    chain_anchors = evidence.get("chainAnchors")
    if isinstance(chain_anchors, dict) and chain_anchors.get("skipped") is not True:
        chain_failures = {
            str(item.get("cid"))
            for item in (chain_anchors.get("failed") or [])
            if isinstance(item, dict) and item.get("cid")
        }
        if chain_anchors.get("verified") is False and cid in chain_failures:
            return False, "Chain anchor verification failed"
        if chain_anchors.get("verified") is None:
            return None, "Chain anchor result missing"

    return True, "Technical verification evidence supports this certification"


def _build_claims(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    for finding in findings:
        cid = finding.get("cid")
        certification_id = finding.get("certificationId")
        claims.append(
            {
                "type": "certification.detected",
                "cid": cid,
                "certificationId": certification_id,
                "verified": finding.get("foundOnAnyNode"),
                "status": finding.get("status"),
            }
        )
        claims.append(
            {
                "type": "certification.applicable",
                "cid": cid,
                "certificationId": certification_id,
                "verified": (finding.get("applicableNodeCount") or 0) > 0,
                "status": finding.get("status"),
            }
        )
        claims.append(
            {
                "type": "certification.technically_credible",
                "cid": cid,
                "certificationId": certification_id,
                "verified": finding.get("status") == "pass",
                "status": finding.get("status"),
            }
        )
    return claims

def _normalize_result_status(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip().lower()
    if text == "warning":
        return "uncertain"
    if text in {"pass", "fail", "uncertain", "not_applicable"}:
        return text
    return fallback


def _derive_failure_type(finding: Dict[str, Any]) -> str:
    status = finding.get("status")
    finding_type = finding.get("findingType")
    if status == "pass":
        return "none"
    if finding_type == "scope_mismatch":
        return "scope_mismatch"
    if finding_type == "missing_required":
        return "absence"
    if finding.get("technicallyCredible") is False:
        return "technical_invalidity"
    if status == "uncertain":
        return "insufficient_evidence"
    if status == "not_applicable":
        return "not_applicable"
    return "other"


def evaluate_certifications(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    root_cid = tool_input.get("rootCid")
    graph = tool_input.get("graph") or {}
    vcs_by_cid = tool_input.get("vcsByCid") or {}
    technical_result = tool_input.get("technicalResult")
    catalog_doc = _load_catalog(tool_input.get("catalogPath"))
    certifications = catalog_doc.get("certifications") or []
    node_index_by_cid = graph.get("nodeIndexByCid") or {}

    findings: List[Dict[str, Any]] = []
    summary = {"pass": 0, "fail": 0, "uncertain": 0, "not_applicable": 0}
    node_results: List[Dict[str, Any]] = []
    if not vcs_by_cid:
        catalog_meta = catalog_doc.get("catalog") or {}
        return {
            "status": "done",
            "success": None,
            "message": "Certification verification requires more evidence.",
            "summary": summary,
            "findings": findings,
            "nodeResults": node_results,
            "claims": [],
            "meta": {
                "rootCid": root_cid,
                "catalogId": catalog_meta.get("id"),
                "catalogVersion": catalog_meta.get("version"),
                "reason": "No VC nodes were available for certification evaluation.",
            },
        }

    evaluations_by_certification: Dict[str, List[Dict[str, Any]]] = {}
    for certification in certifications:
        certification_id = str(certification.get("id") or "")
        if certification_id:
            evaluations_by_certification[certification_id] = []

    for cid, vc in vcs_by_cid.items():
        if not isinstance(vc, dict):
            continue
        metadata = _extract_metadata(vc)
        records = _collect_certification_records(vc)
        node_findings: List[Dict[str, Any]] = []

        for certification in certifications:
            certification_id = str(certification.get("id") or "")
            matches = _match_records(records, certification)
            applicable, applicability_reason = _evaluate_applicability(certification, metadata)
            found = len(matches) > 0
            missing_status = _normalize_result_status(certification.get("missingStatus"), fallback="fail")
            scope_mismatch_status = _normalize_result_status(certification.get("scopeMismatchStatus"), fallback="fail")
            technically_credible: Optional[bool] = None
            technical_reason: Optional[str] = None
            if applicable is True and found:
                technically_credible, technical_reason = _evaluate_technical_credibility(str(cid), technical_result)

            warning: Optional[str] = None
            if applicable is True and found and technically_credible is True:
                status = "pass"
                finding_type = "present"
                reason = "Certification is applicable to this node. Certification evidence found in VC."
            elif applicable is True and found:
                status = "pass"
                finding_type = "present"
                warning = (
                    "This VC is not technically verifiable. "
                    f"{technical_reason or 'Technical verification evidence is missing.'}"
                )
                reason = (
                    "Certification is applicable to this node. Certification evidence found in VC."
                )
            elif applicable is True:
                status = missing_status
                finding_type = "missing_required"
                reason = "Certification is applicable to this node. No applicable certification evidence found."
            elif applicable is False and found:
                status = scope_mismatch_status
                finding_type = "scope_mismatch"
                reason = f"{applicability_reason}. Certification is present on a node outside its expected scope."
            elif applicable is None:
                status = "uncertain"
                finding_type = "uncertain"
                reason = str(applicability_reason or "Certification applicability could not be determined.")
            else:
                status = "not_applicable"
                finding_type = "not_applicable"
                reason = str(applicability_reason or "Certification is outside this node's scope.")

            evidence_pointers = [
                {
                    "source": "vc",
                    "field": match.get("path"),
                    "recordId": str(cid),
                    "nodeCid": str(cid),
                    "value": match.get("value"),
                }
                for match in matches
            ]

            node_finding = {
                "cid": str(cid),
                "nodeIndex": node_index_by_cid.get(str(cid)),
                "certificationId": certification.get("id"),
                "displayName": certification.get("displayName"),
                "applicable": applicable,
                "found": found,
                "technicallyCredible": technically_credible,
                "status": status,
                "findingType": finding_type,
                "failureType": "none",
                "evidencePointers": evidence_pointers,
                "reason": reason,
                "warning": warning,
            }
            node_finding["failureType"] = _derive_failure_type(node_finding)
            node_findings.append(node_finding)
            if certification_id:
                evaluations_by_certification[certification_id].append(node_finding)

        node_state = "not_applicable"
        if any(f.get("status") == "pass" for f in node_findings):
            node_state = "pass"
        elif any(f.get("status") == "fail" for f in node_findings):
            node_state = "fail"
        elif any(f.get("status") == "uncertain" for f in node_findings):
            node_state = "uncertain"
        node_results.append(
            {
                "cid": str(cid),
                "nodeIndex": node_index_by_cid.get(str(cid)),
                "status": node_state,
                "findings": node_findings,
            }
        )

    for certification in certifications:
        certification_id = str(certification.get("id") or "")
        node_findings = evaluations_by_certification.get(certification_id, [])
        pass_nodes = [item for item in node_findings if item.get("status") == "pass"]
        applicable_nodes = [item for item in node_findings if item.get("applicable") is True]
        uncertain_nodes = [item for item in node_findings if item.get("status") == "uncertain"]
        scope_nodes = [item for item in node_findings if item.get("findingType") == "scope_mismatch"]
        found_nodes = [item for item in node_findings if item.get("found")]
        technical_warning_nodes = [item for item in node_findings if item.get("warning")]

        representative = pass_nodes[0] if pass_nodes else applicable_nodes[0] if applicable_nodes else found_nodes[0] if found_nodes else uncertain_nodes[0] if uncertain_nodes else node_findings[0] if node_findings else None

        evidence_pointers = []
        for item in pass_nodes[:5]:
            evidence_pointers.extend(item.get("evidencePointers") or [])

        if pass_nodes:
            status = "pass"
            reason = f"Validated on {len(pass_nodes)} VC node{'s' if len(pass_nodes) != 1 else ''} in the supply chain."
            missing_applicable_count = len([item for item in applicable_nodes if item.get("status") == "fail"])
            technical_warning_count = len(technical_warning_nodes)
            if missing_applicable_count > 0:
                reason += f" {missing_applicable_count} other applicable VC node{'s' if missing_applicable_count != 1 else ''} did not contain matching certification evidence."
            if technical_warning_count > 0:
                reason += f" Warning: {technical_warning_count} supporting VC node{'s' if technical_warning_count != 1 else ''} are not technically verifiable."
            finding_type = "present"
            failure_type = "none"
        elif applicable_nodes:
            failed_applicable = [item for item in applicable_nodes if item.get("status") == "fail"]
            if uncertain_nodes and not failed_applicable:
                status = "uncertain"
                reason = f"Applicable on {len(applicable_nodes)} VC node{'s' if len(applicable_nodes) != 1 else ''}, but validation is incomplete because required metadata or evidence is missing."
                finding_type = "uncertain"
                failure_type = "insufficient_evidence"
            else:
                status = "fail"
                reason = f"Applicable on {len(applicable_nodes)} VC node{'s' if len(applicable_nodes) != 1 else ''}, but none contained matching certification evidence."
                finding_type = "missing_required"
                failure_type = "absence"
        elif uncertain_nodes:
            status = "uncertain"
            reason = f"No VC could be confirmed as applicable because certification scope metadata is incomplete on {len(uncertain_nodes)} node{'s' if len(uncertain_nodes) != 1 else ''}."
            finding_type = "uncertain"
            failure_type = "insufficient_evidence"
        elif scope_nodes:
            status = "fail"
            reason = f"Certification evidence was found on {len(scope_nodes)} VC node{'s' if len(scope_nodes) != 1 else ''}, but only outside the certification scope."
            finding_type = "scope_mismatch"
            failure_type = "scope_mismatch"
        else:
            status = "fail"
            reason = "No VC in this supply chain matched the certification scope, and no valid certification evidence was found."
            finding_type = "missing_required"
            failure_type = "absence"

        summary[status] += 1
        findings.append(
            {
                "cid": str((representative or {}).get("cid") or root_cid or ""),
                "nodeIndex": (representative or {}).get("nodeIndex"),
                "certificationId": certification.get("id"),
                "displayName": certification.get("displayName"),
                "status": status,
                "reason": reason,
                "findingType": finding_type,
                "failureType": failure_type,
                "foundOnAnyNode": len(found_nodes) > 0,
                "applicableNodeCount": len(applicable_nodes),
                "passingNodeCount": len(pass_nodes),
                "uncertainNodeCount": len(uncertain_nodes),
                "scopeMismatchNodeCount": len(scope_nodes),
                "technicalWarningNodeCount": len(technical_warning_nodes),
                "matchedNodeCount": len(found_nodes),
                "passedCids": [str(item.get("cid")) for item in pass_nodes[:5] if item.get("cid")],
                "applicableCids": [str(item.get("cid")) for item in applicable_nodes[:10] if item.get("cid")],
                "evidencePointers": evidence_pointers[:10],
                "warnings": [str(item.get("warning")) for item in technical_warning_nodes if item.get("warning")][:10],
                "sampleFindings": node_findings[:10],
            }
        )

    success: Optional[bool]
    if summary["uncertain"] > 0 and summary["fail"] == 0:
        success = None
    else:
        success = summary["fail"] == 0 and summary["uncertain"] == 0 and summary["pass"] == len(certifications)

    message = "Certification verification completed."
    if success is False:
        message = "Certification verification found applicable certification gaps."
    elif success is None:
        message = "Certification verification requires more evidence."

    catalog_meta = catalog_doc.get("catalog") or {}
    return {
        "status": "done",
        "success": success,
        "message": message,
        "summary": summary,
        "findings": findings,
        "nodeResults": node_results,
        "claims": _build_claims(findings),
        "meta": {
            "rootCid": root_cid,
            "catalogId": catalog_meta.get("id"),
            "catalogVersion": catalog_meta.get("version"),
        },
    }
