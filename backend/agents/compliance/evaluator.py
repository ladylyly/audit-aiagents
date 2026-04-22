from __future__ import annotations

import os
import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from backend.paths import COMPLIANCE_ASSETS_DIR


Rule = Dict[str, Any]
Rulepack = Dict[str, Any]


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _collect_vc_candidates(vc: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = [vc]
    claims = vc.get("claims") if isinstance(vc, dict) else None
    if isinstance(claims, dict):
        candidates.append(claims)

    subject = vc.get("credentialSubject") if isinstance(vc, dict) else None
    if isinstance(subject, dict):
        candidates.append(subject)
        subject_claims = subject.get("claims")
        if isinstance(subject_claims, dict):
            candidates.append(subject_claims)
        company = subject.get("company")
        if isinstance(company, dict):
            candidates.append(company)
        group = subject.get("group")
        if isinstance(group, dict):
            candidates.append(group)

    company = vc.get("company") if isinstance(vc, dict) else None
    if isinstance(company, dict):
        candidates.append(company)
    group = vc.get("group") if isinstance(vc, dict) else None
    if isinstance(group, dict):
        candidates.append(group)
    return candidates


def _parse_iso_date(value: Any) -> Optional[date]:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _as_number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_field(
    field: str,
    *,
    graph: Dict[str, Any],
    vcs_by_cid: Dict[str, Any],
    evaluation_input: Dict[str, Any],
    scope: str = "graph",
    current_cid: Optional[str] = None,
) -> Tuple[List[Any], List[Dict[str, Any]]]:
    values: List[Any] = []
    pointers: List[Dict[str, Any]] = []
    node_index_by_cid = graph.get("nodeIndexByCid") or {}

    def record(source: str, record_id: str, value: Any, node_cid: str | None = None) -> None:
        values.append(value)
        pointers.append(
            {
                "source": source,
                "field": field,
                "recordId": record_id,
                "nodeCid": node_cid,
                "nodeIndex": node_index_by_cid.get(node_cid) if node_cid else None,
            }
        )

    if scope == "node" and current_cid:
        items = [(current_cid, vcs_by_cid.get(current_cid))]
    else:
        items = list((vcs_by_cid or {}).items())

    if field.startswith("graph."):
        path = field[len("graph.") :]
        value = _get_path(graph, path)
        if value is not None:
            record("provenance", "graph", value, None)
        return values, pointers

    if field.startswith("input."):
        path = field[len("input.") :]
        value = _get_path(evaluation_input, path)
        if value is not None:
            record("input", "tool_input", value, None)
        return values, pointers

    if field.startswith("vc."):
        path = field[len("vc.") :]
        for cid, vc in items:
            for candidate in _collect_vc_candidates(vc):
                value = _get_path(candidate, path)
                if value is not None:
                    record(
                        "vc",
                        str(cid),
                        value,
                        _get_path(candidate, "credentialSubject.targetCid") or _get_path(candidate, "targetCid"),
                    )
        return values, pointers

    if field.startswith("company."):
        path = field[len("company.") :]
        for cid, vc in items:
            for candidate in _collect_vc_candidates(vc):
                value = _get_path(candidate, f"company.{path}")
                if value is None:
                    value = _get_path(candidate, path)
                if value is not None:
                    record(
                        "vc",
                        str(cid),
                        value,
                        _get_path(candidate, "credentialSubject.targetCid") or _get_path(candidate, "targetCid"),
                    )
        return values, pointers

    if field.startswith("group."):
        path = field[len("group.") :]
        for cid, vc in items:
            for candidate in _collect_vc_candidates(vc):
                value = _get_path(candidate, f"group.{path}")
                if value is None:
                    value = _get_path(candidate, path)
                if value is not None:
                    record(
                        "vc",
                        str(cid),
                        value,
                        _get_path(candidate, "credentialSubject.targetCid") or _get_path(candidate, "targetCid"),
                    )
        return values, pointers

    for cid, vc in items:
        for candidate in _collect_vc_candidates(vc):
            value = _get_path(candidate, field)
            if value is not None:
                record(
                    "vc",
                    str(cid),
                    value,
                    _get_path(candidate, "credentialSubject.targetCid") or _get_path(candidate, "targetCid"),
                )
    value = _get_path(graph, field)
    if value is not None:
        record("provenance", "graph", value, None)
    return values, pointers


def _pointer_key(pointer: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        pointer.get("source"),
        pointer.get("field"),
        pointer.get("recordId"),
        pointer.get("nodeCid"),
    )


def _merge_unique_pointers(*pointer_lists: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for pointer_list in pointer_lists:
        for pointer in pointer_list:
            key = _pointer_key(pointer)
            if key in seen:
                continue
            seen.add(key)
            merged.append(pointer)
    return merged


def _compare(value: Any, op: str, target: Any) -> Optional[bool]:
    try:
        if op == "date_on_or_after":
            value_date = _parse_iso_date(value)
            target_date = _parse_iso_date(target)
            if value_date is None or target_date is None:
                return None
            return value_date >= target_date
        if op == "date_before":
            value_date = _parse_iso_date(value)
            target_date = _parse_iso_date(target)
            if value_date is None or target_date is None:
                return None
            return value_date < target_date
        if op == "exists":
            return value is not None
        if op == "==":
            return value == target
        if op == "!=":
            return value != target
        if op == "not_in":
            return value not in (target or [])
        if op == ">":
            return float(value) > float(target)
        if op == ">=":
            return float(value) >= float(target)
        if op == "<":
            return float(value) < float(target)
        if op == "<=":
            return float(value) <= float(target)
        if op == "in":
            return value in (target or [])
        if op == "contains":
            return target in value
    except Exception:
        return None
    return None


def _evaluate_condition(
    cond: Dict[str, Any],
    *,
    graph: Dict[str, Any],
    vcs_by_cid: Dict[str, Any],
    evaluation_input: Dict[str, Any],
    scope: str = "graph",
    current_cid: Optional[str] = None,
) -> Optional[bool]:
    field = cond.get("field")
    op = cond.get("op")
    target = cond.get("value")
    if not field or not op:
        if not (
            cond.get("metric") == "ratio"
            or (cond.get("numeratorField") and cond.get("denominatorField"))
        ):
            return None

    values: List[Any] = []
    if field:
        values, _ = _resolve_field(
            field,
            graph=graph,
            vcs_by_cid=vcs_by_cid,
            evaluation_input=evaluation_input,
            scope=scope,
            current_cid=current_cid,
        )
    elif cond.get("metric") == "ratio" or (cond.get("numeratorField") and cond.get("denominatorField")):
        numerator_values, _ = _resolve_field(
            cond["numeratorField"],
            graph=graph,
            vcs_by_cid=vcs_by_cid,
            evaluation_input=evaluation_input,
            scope=scope,
            current_cid=current_cid,
        )
        denominator_values, _ = _resolve_field(
            cond["denominatorField"],
            graph=graph,
            vcs_by_cid=vcs_by_cid,
            evaluation_input=evaluation_input,
            scope=scope,
            current_cid=current_cid,
        )
        if not numerator_values or not denominator_values:
            return None

        numerator_numbers = [_as_number(value) for value in numerator_values]
        denominator_numbers = [_as_number(value) for value in denominator_values]
        if any(value is None for value in numerator_numbers + denominator_numbers):
            return None

        denominator_sum = sum(value for value in denominator_numbers if value is not None)
        if denominator_sum == 0:
            return None

        numerator_sum = sum(value for value in numerator_numbers if value is not None)
        multiplier = _as_number(cond.get("multiplier"))
        values = [(numerator_sum / denominator_sum) * (multiplier if multiplier is not None else 1.0)]

    if not values:
        return None

    saw_none = False
    for value in values:
        result = _compare(value, op, target)
        if result is True:
            return True
        if result is None:
            saw_none = True

    if saw_none:
        return None
    return False


def _evaluate_conditions_tree(
    tree: Dict[str, Any],
    *,
    graph: Dict[str, Any],
    vcs_by_cid: Dict[str, Any],
    evaluation_input: Dict[str, Any],
    scope: str = "graph",
    current_cid: Optional[str] = None,
) -> Optional[bool]:
    if not isinstance(tree, dict):
        return None

    if "all" in tree:
        results = []
        for cond in tree.get("all") or []:
            if isinstance(cond, dict) and ("all" in cond or "any" in cond):
                result = _evaluate_conditions_tree(
                    cond,
                    graph=graph,
                    vcs_by_cid=vcs_by_cid,
                    evaluation_input=evaluation_input,
                    scope=scope,
                    current_cid=current_cid,
                )
            else:
                result = _evaluate_condition(
                    cond,
                    graph=graph,
                    vcs_by_cid=vcs_by_cid,
                    evaluation_input=evaluation_input,
                    scope=scope,
                    current_cid=current_cid,
                )
            results.append(result)
        if any(result is None for result in results):
            return None
        return all(results)

    if "any" in tree:
        results = []
        for cond in tree.get("any") or []:
            if isinstance(cond, dict) and ("all" in cond or "any" in cond):
                result = _evaluate_conditions_tree(
                    cond,
                    graph=graph,
                    vcs_by_cid=vcs_by_cid,
                    evaluation_input=evaluation_input,
                    scope=scope,
                    current_cid=current_cid,
                )
            else:
                result = _evaluate_condition(
                    cond,
                    graph=graph,
                    vcs_by_cid=vcs_by_cid,
                    evaluation_input=evaluation_input,
                    scope=scope,
                    current_cid=current_cid,
                )
            results.append(result)
        if any(result is True for result in results):
            return True
        if any(result is None for result in results):
            return None
        return False

    return None


def _collect_fields_from_tree(tree: Any) -> List[str]:
    if not isinstance(tree, dict):
        return []
    if "field" in tree and isinstance(tree.get("field"), str):
        return [tree["field"]]
    if isinstance(tree.get("numeratorField"), str) and isinstance(tree.get("denominatorField"), str):
        return [tree["numeratorField"], tree["denominatorField"]]

    fields: List[str] = []
    for key in ("all", "any"):
        for child in tree.get(key) or []:
            fields.extend(_collect_fields_from_tree(child))
    return fields


def _default_rulepacks_dir() -> str:
    return os.fspath(COMPLIANCE_ASSETS_DIR / "rulepacks")


def _default_index_path() -> str:
    return os.path.join(_default_rulepacks_dir(), "index.yaml")


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_rulepack_index(path: Optional[str] = None) -> Dict[str, Any]:
    return _load_yaml(path or _default_index_path())


def _resolve_rulepack_path(index_path: str, relative_path: str) -> str:
    return os.path.normpath(os.path.join(os.path.dirname(index_path), relative_path))


def _infer_scope(rule: Rule) -> str:
    explicit = str(rule.get("scope") or "").strip().lower()
    if explicit in {"node", "graph"}:
        return explicit

    fields = list(rule.get("evidenceRequired") or [])
    fields.extend(_collect_fields_from_tree(rule.get("applicability")))
    fields.extend(_collect_fields_from_tree(rule.get("conditions")))
    graph_only_prefixes = ("graph.", "company.", "group.")
    if any(isinstance(field, str) and field.startswith(graph_only_prefixes) for field in fields):
        return "graph"
    return "node"


def _iter_selected_rulepack_paths(tool_input: Dict[str, Any]) -> List[str]:
    explicit_paths = tool_input.get("rulepackPaths")
    if isinstance(explicit_paths, list) and explicit_paths:
        return [str(path) for path in explicit_paths]

    explicit_path = tool_input.get("rulepackPath")
    if isinstance(explicit_path, str) and explicit_path.strip():
        return [explicit_path]

    index_path = tool_input.get("rulepackIndexPath") or _default_index_path()
    index = _load_rulepack_index(index_path)
    entries = index.get("rulepacks") or []

    requested_ids = tool_input.get("rulepackIds")
    if not requested_ids:
        requested_id = tool_input.get("rulepackId")
        if requested_id:
            requested_ids = [requested_id]

    selected_paths: List[str] = []
    for entry in entries:
        entry_id = entry.get("id")
        enabled = bool(entry.get("enabled", False))
        if requested_ids:
            if entry_id in requested_ids:
                selected_paths.append(_resolve_rulepack_path(index_path, entry["path"]))
        elif enabled:
            selected_paths.append(_resolve_rulepack_path(index_path, entry["path"]))
    return selected_paths


def _load_selected_rulepacks(tool_input: Dict[str, Any]) -> List[Dict[str, Any]]:
    packs: List[Dict[str, Any]] = []
    for path in _iter_selected_rulepack_paths(tool_input):
        pack = _load_yaml(path)
        pack["_sourcePath"] = path
        packs.append(pack)
    return packs


def _extract_article_number(article_ref: Optional[str]) -> Optional[int]:
    if not article_ref:
        return None
    match = re.search(r"Article\s+(\d+)", article_ref)
    if not match:
        return None
    return int(match.group(1))


def _resolve_chapter(rule: Rule, pack: Rulepack) -> Tuple[Optional[str], Optional[str]]:
    explicit_id = rule.get("chapterId")
    explicit_title = rule.get("chapterTitle")
    if explicit_id or explicit_title:
        return explicit_id, explicit_title

    article_number = _extract_article_number(rule.get("articleRef"))
    if article_number is None:
        return None, None

    for chapter in (pack.get("chapters") or []):
        start = chapter.get("articleStart")
        end = chapter.get("articleEnd")
        if isinstance(start, int) and isinstance(end, int) and start <= article_number <= end:
            return chapter.get("id"), chapter.get("title")
    return None, None


def _evaluate_applicability(
    rule: Rule,
    *,
    graph: Dict[str, Any],
    vcs_by_cid: Dict[str, Any],
    evaluation_input: Dict[str, Any],
    scope: str,
    current_cid: Optional[str] = None,
) -> Tuple[Optional[bool], List[Dict[str, Any]], List[str]]:
    tree = rule.get("applicability")
    if not tree:
        return True, [], []

    evidence_pointers: List[Dict[str, Any]] = []
    missing_fields: List[str] = []
    for field in _collect_fields_from_tree(tree):
        values, pointers = _resolve_field(
            field,
            graph=graph,
            vcs_by_cid=vcs_by_cid,
            evaluation_input=evaluation_input,
            scope=scope,
            current_cid=current_cid,
        )
        if values:
            evidence_pointers.extend(pointers)
        else:
            missing_fields.append(field)

    result = _evaluate_conditions_tree(
        tree,
        graph=graph,
        vcs_by_cid=vcs_by_cid,
        evaluation_input=evaluation_input,
        scope=scope,
        current_cid=current_cid,
    )
    return result, evidence_pointers, missing_fields


def _base_result(rule: Rule, pack: Rulepack) -> Dict[str, Any]:
    chapter_id, chapter_title = _resolve_chapter(rule, pack)
    return {
        "id": rule.get("id"),
        "articleRef": rule.get("articleRef"),
        "paragraphRef": rule.get("paragraphRef"),
        "title": rule.get("title"),
        "chapterId": chapter_id,
        "chapterTitle": chapter_title,
        "regulationId": (pack.get("regulation") or {}).get("id"),
        "regulationShortName": (pack.get("regulation") or {}).get("shortName"),
        "rulepackId": (pack.get("rulepack") or {}).get("id"),
        "encodable": bool(rule.get("encodable", True)),
        "encodabilityReason": rule.get("encodabilityReason"),
    }


def _evaluate_rule(
    rule: Rule,
    pack: Rulepack,
    *,
    graph: Dict[str, Any],
    vcs_by_cid: Dict[str, Any],
    evaluation_input: Dict[str, Any],
    current_cid: Optional[str] = None,
) -> Dict[str, Any]:
    result = _base_result(rule, pack)
    scope = _infer_scope(rule)
    result["scope"] = scope
    result["nodeCid"] = current_cid
    result["nodeIndex"] = (graph.get("nodeIndexByCid") or {}).get(current_cid) if current_cid else None

    if rule.get("entityLevel") is False:
        result.update(
            {
                "status": "not_applicable",
                "reason": rule.get("notApplicableReason")
                or "This provision is not a direct company-level obligation for entity-level compliance assessment.",
                "evidencePointers": [],
                "escalation": None,
            }
        )
        return result

    applicability_result, applicability_pointers, applicability_missing = _evaluate_applicability(
        rule,
        graph=graph,
        vcs_by_cid=vcs_by_cid,
        evaluation_input=evaluation_input,
        scope=scope,
        current_cid=current_cid,
    )
    if applicability_result is False:
        result.update(
            {
                "status": "not_applicable",
                "reason": "Applicability conditions not met",
                "evidencePointers": applicability_pointers,
                "escalation": None,
            }
        )
        return result

    if applicability_result is None:
        result.update(
            {
                "status": "uncertain",
                "reason": f"Missing applicability evidence: {', '.join(applicability_missing)}",
                "evidencePointers": applicability_pointers,
                "escalation": {
                    "needsManualReview": True,
                    "llmSuggestion": "Resolve applicability evidence before determining whether this obligation applies.",
                    "reason": "missing applicability evidence",
                },
            }
        )
        return result

    encodable = result["encodable"]
    if not encodable:
        result.update(
            {
                "status": "uncertain",
                "reason": "Not fully encodable",
                "evidencePointers": applicability_pointers,
                "escalation": {
                    "needsManualReview": True,
                    "llmSuggestion": "Provide a legal interpretation and identify required evidence.",
                    "reason": result["encodabilityReason"] or "requires legal interpretation",
                },
            }
        )
        return result

    evidence_required = rule.get("evidenceRequired") or []
    evidence_pointers: List[Dict[str, Any]] = []
    missing_fields: List[str] = []
    for field in evidence_required:
        values, pointers = _resolve_field(
            field,
            graph=graph,
            vcs_by_cid=vcs_by_cid,
            evaluation_input=evaluation_input,
            scope=scope,
            current_cid=current_cid,
        )
        if values:
            evidence_pointers.extend(pointers)
        else:
            missing_fields.append(field)

    all_pointers = _merge_unique_pointers(applicability_pointers, evidence_pointers)
    check_type = rule.get("checkType") or "presence"
    conditions = rule.get("conditions")

    if conditions:
        condition_pointers: List[Dict[str, Any]] = []
        for field in _collect_fields_from_tree(conditions):
            _, pointers = _resolve_field(
                field,
                graph=graph,
                vcs_by_cid=vcs_by_cid,
                evaluation_input=evaluation_input,
                scope=scope,
                current_cid=current_cid,
            )
            condition_pointers.extend(pointers)
        all_pointers = _merge_unique_pointers(all_pointers, condition_pointers)

        cond_result = _evaluate_conditions_tree(
            conditions,
            graph=graph,
            vcs_by_cid=vcs_by_cid,
            evaluation_input=evaluation_input,
            scope=scope,
            current_cid=current_cid,
        )
        if cond_result is None:
            result.update(
                {
                    "status": "uncertain",
                    "reason": "Missing evidence for condition evaluation",
                    "evidencePointers": all_pointers,
                    "escalation": {
                        "needsManualReview": True,
                        "llmSuggestion": "Resolve missing evidence and reassess conditions.",
                        "reason": "missing evidence",
                    },
                }
            )
            return result

        false_status = "fail"
        false_reason = "Conditions not satisfied"
        if rule.get("obligationType") == "scope_gate":
            false_status = "not_applicable"
            false_reason = "Scope gate conditions not met"

        result.update(
            {
                "status": "pass" if cond_result else false_status,
                "reason": "Conditions satisfied" if cond_result else false_reason,
                "evidencePointers": all_pointers,
                "escalation": None,
            }
        )
        return result

    if check_type == "boolean":
        if missing_fields:
            result.update(
                {
                    "status": "uncertain",
                    "reason": f"Missing evidence: {', '.join(missing_fields)}",
                    "evidencePointers": all_pointers,
                    "escalation": {
                        "needsManualReview": True,
                        "llmSuggestion": "Provide the missing boolean evidence.",
                        "reason": "missing evidence",
                    },
                }
            )
            return result

        failed_fields: List[str] = []
        for field in evidence_required:
            values, _ = _resolve_field(
                field,
                graph=graph,
                vcs_by_cid=vcs_by_cid,
                evaluation_input=evaluation_input,
                scope=scope,
                current_cid=current_cid,
            )
            if values and not any(value is True for value in values):
                failed_fields.append(field)

        if failed_fields:
            result.update(
                {
                    "status": "fail",
                    "reason": f"Explicit false or unsatisfied boolean evidence: {', '.join(failed_fields)}",
                    "evidencePointers": all_pointers,
                    "escalation": None,
                }
            )
            return result

        result.update(
            {
                "status": "pass",
                "reason": "All required evidence is true",
                "evidencePointers": all_pointers,
                "escalation": None,
            }
        )
        return result

    if missing_fields:
        result.update(
            {
                "status": "uncertain",
                "reason": f"Missing evidence: {', '.join(missing_fields)}",
                "evidencePointers": all_pointers,
                "escalation": {
                    "needsManualReview": True,
                    "llmSuggestion": "Provide the missing evidence and re-run compliance checks.",
                    "reason": "missing evidence",
                },
            }
        )
        return result

    result.update(
        {
            "status": "pass",
            "reason": "All required evidence present",
            "evidencePointers": all_pointers,
            "escalation": None,
        }
    )
    return result


def _status_summary(results: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"pass": 0, "fail": 0, "uncertain": 0, "not_applicable": 0}
    for result in results:
        status = result.get("status") or "uncertain"
        if status not in summary:
            status = "uncertain"
        summary[status] += 1
    summary["applicable"] = summary["pass"] + summary["fail"] + summary["uncertain"]
    summary["total"] = summary["applicable"] + summary["not_applicable"]
    return summary


def _coverage(summary: Dict[str, int]) -> Dict[str, Any]:
    total = int(summary.get("total", 0))
    applicable = int(summary.get("applicable", 0))
    return {
        "applicableRules": applicable,
        "notApplicableRules": int(summary.get("not_applicable", 0)),
        "totalRules": total,
        "applicabilityRatio": (applicable / total) if total else 0.0,
    }


def _overall_status(summary: Dict[str, int]) -> str:
    applicable_count = summary.get("pass", 0) + summary.get("fail", 0) + summary.get("uncertain", 0)
    if applicable_count == 0:
        return "not_applicable"
    if summary.get("fail", 0) > 0:
        return "fail"
    if summary.get("uncertain", 0) > 0:
        return "uncertain"
    return "pass"


def _group_results_by_chapter(results: List[Dict[str, Any]], pack: Rulepack) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for result in results:
        key = (result.get("chapterId") or "unmapped", result.get("chapterTitle") or "Unmapped")
        grouped.setdefault(key, []).append(result)

    chapter_order = {
        chapter.get("id"): index for index, chapter in enumerate(pack.get("chapters") or [])
    }
    chapter_results: List[Dict[str, Any]] = []
    for (chapter_id, chapter_title), chapter_rules in grouped.items():
        summary = _status_summary(chapter_rules)
        status = _overall_status(summary)
        chapter_results.append(
            {
                "id": chapter_id,
                "title": chapter_title,
                "status": status,
                "applicable": status != "not_applicable",
                "applicabilityExplanation": (
                    "No applicable rules in this chapter for the available supply-chain evidence."
                    if status == "not_applicable"
                    else "At least one rule in this chapter was applicable."
                ),
                "summary": summary,
                "coverage": _coverage(summary),
                "rules": chapter_rules,
            }
        )
    return sorted(
        chapter_results,
        key=lambda item: (chapter_order.get(item["id"], 10_000), item["title"]),
    )


def _regulation_message(status: str, short_name: str) -> str:
    if status == "fail":
        return f"{short_name} checks failed."
    if status == "uncertain":
        return f"{short_name} checks require manual review."
    if status == "not_applicable":
        return f"{short_name} was not applicable to the available evidence."
    return f"{short_name} checks passed."


def _status_rank(status: str) -> int:
    order = {
        "fail": 0,
        "uncertain": 1,
        "pass": 2,
        "not_applicable": 3,
    }
    return order.get(status or "uncertain", 1)


def _aggregate_rule_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(str(result.get("id")), []).append(result)

    aggregate: List[Dict[str, Any]] = []
    for rule_id, variants in grouped.items():
        ordered = sorted(variants, key=lambda item: _status_rank(str(item.get("status"))))
        selected = dict(ordered[0])
        selected["nodeOutcomes"] = [
            {
                "nodeCid": item.get("nodeCid"),
                "nodeIndex": item.get("nodeIndex"),
                "status": item.get("status"),
                "reason": item.get("reason"),
            }
            for item in variants
        ]
        aggregate.append(selected)
    return aggregate


def evaluate_compliance(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    root_cid = tool_input.get("rootCid")
    graph = tool_input.get("graph") or {}
    vcs_by_cid = tool_input.get("vcsByCid") or {}
    evaluation_input = tool_input

    packs = _load_selected_rulepacks(tool_input)
    if not packs:
        raise FileNotFoundError("No compliance rulepacks selected or enabled.")

    graph_node_ids = [
        str(node.get("cid"))
        for node in (graph.get("nodes") or [])
        if isinstance(node, dict) and node.get("cid")
    ]

    all_rules: List[Dict[str, Any]] = []
    regulations: List[Dict[str, Any]] = []
    node_results: List[Dict[str, Any]] = []

    for pack in packs:
        pack_rules = pack.get("rules") or []
        pack_node_rules: List[Dict[str, Any]] = []

        for rule in pack_rules:
            scope = _infer_scope(rule)
            if scope == "graph":
                pack_node_rules.append(
                    _evaluate_rule(
                        rule,
                        pack,
                        graph=graph,
                        vcs_by_cid=vcs_by_cid,
                        evaluation_input=evaluation_input,
                    )
                )
                continue

            for cid in graph_node_ids:
                scoped_vcs = {cid: vcs_by_cid.get(cid)} if cid in vcs_by_cid else {}
                result = _evaluate_rule(
                    rule,
                    pack,
                    graph=graph,
                    vcs_by_cid=scoped_vcs,
                    evaluation_input=evaluation_input,
                    current_cid=cid,
                )
                pack_node_rules.append(result)

        evaluated_rules = _aggregate_rule_results(pack_node_rules)
        chapter_results = _group_results_by_chapter(evaluated_rules, pack)
        summary = _status_summary(evaluated_rules)
        status = _overall_status(summary)

        regulation_info = pack.get("regulation") or {}
        rulepack_info = pack.get("rulepack") or {}

        regulations.append(
            {
                "regulation": regulation_info,
                "rulepack": {
                    "id": rulepack_info.get("id"),
                    "version": rulepack_info.get("version"),
                    "status": rulepack_info.get("status"),
                    "sourcePath": pack.get("_sourcePath"),
                },
                "status": status,
                "applicable": status != "not_applicable",
                "applicabilityExplanation": (
                    "No rules in this regulation were applicable to the available evidence."
                    if status == "not_applicable"
                    else "At least one obligation in this regulation was applicable."
                ),
                "message": _regulation_message(status, regulation_info.get("shortName") or rulepack_info.get("id") or "Rulepack"),
                "summary": summary,
                "coverage": _coverage(summary),
                "chapters": chapter_results,
                "rules": evaluated_rules,
            }
        )
        all_rules.extend(evaluated_rules)

        for cid in graph_node_ids:
            node_rule_results = [
                result
                for result in pack_node_rules
                if result.get("nodeCid") == cid and result.get("scope") == "node"
            ]
            node_summary = _status_summary(node_rule_results)
            node_results.append(
                {
                    "cid": cid,
                    "nodeIndex": (graph.get("nodeIndexByCid") or {}).get(cid),
                    "rulepackId": rulepack_info.get("id"),
                    "regulationId": regulation_info.get("id"),
                    "summary": node_summary,
                    "coverage": _coverage(node_summary),
                    "status": _overall_status(node_summary),
                    "rules": node_rule_results,
                }
            )

    overall_summary = _status_summary(all_rules)
    overall_status = _overall_status(overall_summary)
    success: Optional[bool]
    if overall_status == "fail":
        success = False
    elif overall_status == "uncertain":
        success = None
    else:
        success = True

    message = "Compliance verification completed."
    if overall_status == "fail":
        message = "Compliance verification failed."
    elif overall_status == "uncertain":
        message = "Compliance verification requires manual review."
    elif overall_status == "not_applicable":
        message = "No applicable compliance obligations were triggered."

    return {
        "status": "done",
        "success": success,
        "message": message,
        "rules": all_rules,
        "summary": overall_summary,
        "coverage": _coverage(overall_summary),
        "regulations": regulations,
        "nodeResults": node_results,
        "meta": {
            "rootCid": root_cid,
            "rulepackIds": [reg["rulepack"]["id"] for reg in regulations],
            "rulepackVersions": [reg["rulepack"]["version"] for reg in regulations],
        },
    }
