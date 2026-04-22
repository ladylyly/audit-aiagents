from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.agents.technical_verification.verification.anchors import (
    verify_price_commitment_anchors,
    verify_vc_anchors,
)
from backend.agents.technical_verification.verification.signatures import verify_vc_signature
from backend.agents.technical_verification.verification.zkp_cli import (
    verify_tx_hash_commitment,
    verify_value_commitment,
)
from backend.agents.technical_verification.verification.zkp_extract import (
    extract_tx_hash_payload,
    extract_zkp_payload,
)
from backend.services.ipfs_fetcher import IpfsFetcher, default_ipfs_config
from backend.services.provenance_graph import build_provenance_graph


def _failure(code: str, reason: str, **extra: Any) -> Dict[str, Any]:
    f = {"code": code, "reason": reason}
    f.update(extra)
    return f


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _node_ref(graph: Dict[str, Any], cid: Optional[str]) -> Dict[str, Any]:
    if not cid:
        return {"cid": cid, "nodeIndex": None}
    node_index = (graph.get("nodeIndexByCid") or {}).get(cid)
    return {"cid": cid, "nodeIndex": node_index}


def _normalize_anchor_failures(graph: Dict[str, Any], failures: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in failures or []:
        if not isinstance(item, dict):
            continue
        cid = item.get("cid")
        normalized.append(
            {
                "cid": cid,
                "nodeIndex": (graph.get("nodeIndexByCid") or {}).get(cid),
                "productContract": item.get("productContract"),
                "expected": item.get("expected") or item.get("expectedHash") or item.get("expectedVcHash"),
                "actual": item.get("actual") or item.get("actualHash") or item.get("onchainHash") or item.get("vcHash"),
                "details": item,
            }
        )
    return normalized


def _build_temporal_findings(graph: Dict[str, Any], now: datetime) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    nodes = {
        str(node.get("cid")): node
        for node in (graph.get("nodes") or [])
        if isinstance(node, dict) and node.get("cid")
    }

    for cid, node in nodes.items():
        issuance = _parse_datetime(node.get("issuanceDate") or node.get("issuanceTimestamp"))
        if issuance and issuance > now:
            findings.append(
                _failure(
                    "FUTURE_ISSUANCE_DATE",
                    "VC issuanceDate is in the future",
                    cid=cid,
                    nodeIndex=node.get("nodeIndex"),
                    issuanceDate=node.get("issuanceDate"),
                    observedAt=now.isoformat(),
                )
            )

    for edge in (graph.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        parent = nodes.get(str(edge.get("fromCid") or edge.get("from")))
        child = nodes.get(str(edge.get("toCid") or edge.get("to")))
        if not parent or not child:
            continue
        parent_dt = _parse_datetime(parent.get("issuanceDate") or parent.get("issuanceTimestamp"))
        child_dt = _parse_datetime(child.get("issuanceDate") or child.get("issuanceTimestamp"))
        if parent_dt and child_dt and child_dt > parent_dt:
            findings.append(
                _failure(
                    "TEMPORAL_ORDERING_FAIL",
                    "Child issuanceDate is later than the assembly VC that references it",
                    cid=child.get("cid"),
                    nodeIndex=child.get("nodeIndex"),
                    parentCid=parent.get("cid"),
                    parentNodeIndex=parent.get("nodeIndex"),
                    childCid=child.get("cid"),
                    childNodeIndex=child.get("nodeIndex"),
                    parentIssuanceDate=parent.get("issuanceDate"),
                    childIssuanceDate=child.get("issuanceDate"),
                )
            )
    return findings


def _extract_price_commitment_for_anchor(vc: Dict[str, Any]) -> Optional[str]:
    if not isinstance(vc, dict):
        return None
    subject = vc.get("credentialSubject")
    if not isinstance(subject, dict):
        return None

    price_commitment = subject.get("priceCommitment")
    if isinstance(price_commitment, dict) and price_commitment.get("commitment"):
        return str(price_commitment.get("commitment"))

    price = subject.get("price")
    if isinstance(price, str):
        try:
            price = json.loads(price)
        except Exception:
            price = {}

    zkp = price.get("zkpProof") if isinstance(price, dict) else None
    if isinstance(zkp, dict) and zkp.get("commitment"):
        return str(zkp.get("commitment"))

    return None


def _root_fetch_failure_result(root_cid: str, reason: str) -> Dict[str, Any]:
    claims = [
        {
            "type": "provenance.continuity",
            "verified": False,
            "reason": reason,
        },
        {
            "type": "provenance.governance",
            "verified": False,
            "reason": "Provenance graph could not be built because the root VC was unavailable.",
            "violations": [],
        },
    ]
    return {
        "success": False,
        "failures": [
            _failure("ROOT_VC_FETCH_FAILED", reason, cid=root_cid),
        ],
        "claims": claims,
        "evidence": {
            "graph": None,
            "vcsByCid": {"count": 0},
            "stepStatus": {
                "signature": {"label": "Signature verification", "status": "skipped", "detail": "Root VC could not be fetched"},
                "zkp": {"label": "ZKP verification", "status": "skipped", "detail": "Root VC could not be fetched"},
                "price_commitment_anchor": {"label": "Price commitment anchor", "status": "skipped", "detail": "Root VC could not be fetched"},
                "current_anchor": {"label": "Current VC hash anchor", "status": "skipped", "detail": "Root VC could not be fetched"},
                "provenance": {"label": "Provenance continuity", "status": "failed", "detail": reason},
                "governance": {"label": "Governance consistency", "status": "skipped", "detail": "Root VC could not be fetched"},
                "chain_anchors": {"label": "Chain-wide anchors", "status": "skipped", "detail": "Root VC could not be fetched"},
            },
        },
    }


def verify_all(root_cid: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    
    #Deterministic technical verification (steps 1–6). Returns: { success, failures[], claims[], evidence{} }
    opts = options or {}
    max_nodes = int(opts.get("maxNodes") or 50)
    rpc_url = opts.get("rpcUrl")
    contract_address = opts.get("contractAddress")
    zkp_opts = (opts.get("zkp") or {}) if isinstance(opts.get("zkp"), dict) else {}
    zkp_enabled = bool(zkp_opts.get("enabled", True))
    progress_callback = opts.get("_progress_callback") if callable(opts.get("_progress_callback")) else None

    failures: List[Dict[str, Any]] = []
    evidence: Dict[str, Any] = {}
    step_status: Dict[str, Dict[str, Any]] = {
        "signature": {"label": "Signature verification", "status": "pending", "detail": None},
        "zkp": {"label": "ZKP verification", "status": "pending", "detail": None},
        "price_commitment_anchor": {"label": "Price commitment anchor", "status": "pending", "detail": None},
        "current_anchor": {"label": "Current VC hash anchor", "status": "pending", "detail": None},
        "provenance": {"label": "Provenance continuity", "status": "pending", "detail": None},
        "governance": {"label": "Governance consistency", "status": "pending", "detail": None},
        "chain_anchors": {"label": "Chain-wide anchors", "status": "pending", "detail": None},
    }

    def update_step(step_key: str, status: str, detail: Optional[str] = None) -> None:
        if step_key not in step_status:
            return
        step_status[step_key]["status"] = status
        step_status[step_key]["detail"] = detail
        if progress_callback:
            progress_callback(
                {
                    "currentStep": step_key,
                    "steps": step_status,
                }
            )

    fetcher = IpfsFetcher(default_ipfs_config())

    # Build provenance graph (step 4/5 rely on this)
    try:
        graph = build_provenance_graph(root_cid, fetcher.fetch_json, max_nodes=max_nodes)
    except Exception as e:
        return _root_fetch_failure_result(root_cid, str(e))
    evidence["graph"] = graph

    node_cids = [n.get("cid") for n in (graph.get("nodes") or []) if isinstance(n, dict) and n.get("cid")]

    # Fetch all VC payloads once
    vcs_by_cid: Dict[str, Any] = {}
    for cid in node_cids:
        try:
            vcs_by_cid[cid] = fetcher.fetch_json(cid)
        except Exception as e:
            failures.append(_failure("IPFS_FETCH_FAILED", str(e), cid=cid))
    evidence["vcsByCid"] = {"count": len(vcs_by_cid)}

    # 1) Signature verification (per VC)
    update_step("signature", "running", "Checking VC signatures")
    sig_results: Dict[str, Any] = {}
    for cid, vc in vcs_by_cid.items():
        try:
            sig_results[cid] = verify_vc_signature(vc, contract_address=contract_address)
            if sig_results[cid].get("success") is not True:
                failures.append(_failure("SIGNATURE_INVALID", sig_results[cid].get("message") or "Signature invalid", cid=cid))
        except Exception as e:
            failures.append(_failure("SIGNATURE_ERROR", str(e), cid=cid))
    evidence["signatures"] = {"results": sig_results}
    signature_failures = [f for f in failures if f.get("code") in {"SIGNATURE_INVALID", "SIGNATURE_ERROR"}]
    update_step(
        "signature",
        "passed" if not signature_failures else "failed",
        "All VC signatures valid" if not signature_failures else f"{len(signature_failures)} signature issue(s)",
    )

    # 2) ZKP verification (per VC where payload exists)
    update_step("zkp", "running", "Verifying zero-knowledge proofs")
    zkp_results: Dict[str, Any] = {}
    if zkp_enabled:
        for cid, vc in vcs_by_cid.items():
            try:
                z = extract_zkp_payload(vc)
                commitment = z.get("commitment")
                proof = z.get("proof")
                binding_tag = z.get("bindingTag")
                if not commitment or not proof:
                    failures.append(_failure("ZKP_MALFORMED", "Missing commitment/proof", cid=cid))
                    continue
                res = verify_value_commitment(
                    commitment_hex=str(commitment),
                    proof_hex=str(proof),
                    binding_tag_hex=str(binding_tag) if binding_tag else None,
                    cli_path=zkp_opts.get("cliPath"),
                )
                zkp_results[cid] = res
                if res.get("skipped"):
                    failures.append(_failure("ZKP_SKIPPED", res.get("reason") or "ZKP skipped", cid=cid))
                elif res.get("verified") is not True:
                    failures.append(_failure("ZKP_INVALID", "ZKP proof invalid", cid=cid, details=res))
            except Exception as e:
                failures.append(_failure("ZKP_MISSING", str(e), cid=cid))
    else:
        evidence["zkp"] = {"skipped": True, "reason": "zkp.enabled=false"}
    evidence["zkp"] = {"results": zkp_results}
    zkp_failures = [f for f in failures if str(f.get("code", "")).startswith("ZKP_")]
    if not zkp_enabled:
        update_step("zkp", "skipped", "ZKP verification disabled")
    else:
        update_step(
            "zkp",
            "passed" if not zkp_failures else "failed",
            "All ZKP checks passed" if not zkp_failures else f"{len(zkp_failures)} ZKP issue(s)",
        )

    now = datetime.now(timezone.utc)
    temporal_failures = _build_temporal_findings(graph, now)
    failures.extend(temporal_failures)
    evidence["temporal"] = {
        "checkedAt": now.isoformat(),
        "verified": len(temporal_failures) == 0,
        "failures": temporal_failures,
    }

    # 2.5) Price commitment anchor checks (per VC where possible)
    update_step("price_commitment_anchor", "running", "Checking on-chain price commitments")
    price_commitment_anchor_result: Dict[str, Any] = {
        "skipped": True,
        "verified": None,
        "reason": "rpcUrl not provided",
    }
    if rpc_url and graph.get("nodes"):
        try:
            price_anchor_nodes = []
            for n in (graph.get("nodes") or []):
                if not isinstance(n, dict):
                    continue
                cid = n.get("cid")
                if not cid:
                    continue
                vc = vcs_by_cid.get(cid)
                price_anchor_nodes.append(
                    {
                        "cid": cid,
                        "productContract": n.get("productContract"),
                        "vcPriceCommitment": _extract_price_commitment_for_anchor(vc),
                    }
                )

            price_commitment_anchor_result = verify_price_commitment_anchors(
                rpc_url=rpc_url,
                nodes=price_anchor_nodes,
            )
            if price_commitment_anchor_result.get("verified") is False:
                normalized_price_failures = _normalize_anchor_failures(
                    graph,
                    price_commitment_anchor_result.get("failed"),
                )
                price_commitment_anchor_result["failed"] = normalized_price_failures
                failures.append(
                    _failure(
                        "PRICE_COMMITMENT_ANCHOR_MISMATCH",
                        "One or more on-chain price commitments mismatched",
                        details=normalized_price_failures,
                    )
                )
        except Exception as e:
            failures.append(_failure("PRICE_COMMITMENT_ANCHOR_ERROR", str(e)))
    elif rpc_url:
        price_commitment_anchor_result = {
            "skipped": True,
            "verified": None,
            "reason": "No graph nodes available for anchor verification",
        }
    evidence["priceCommitmentAnchor"] = price_commitment_anchor_result
    if price_commitment_anchor_result.get("skipped"):
        update_step(
            "price_commitment_anchor",
            "skipped",
            price_commitment_anchor_result.get("reason"),
        )
    else:
        update_step(
            "price_commitment_anchor",
            "passed" if price_commitment_anchor_result.get("verified") else "failed",
            "All on-chain price commitments match"
            if price_commitment_anchor_result.get("verified")
            else "Price commitment anchor mismatch",
        )

    # 3) Current VC anchor for the root VC only
    update_step("current_anchor", "running", "Checking root VC anchor")
    current_anchor_result: Dict[str, Any] = {"skipped": True, "verified": None, "reason": "rpcUrl not provided"}
    # 6) Chain-wide anchors for the full graph
    update_step("chain_anchors", "running", "Checking chain-wide anchors")
    chain_anchor_result: Dict[str, Any] = {"skipped": True, "verified": None, "reason": "rpcUrl not provided"}
    if rpc_url and graph.get("nodes"):
        try:
            graph_nodes = [
                {"cid": n.get("cid"), "productContract": n.get("productContract")}
                for n in (graph.get("nodes") or [])
                if isinstance(n, dict) and n.get("cid")
            ]
            chain_anchor_result = verify_vc_anchors(rpc_url=rpc_url, nodes=graph_nodes)
            root_nodes = [n for n in graph_nodes if n.get("cid") == root_cid]
            if root_nodes:
                current_anchor_result = verify_vc_anchors(rpc_url=rpc_url, nodes=root_nodes)
            else:
                current_anchor_result = {
                    "skipped": True,
                    "verified": None,
                    "reason": "Root node missing productContract",
                }
            current_anchor_result["coverage"] = {
                "checkedNodes": len(root_nodes),
                "requestedNodes": 1,
            }
            chain_anchor_result["coverage"] = {
                "checkedNodes": len(graph_nodes),
                "requestedNodes": len(graph_nodes),
            }
            if current_anchor_result.get("verified") is False:
                normalized_current_failures = _normalize_anchor_failures(graph, current_anchor_result.get("failed"))
                current_anchor_result["failed"] = normalized_current_failures
                failures.append(
                    _failure(
                        "CURRENT_ANCHOR_MISMATCH",
                        "Current VC anchor mismatched",
                        details=normalized_current_failures,
                    )
                )
            if chain_anchor_result.get("verified") is False:
                normalized_chain_failures = _normalize_anchor_failures(graph, chain_anchor_result.get("failed"))
                chain_anchor_result["failed"] = normalized_chain_failures
                failures.append(
                    _failure(
                        "CHAIN_ANCHOR_MISMATCH",
                        "One or more chain anchors mismatched",
                        details=normalized_chain_failures,
                    )
                )
        except Exception as e:
            failures.append(_failure("ANCHOR_ERROR", str(e)))
    elif rpc_url:
        current_anchor_result = {
            "skipped": True,
            "verified": None,
            "reason": "No graph nodes available for anchor verification",
        }
        chain_anchor_result = {
            "skipped": True,
            "verified": None,
            "reason": "No graph nodes available for anchor verification",
            "coverage": {
                "checkedNodes": 0,
                "requestedNodes": 0,
            },
        }
    evidence["currentAnchor"] = current_anchor_result
    evidence["chainAnchors"] = chain_anchor_result
    if current_anchor_result.get("skipped"):
        update_step("current_anchor", "skipped", current_anchor_result.get("reason"))
    else:
        update_step(
            "current_anchor",
            "passed" if current_anchor_result.get("verified") else "failed",
            "Root VC anchor matches" if current_anchor_result.get("verified") else "Root VC anchor mismatch",
        )
    if chain_anchor_result.get("skipped"):
        update_step("chain_anchors", "skipped", chain_anchor_result.get("reason"))
    else:
        update_step(
            "chain_anchors",
            "passed" if chain_anchor_result.get("verified") else "failed",
            "All chain anchors match" if chain_anchor_result.get("verified") else "Chain anchor mismatch",
        )

    # 4) Provenance continuity
    update_step("provenance", "running", "Validating provenance continuity")
    if graph.get("continuity", {}).get("verified") is False:
        failures.append(_failure("PROVENANCE_CONTINUITY_FAIL", graph.get("continuity", {}).get("reason") or "Continuity failed"))
    update_step(
        "provenance",
        "passed" if graph.get("continuity", {}).get("verified") else "failed",
        graph.get("continuity", {}).get("reason"),
    )

    # 5) Governance consistency
    update_step("governance", "running", "Checking governance consistency")
    if graph.get("governance", {}).get("verified") is False:
        failures.append(
            _failure(
                "GOVERNANCE_FAIL",
                graph.get("governance", {}).get("reason") or "Governance failed",
                violations=graph.get("governance", {}).get("violations"),
            )
        )
    update_step(
        "governance",
        "passed" if graph.get("governance", {}).get("verified") else "failed",
        graph.get("governance", {}).get("reason"),
    )

    # Optional tx-hash proof checks if present in any VC
    tx_commitment_results: Dict[str, Any] = {}
    purchase_tx_commitment_results: Dict[str, Any] = {}
    for cid, vc in vcs_by_cid.items():
        try:
            tx_payload = extract_tx_hash_payload(vc, "txHashCommitment")
            tx_res = verify_tx_hash_commitment(
                commitment_hex=str(tx_payload.get("commitment")),
                proof_hex=str(tx_payload.get("proof")),
                binding_tag_hex=str(tx_payload.get("bindingTag")) if tx_payload.get("bindingTag") else None,
                cli_path=zkp_opts.get("cliPath"),
            )
            tx_commitment_results[cid] = tx_res
            if tx_res.get("verified") is False and not tx_res.get("skipped"):
                failures.append(_failure("TX_HASH_ZKP_INVALID", "Delivery tx-hash commitment invalid", cid=cid, details=tx_res))
        except Exception:
            pass

        try:
            purchase_payload = extract_tx_hash_payload(vc, "purchaseTxHashCommitment")
            purchase_res = verify_tx_hash_commitment(
                commitment_hex=str(purchase_payload.get("commitment")),
                proof_hex=str(purchase_payload.get("proof")),
                binding_tag_hex=str(purchase_payload.get("bindingTag")) if purchase_payload.get("bindingTag") else None,
                cli_path=zkp_opts.get("cliPath"),
            )
            purchase_tx_commitment_results[cid] = purchase_res
            if purchase_res.get("verified") is False and not purchase_res.get("skipped"):
                failures.append(_failure("PURCHASE_TX_HASH_ZKP_INVALID", "Purchase tx-hash commitment invalid", cid=cid, details=purchase_res))
        except Exception:
            pass

    evidence["txHashCommitments"] = {
        "delivery": tx_commitment_results,
        "purchase": purchase_tx_commitment_results,
    }
    evidence["stepStatus"] = step_status

    claims = [
        {"type": "provenance.continuity", "verified": bool(graph.get("continuity", {}).get("verified")), "reason": graph.get("continuity", {}).get("reason")},
        {"type": "provenance.governance", "verified": bool(graph.get("governance", {}).get("verified")), "reason": graph.get("governance", {}).get("reason"), "violations": graph.get("governance", {}).get("violations") or []},
        {"type": "provenance.temporal.valid", "verified": len(temporal_failures) == 0, "failures": temporal_failures},
        {"type": "vc.signatures.all_valid", "verified": all(v.get("success") is True for v in sig_results.values()) if sig_results else False, "checked": len(sig_results)},
        {"type": "vc.issuance_date.valid", "verified": not any(f.get("code") == "FUTURE_ISSUANCE_DATE" for f in temporal_failures), "checked": len(node_cids)},
        {
            "type": "vc.price_commitment_anchor.valid",
            "verified": bool(price_commitment_anchor_result.get("verified")) if not price_commitment_anchor_result.get("skipped") else None,
            "skipped": bool(price_commitment_anchor_result.get("skipped")),
            "reason": price_commitment_anchor_result.get("reason"),
        },
        {"type": "vc.current_anchor.valid", "verified": bool(current_anchor_result.get("verified")) if not current_anchor_result.get("skipped") else None, "skipped": bool(current_anchor_result.get("skipped")), "reason": current_anchor_result.get("reason")},
        {"type": "vc.chain_anchors.valid", "verified": bool(chain_anchor_result.get("verified")) if not chain_anchor_result.get("skipped") else None, "skipped": bool(chain_anchor_result.get("skipped")), "reason": chain_anchor_result.get("reason")},
        {
            "type": "vc.chain_anchors.coverage",
            "verified": None if chain_anchor_result.get("skipped") else bool(chain_anchor_result.get("verified")),
            "skipped": bool(chain_anchor_result.get("skipped")),
            "reason": chain_anchor_result.get("reason"),
            "coverage": chain_anchor_result.get("coverage"),
        },
        {"type": "vc.tx_hash_commitments.checked", "verified": all(v.get("verified") is True for v in tx_commitment_results.values()) if tx_commitment_results else None, "checked": len(tx_commitment_results)},
        {"type": "vc.purchase_tx_hash_commitments.checked", "verified": all(v.get("verified") is True for v in purchase_tx_commitment_results.values()) if purchase_tx_commitment_results else None, "checked": len(purchase_tx_commitment_results)},
    ]

    return {
        "success": len(failures) == 0,
        "failures": failures,
        "claims": claims,
        "evidence": evidence,
    }
