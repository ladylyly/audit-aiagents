# Flask API for audit runs, stored reports, and report Q&A

import json
import logging
import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from backend.agents.orchestrator.orchestrator import create_orchestrator_from_env
from backend.integrations.llm_client import LLMClient
from backend.paths import BACKEND_ENV_PATH, DATA_REPORTS_DIR
from backend.services.ipfs_fetcher import IpfsFetchConfig, IpfsFetcher

load_dotenv(BACKEND_ENV_PATH)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("audit-api")

app = Flask(__name__)
CORS(app)

_reports: Dict[str, Dict[str, Any]] = {}
_reports_lock = threading.Lock()
_reports_dir = DATA_REPORTS_DIR
_reports_dir.mkdir(parents=True, exist_ok=True)
_graph_cache: Dict[str, Dict[str, Any]] = {}
_graph_cache_lock = threading.Lock()
_vc_cache: Dict[str, Dict[str, Any]] = {}
_vc_cache_lock = threading.Lock()

_llm: Optional[Any] = None
_llm_lock = threading.Lock()


def _get_llm():
    global _llm
    with _llm_lock:
        if _llm is None:
            _llm = LLMClient()
    return _llm


def _run_orchestrator(report_id: str, root_cid: str) -> None:
    """Run the orchestrator in a background thread and store the result."""
    def progress_callback(progress: Dict[str, Any]) -> None:
        current_step = progress.get("currentStep")
        step_info = (progress.get("steps") or {}).get(current_step) if current_step else None
        if isinstance(step_info, dict):
            label = step_info.get("label") or current_step
            status = step_info.get("status")
            detail = step_info.get("detail")
            logger.info(
                "report=%s step=%s status=%s detail=%s",
                report_id,
                label,
                status,
                detail,
            )
        else:
            logger.info("report=%s progress=%s", report_id, progress)

        with _reports_lock:
            if report_id not in _reports:
                return
            _reports[report_id]["progress"] = progress
            _reports[report_id]["updatedAt"] = _utc_now()
            _persist_report(_reports[report_id])

    try:
        logger.info("report=%s status=running rootCid=%s", report_id, root_cid)
        selected_rpc, rpc_source = _resolve_rpc_for_log()
        logger.info(
            "report=%s rpc_selected source=%s endpoint=%s",
            report_id,
            rpc_source or "none",
            _sanitize_rpc_for_log(selected_rpc),
        )
        orch = create_orchestrator_from_env()
        result = orch.run({"rootCid": root_cid, "_progress_callback": progress_callback})
        with _reports_lock:
            _reports[report_id]["status"] = "done"
            _reports[report_id]["result"] = result
            _reports[report_id]["updatedAt"] = _utc_now()
            _persist_report(_reports[report_id])
        logger.info("report=%s status=done", report_id)
    except Exception as exc:
        with _reports_lock:
            _reports[report_id]["status"] = "error"
            _reports[report_id]["error"] = str(exc)
            _reports[report_id]["updatedAt"] = _utc_now()
            _persist_report(_reports[report_id])
        logger.exception("report=%s status=error", report_id)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_rpc_for_log() -> tuple[Optional[str], Optional[str]]:
    for key in ("RPC_HTTPS_URL", "RPC_URL", "RPC_WSS_URL"):
        value = os.getenv(key)
        if value:
            return value, key
    return None, None


def _sanitize_rpc_for_log(value: Optional[str]) -> str:
    if not value:
        return "none"
    try:
        parts = urlsplit(value)
        if parts.scheme and parts.hostname:
            host = parts.hostname
            if parts.port:
                host = f"{host}:{parts.port}"
            return f"{parts.scheme}://{host}"
    except Exception:
        pass
    return "configured"


def _report_path(report_id: str) -> Path:
    return _reports_dir / f"{report_id}.json"


def _persist_report(record: Dict[str, Any]) -> None:
    _report_path(record["reportId"]).write_text(json.dumps(record, indent=2), encoding="utf-8")


def _load_reports_from_disk() -> None:
    for path in sorted(_reports_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(record, dict) and record.get("reportId"):
                _reports[record["reportId"]] = record
        except Exception:
            continue


def _load_report_from_disk(report_id: str) -> Optional[Dict[str, Any]]:
    path = _report_path(report_id)
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(record, dict) or record.get("reportId") != report_id:
        return None
    _reports[report_id] = record
    return record


def _preload_reports_enabled() -> bool:
    raw = str(os.getenv("REPORT_PRELOAD_ON_STARTUP", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


_COMPACT_RESULT_BUNDLE_KEYS = (
    "claims",
    "domainStatus",
    "domainSummaries",
    "explanations",
    "graph",
    "rootCid",
    "supplyChainProfile",
    "technical",
    "technical_summary",
    "vcsByCid",
    "vcsByCidPresent",
)


def _truncate_list(items: Any, limit: int) -> Any:
    if not isinstance(items, list):
        return items
    return deepcopy(items[:limit])


def _compact_mapping(item: Any, allowed_keys: tuple[str, ...]) -> Any:
    if not isinstance(item, dict):
        return deepcopy(item)
    return {key: deepcopy(item.get(key)) for key in allowed_keys if key in item}


def _compact_list_of_mappings(items: Any, allowed_keys: tuple[str, ...], limit: int) -> list[Any]:
    if not isinstance(items, list):
        return []
    return [
        _compact_mapping(item, allowed_keys) if isinstance(item, dict) else deepcopy(item)
        for item in items[:limit]
    ]


def _build_compact_result_payload(result: Any) -> Any:
    if not isinstance(result, dict):
        return deepcopy(result)

    result_payload: Dict[str, Any] = {}
    for key in ("success", "entity", "auditDate", "timestamp", "llm_summary", "executive_summary"):
        if key in result:
            result_payload[key] = deepcopy(result.get(key))

    bundle = result.get("result_bundle")
    if isinstance(bundle, dict):
        result_payload["result_bundle"] = {
            key: deepcopy(bundle[key])
            for key in _COMPACT_RESULT_BUNDLE_KEYS
            if key in bundle
        }

    return result_payload


def _build_report_payload(record: Dict[str, Any], include_full: bool = False) -> Dict[str, Any]:
    if include_full:
        return deepcopy(record)

    payload: Dict[str, Any] = {
        "reportId": record.get("reportId"),
        "rootCid": record.get("rootCid"),
        "status": record.get("status"),
        "createdAt": record.get("createdAt"),
        "updatedAt": record.get("updatedAt"),
    }

    if "error" in record:
        payload["error"] = record.get("error")
    if "progress" in record:
        payload["progress"] = deepcopy(record.get("progress"))

    result = record.get("result")
    if isinstance(result, dict):
        payload["result"] = _build_compact_result_payload(result)

    return payload


def _build_graph_summary(graph: Any, vcs_by_cid: Any) -> Dict[str, Any]:
    graph = graph if isinstance(graph, dict) else {}
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    continuity = graph.get("continuity") if isinstance(graph.get("continuity"), dict) else {}
    governance = graph.get("governance") if isinstance(graph.get("governance"), dict) else {}
    return {
        "rootCid": graph.get("rootCid"),
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "vcCount": len(vcs_by_cid) if isinstance(vcs_by_cid, dict) else 0,
        "continuity": _compact_mapping(
            continuity,
            ("status", "reason", "issues", "warnings"),
        ),
        "governance": _compact_mapping(
            governance,
            ("status", "reason", "issues", "warnings"),
        ),
    }


def _build_domain_status_qa_digest(domain_status: Any) -> Dict[str, Any]:
    status = domain_status if isinstance(domain_status, dict) else {}

    technical = status.get("technical") if isinstance(status.get("technical"), dict) else {}
    compliance = status.get("compliance") if isinstance(status.get("compliance"), dict) else {}
    certification = status.get("certification") if isinstance(status.get("certification"), dict) else {}
    esg = status.get("esg") if isinstance(status.get("esg"), dict) else {}

    return {
        "technical": {
            **_compact_mapping(technical, ("state", "detail", "source", "score", "findings")),
            "observations": _truncate_list(technical.get("observations"), 5),
        },
        "compliance": {
            **_compact_mapping(compliance, ("state", "detail", "source", "score", "findings", "summary", "coverage")),
            "observations": _truncate_list(compliance.get("observations"), 6),
            "actions": _compact_list_of_mappings(compliance.get("actions"), ("text", "deadline"), 6),
            "regulations": _compact_list_of_mappings(
                compliance.get("regulations"),
                ("id", "shortName", "status", "applicable", "message", "summary", "coverage"),
                8,
            ),
            "articles": _compact_list_of_mappings(
                compliance.get("articles"),
                ("id", "title", "status", "detail"),
                12,
            ),
        },
        "certification": {
            **_compact_mapping(certification, ("state", "detail", "source", "score", "findings", "summary")),
            "observations": _truncate_list(certification.get("observations"), 6),
            "actions": _compact_list_of_mappings(certification.get("actions"), ("text", "deadline"), 6),
            "certifications": _compact_list_of_mappings(
                certification.get("certifications"),
                (
                    "name",
                    "status",
                    "detail",
                    "certificationId",
                    "passingNodeCount",
                    "applicableNodeCount",
                    "matchedNodeCount",
                    "failureType",
                ),
                10,
            ),
        },
        "esg": {
            **_compact_mapping(esg, ("state", "detail", "source", "score", "findings", "verdict", "breakdown", "coverage", "confidence")),
            "flags": _truncate_list(esg.get("flags"), 12),
            "observations": _truncate_list(esg.get("observations"), 6),
            "actions": _compact_list_of_mappings(esg.get("actions"), ("text", "deadline"), 6),
            "items": _compact_list_of_mappings(esg.get("items"), ("category", "title", "status", "score", "detail"), 6),
        },
    }


def _build_explanations_qa_digest(explanations: Any) -> Dict[str, Any]:
    if not isinstance(explanations, dict):
        return {}

    technical = explanations.get("technical") if isinstance(explanations.get("technical"), dict) else {}
    compliance = explanations.get("compliance") if isinstance(explanations.get("compliance"), dict) else {}
    esg = explanations.get("esg") if isinstance(explanations.get("esg"), dict) else {}
    certification = explanations.get("certification") if isinstance(explanations.get("certification"), dict) else {}

    return {
        "technical": {
            "diagnoses": _compact_list_of_mappings(
                technical.get("diagnoses"),
                ("failure_ref", "severity", "explanation", "remediation", "confidence"),
                8,
            )
        },
        "compliance": _compact_mapping(compliance, ("error",)),
        "esg": _compact_mapping(esg, ("llmExplanation", "primaryDrivers", "recommendedActions", "confidence")),
        "certification": {
            "findings": _compact_list_of_mappings(
                certification.get("findings"),
                ("ref", "severity", "explanation", "recommendedActions", "confidence"),
                8,
            )
        },
    }


def _build_technical_qa_digest(technical: Any) -> Dict[str, Any]:
    tech = technical if isinstance(technical, dict) else {}
    return {
        "success": tech.get("success"),
        "claims": _truncate_list(tech.get("claims"), 12),
        "failures": _compact_list_of_mappings(
            tech.get("failures"),
            ("code", "type", "category", "severity", "message", "detail", "cid", "check", "reason"),
            20,
        ),
    }


def _build_domain_summaries_qa_digest(domain_summaries: Any) -> Dict[str, Any]:
    if not isinstance(domain_summaries, dict):
        return {}

    digest: Dict[str, Any] = {}
    for domain, payload in domain_summaries.items():
        if isinstance(payload, dict):
            digest[domain] = _compact_mapping(
                payload,
                ("domain", "state", "summaryText", "source", "fallbackReason"),
            )
    return digest


def _build_qa_result_payload(result: Any) -> Any:
    if not isinstance(result, dict):
        return deepcopy(result)

    result_payload: Dict[str, Any] = {}
    for key in ("success", "entity", "auditDate", "timestamp", "llm_summary", "executive_summary"):
        if key in result:
            result_payload[key] = deepcopy(result.get(key))

    bundle = result.get("result_bundle")
    if not isinstance(bundle, dict):
        return result_payload

    vcs_by_cid = bundle.get("vcsByCid")
    result_payload["qa_digest"] = {
        "rootCid": bundle.get("rootCid"),
        "claims": deepcopy(bundle.get("claims")),
        "supplyChainProfile": deepcopy(bundle.get("supplyChainProfile")),
        "technical_summary": deepcopy(bundle.get("technical_summary")),
        "graphSummary": _build_graph_summary(bundle.get("graph"), vcs_by_cid),
        "domainSummaries": _build_domain_summaries_qa_digest(bundle.get("domainSummaries")),
        "domainStatus": _build_domain_status_qa_digest(bundle.get("domainStatus")),
        "technical": _build_technical_qa_digest(bundle.get("technical")),
        "explanations": _build_explanations_qa_digest(bundle.get("explanations")),
        "vcsByCidPresent": deepcopy(bundle.get("vcsByCidPresent")),
    }

    return result_payload


def _should_regenerate_executive_summary(summary: Any, record: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(summary, str) or not summary.strip() or not isinstance(record, dict):
        return True

    result = record.get("result")
    if not isinstance(result, dict):
        return False

    bundle = result.get("result_bundle")
    if not isinstance(bundle, dict):
        return False

    claims = bundle.get("claims")
    supply_chain_profile = bundle.get("supplyChainProfile")
    domain_status = bundle.get("domainStatus")

    has_rich_context = bool(claims) or bool(supply_chain_profile) or bool(domain_status)
    if not has_rich_context:
        return False

    normalized = " ".join(summary.lower().split())
    stale_markers = (
        'supplier entity',
        'auditdate is null',
        'no vc claims',
        'no technical, compliance, certification, or esg findings',
    )
    return any(marker in normalized for marker in stale_markers)


def _build_qa_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    if "result" in payload and ("reportId" in payload or "rootCid" in payload or "status" in payload):
        record = _build_report_payload(payload, include_full=False)
        if isinstance(record.get("result"), dict):
            record["result"] = _build_qa_result_payload(record.get("result"))
        return record

    if "result_bundle" in payload or "success" in payload or "entity" in payload:
        return _build_qa_result_payload(payload)

    return deepcopy(payload)


if _preload_reports_enabled():
    with _reports_lock:
        _load_reports_from_disk()

@app.post("/api/run")
def run_audit():
    data = request.get_json(force=True, silent=True) or {}
    root_cid = (data.get("rootCid") or "").strip()
    if not root_cid:
        return jsonify({"error": "rootCid is required"}), 400

    report_id = str(uuid.uuid4())
    with _reports_lock:
        _reports[report_id] = {
            "reportId": report_id,
            "rootCid": root_cid,
            "status": "running",
            "createdAt": _utc_now(),
            "updatedAt": _utc_now(),
            "progress": {
                "currentStep": None,
                "steps": {},
            },
        }
        _persist_report(_reports[report_id])

    t = threading.Thread(
        target=_run_orchestrator,
        args=(report_id, root_cid),
        daemon=True,
    )
    t.start()

    return jsonify({"reportId": report_id}), 202


@app.post("/api/graph")
def build_graph():
    data = request.get_json(force=True, silent=True) or {}
    root_cid = (data.get("rootCid") or "").strip()
    if not root_cid:
        return jsonify({"error": "rootCid is required"}), 400

    try:
        with _graph_cache_lock:
            cached = _graph_cache.get(root_cid)
        if cached is not None:
            logger.info("graph_build status=cached rootCid=%s", root_cid)
            return jsonify(cached)

        logger.info("graph_build status=running rootCid=%s", root_cid)
        orch = create_orchestrator_from_env()
        graph = orch.build_graph(root_cid)
        payload = {
            "graph": graph,
            "view": {
                "nodes": [
                    {
                        "id": n.get("cid"),
                        "cid": n.get("cid"),
                        "label": (n.get("cid") or "")[:12] + "...",
                        "issuerAddress": n.get("issuerAddress"),
                        "holderAddress": n.get("holderAddress"),
                        "productContract": n.get("productContract"),
                    }
                    for n in (graph.get("nodes") or [])
                    if isinstance(n, dict) and n.get("cid")
                ],
                "edges": [
                    {"id": f"{e.get('from')}->{e.get('to')}", "source": e.get("from"), "target": e.get("to")}
                    for e in (graph.get("edges") or [])
                    if isinstance(e, dict) and e.get("from") and e.get("to")
                ],
                "rootCid": root_cid,
            },
        }
        with _graph_cache_lock:
            _graph_cache[root_cid] = payload
        logger.info("graph_build status=done rootCid=%s", root_cid)
        return jsonify(payload)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/vc")
def get_vc():
    data = request.get_json(force=True, silent=True) or {}
    cid = (data.get("cid") or "").strip()
    report_id = (data.get("reportId") or "").strip()
    if not cid:
        return jsonify({"error": "cid is required"}), 400

    try:
        with _vc_cache_lock:
            cached = _vc_cache.get(cid)
        if cached is not None:
            return jsonify({"cid": cid, "vc": cached, "source": "vc_cache"})

        if report_id:
            with _reports_lock:
                record = _reports.get(report_id) or _load_report_from_disk(report_id)
            bundle = (((record or {}).get("result") or {}).get("result_bundle") or {})
            vcs_by_cid = bundle.get("vcsByCid") or {}
            if isinstance(vcs_by_cid, dict) and cid in vcs_by_cid:
                with _vc_cache_lock:
                    _vc_cache[cid] = vcs_by_cid[cid]
                return jsonify({"cid": cid, "vc": vcs_by_cid[cid], "source": "report_bundle"})

        orch = create_orchestrator_from_env()
        interactive_ipfs = IpfsFetcher(
            IpfsFetchConfig(
                gateways=list(orch.config.ipfs.gateways),
                timeout_s=float(os.getenv("VC_IPFS_TIMEOUT_S", "4")),
                retries=int(os.getenv("VC_IPFS_RETRIES", "0")),
                backoff_s=float(os.getenv("VC_IPFS_BACKOFF_S", "0.2")),
                jitter_s=float(os.getenv("VC_IPFS_JITTER_S", "0.1")),
            )
        )
        vc = interactive_ipfs.fetch_json(cid)
        with _vc_cache_lock:
            _vc_cache[cid] = vc
        return jsonify({"cid": cid, "vc": vc, "source": "ipfs"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/report/<report_id>")
def get_report(report_id: str):
    include_full = str(request.args.get("full") or "").strip().lower() in {"1", "true", "yes"}
    with _reports_lock:
        record = _reports.get(report_id) or _load_report_from_disk(report_id)
    if record is None:
        return jsonify({"error": "report not found"}), 404
    return jsonify(_build_report_payload(record, include_full=include_full))


@app.get("/api/reports")
def list_reports():
    with _reports_lock:
        rows = sorted(
            _reports.values(),
            key=lambda row: row.get("updatedAt") or row.get("createdAt") or "",
            reverse=True,
        )
    return jsonify(
        {
            "reports": [
                {
                    "reportId": row.get("reportId"),
                    "rootCid": row.get("rootCid"),
                    "status": row.get("status"),
                    "createdAt": row.get("createdAt"),
                    "updatedAt": row.get("updatedAt"),
                    "success": ((row.get("result") or {}).get("success") if isinstance(row.get("result"), dict) else None),
                }
                for row in rows
            ]
        }
    )


@app.post("/api/qa")
def qa():
    data = request.get_json(force=True, silent=True) or {}
    report_id = (data.get("reportId") or "").strip()
    question  = (data.get("question") or "").strip()
    mode = (data.get("mode") or "").strip().lower()
    inline_report_data = data.get("reportData")

    if not question:
        return jsonify({"error": "question is required"}), 400

    record = None

    if report_id:
        with _reports_lock:
            record = _reports.get(report_id) or _load_report_from_disk(report_id)
        if record is None and inline_report_data is None:
            return jsonify({"error": "report not found"}), 404
        if record is not None and record.get("status") != "done" and inline_report_data is None:
            return jsonify({"error": "report not ready yet"}), 409

    if mode == "executive_summary" and record is not None:
        existing_summary = ((record.get("result") or {}).get("executive_summary"))
        if not _should_regenerate_executive_summary(existing_summary, record):
            return jsonify({"answer": existing_summary, "cached": True})

    if inline_report_data is not None:
        if record is None:
            report_payload = _build_qa_payload(inline_report_data)
        else:
            report_payload = _build_qa_result_payload(record.get("result"))
    else:
        if record is None:
            return jsonify({"error": "reportId or reportData is required"}), 400
        report_payload = _build_qa_result_payload(record.get("result"))

    try:
        llm = _get_llm()
        if mode == "executive_summary":
            answer = llm.ask_executive_summary(report_payload, question)
        else:
            answer = llm.ask_about_report(report_payload, question)

        if mode == "executive_summary" and record is not None:
            with _reports_lock:
                current = _reports.get(report_id)
                if current is not None and isinstance(current.get("result"), dict):
                    current["result"]["executive_summary"] = answer
                    current["result"]["executive_summary_updatedAt"] = _utc_now()
                    current["updatedAt"] = _utc_now()
                    _persist_report(current)

        return jsonify({"answer": answer})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "7002"))
    print(f"Audit Agent API server starting on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
