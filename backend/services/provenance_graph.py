from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


def _normalize(value: Any) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    return v if v else None


def _normalize_address(value: Any) -> Optional[str]:
    v = _normalize(value)
    return v.lower() if v else None


def _did_to_address(value: Any) -> Optional[str]:
    v = _normalize(value)
    if not v:
        return None
    lower = v.lower()
    marker = ":0x"
    idx = lower.rfind(marker)
    if idx == -1:
        return lower
    return lower[idx + 1 :]


def _parse_datetime(value: Any) -> Optional[datetime]:
    text = _normalize(value)
    if not text:
        return None
    candidate = text
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _get_component_credentials(vc: Dict[str, Any]) -> List[str]:
    subject = vc.get("credentialSubject") if isinstance(vc, dict) else None
    if not isinstance(subject, dict):
        return []

    listing = subject.get("listing")
    if isinstance(listing, dict):
        listing_components = listing.get("componentCredentials")
        if isinstance(listing_components, list):
            return [str(x) for x in listing_components if x is not None]

    subject_components = subject.get("componentCredentials")
    if isinstance(subject_components, list):
        return [str(x) for x in subject_components if x is not None]

    return []


@dataclass
class GraphNode:
    cid: str
    node_index: int
    product_id: Optional[str]
    product_contract: Optional[str]
    subject_id: Optional[str]
    chain_id: Optional[str]
    issuer_did: Optional[str]
    issuer_address: Optional[str]
    holder_did: Optional[str]
    holder_address: Optional[str]
    previous_credential: Optional[str]
    issuance_date: Optional[str]
    issuance_ts: Optional[str]
    component_credentials: List[str]


@dataclass
class GraphEdge:
    from_cid: str
    to_cid: str
    from_node_index: Optional[int]
    to_node_index: Optional[int]


def build_provenance_graph(
    root_cid: str,
    fetch_vc_by_cid,
    *,
    max_nodes: int = 50,
) -> Dict[str, Any]:
    
    # Build a provenance DAG by recursively following componentCredentials.
    if not root_cid or not isinstance(root_cid, str):
        raise ValueError("root_cid is required")

    visited: Set[str] = set()
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    by_cid: Dict[str, GraphNode] = {}
    stack: List[str] = [root_cid]

    continuity = {
        "verified": True,
        "reason": None,
        "cycleDetected": False,
        "missingLink": False,
        "truncated": False,
        "invalidReferences": False,
    }

    while stack:
        current = stack.pop()
        if not current or current in visited:
            continue
        if len(visited) >= max_nodes:
            continuity["verified"] = False
            continuity["truncated"] = True
            continuity["reason"] = f"Max node limit {max_nodes} reached while traversing provenance graph"
            break

        visited.add(current)

        try:
            vc = fetch_vc_by_cid(current)
        except Exception as e:
            if not nodes and current == root_cid:
                raise RuntimeError(f"Failed to fetch root CID {current}: {e}") from e
            continuity["verified"] = False
            continuity["missingLink"] = True
            continuity["reason"] = f"Failed to fetch CID {current}: {e}"
            continue

        subject = vc.get("credentialSubject", {}) if isinstance(vc, dict) else {}
        component_credentials = [_normalize(x) for x in _get_component_credentials(vc)]
        component_credentials = [x for x in component_credentials if x]

        issuer_did = None
        if isinstance(vc.get("issuer"), dict):
            issuer_did = _normalize(vc.get("issuer", {}).get("id"))
        holder_did = None
        if isinstance(vc.get("holder"), dict):
            holder_did = _normalize(vc.get("holder", {}).get("id"))

        issuance_date = _normalize(vc.get("issuanceDate"))
        parsed_issuance = _parse_datetime(issuance_date)
        node = GraphNode(
            cid=current,
            node_index=len(nodes),
            product_id=_normalize(subject.get("productId")),
            product_contract=_normalize_address(subject.get("productContract")),
            subject_id=_normalize_address(subject.get("id")),
            chain_id=_normalize(subject.get("chainId")),
            issuer_did=issuer_did,
            issuer_address=_did_to_address(issuer_did),
            holder_did=holder_did,
            holder_address=_did_to_address(holder_did),
            previous_credential=_normalize(subject.get("previousCredential")),
            issuance_date=issuance_date,
            issuance_ts=parsed_issuance.isoformat() if parsed_issuance else None,
            component_credentials=component_credentials,
        )

        nodes.append(node)
        by_cid[current] = node

        for child in component_credentials:
            edges.append(
                GraphEdge(
                    from_cid=current,
                    to_cid=child,
                    from_node_index=node.node_index,
                    to_node_index=None,
                )
            )
            if child == current:
                continuity["verified"] = False
                continuity["cycleDetected"] = True
                continuity["reason"] = f"Self-cycle detected at CID {current}"
            if child not in visited:
                stack.append(child)

    if not continuity["reason"]:
        continuity["reason"] = (
            "Unbroken component-linked provenance path"
            if continuity["verified"]
            else "Provenance continuity check failed"
        )

    identity = {"verified": True, "reason": None, "baseline": None, "mismatches": []}
    if nodes:
        baseline = {
            "productId": nodes[0].product_id,
            "productContract": nodes[0].product_contract,
            "subjectId": nodes[0].subject_id,
            "chainId": nodes[0].chain_id,
        }
        identity["baseline"] = baseline
        for n in nodes[1:]:
            comparisons = {
                "productId": n.product_id,
                "productContract": n.product_contract,
                "subjectId": n.subject_id,
                "chainId": n.chain_id,
            }
            for field, expected in baseline.items():
                actual = comparisons.get(field)
                if expected and actual and expected != actual:
                    identity["mismatches"].append(
                        {
                            "cid": n.cid,
                            "nodeIndex": n.node_index,
                            "field": field,
                            "expected": expected,
                            "actual": actual,
                        }
                    )
    identity["verified"] = len(identity["mismatches"]) == 0
    identity["reason"] = (
        "Asset identity is consistent across provenance graph"
        if identity["verified"]
        else "Identity mismatch detected across provenance graph"
    )

    parents_by_cid: Dict[str, List[str]] = {}
    children_by_cid: Dict[str, List[str]] = {}
    for edge in edges:
        parents_by_cid.setdefault(edge.to_cid, []).append(edge.from_cid)
        children_by_cid.setdefault(edge.from_cid, []).append(edge.to_cid)

    governance = {"verified": True, "reason": None, "violations": []}
    for edge in edges:
        parent = by_cid.get(edge.from_cid)
        child = by_cid.get(edge.to_cid)
        edge.to_node_index = child.node_index if child else None
        if not parent or not child:
            governance["verified"] = False
            governance["violations"].append(
                {
                    "from": edge.from_cid,
                    "to": edge.to_cid,
                    "fromCid": edge.from_cid,
                    "toCid": edge.to_cid,
                    "fromNodeIndex": edge.from_node_index,
                    "toNodeIndex": edge.to_node_index,
                    "reason": "Referenced component VC could not be loaded",
                }
            )
            continue
        if not parent.issuer_address or not child.holder_address or parent.issuer_address != child.holder_address:
            governance["verified"] = False
            governance["violations"].append(
                {
                    "from": edge.from_cid,
                    "to": edge.to_cid,
                    "fromCid": edge.from_cid,
                    "toCid": edge.to_cid,
                    "fromNodeIndex": edge.from_node_index,
                    "toNodeIndex": edge.to_node_index,
                    "expectedIssuer": child.holder_address,
                    "actualIssuer": parent.issuer_address,
                    "reason": "Governance mismatch: parent issuer must equal component holder",
                }
            )
    governance["reason"] = (
        "Issuer-holder governance is consistent across component links"
        if governance["verified"]
        else "Governance mismatch detected across component links"
    )

    return {
        "success": continuity["verified"] and identity["verified"] and governance["verified"],
        "continuity": continuity,
        "identity": identity,
        "governance": governance,
        "chainLength": len(nodes),
        "nodeIndexByCid": {n.cid: n.node_index for n in nodes},
        "parentsByCid": parents_by_cid,
        "childrenByCid": children_by_cid,
        "nodes": [
            {
                "cid": n.cid,
                "nodeIndex": n.node_index,
                "productId": n.product_id,
                "productContract": n.product_contract,
                "subjectId": n.subject_id,
                "chainId": n.chain_id,
                "issuerDid": n.issuer_did,
                "issuerAddress": n.issuer_address,
                "holderDid": n.holder_did,
                "holderAddress": n.holder_address,
                "previousCredential": n.previous_credential,
                "issuanceDate": n.issuance_date,
                "issuanceTimestamp": n.issuance_ts,
                "parentCids": parents_by_cid.get(n.cid, []),
                "childCids": children_by_cid.get(n.cid, []),
                "componentCredentials": n.component_credentials,
            }
            for n in nodes
        ],
        "edges": [
            {
                "from": e.from_cid,
                "to": e.to_cid,
                "fromCid": e.from_cid,
                "toCid": e.to_cid,
                "fromNodeIndex": e.from_node_index,
                "toNodeIndex": e.to_node_index,
            }
            for e in edges
        ],
    }
