from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import yaml

from backend.agents.esg.extractors import build_esg_input
from backend.paths import ESG_ASSETS_DIR


ENVIRONMENTAL_RISK_TAGS = {
    "deforestation_risk",
    "deforestation_pressure",
    "biodiversity_disturbance",
    "tailings_runoff_risk",
    "water_stress",
    "protected_area_risk",
}


def _clamp(score: float) -> float:
    return max(0.0, min(1.0, score))


def _score_ratio(matched: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return _clamp(matched / total)


def _score_percent(score: float) -> int:
    return int(round(_clamp(score) * 100))


def _status_from_score(score_100: int) -> str:
    if score_100 >= 80:
        return "pass"
    if score_100 >= 55:
        return "warning"
    return "fail"


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_rulepack(path: Optional[str] = None) -> Dict[str, Any]:
    if not path:
        path = os.fspath(ESG_ASSETS_DIR / "rulepacks" / "esrs_esg.v1.yaml")
    return _load_yaml(path)


def _load_lookups() -> Dict[str, Any]:
    return _load_yaml(os.fspath(ESG_ASSETS_DIR / "rulepacks" / "country_risk.v1.yaml"))


def _cert_signal(node: Dict[str, Any], allowed: List[str]) -> bool:
    certifications = set(node.get("certifications") or [])
    return any(cert in certifications for cert in allowed)


def _has_location(node: Dict[str, Any]) -> bool:
    location = node.get("location") or {}
    return (location.get("latitude") is not None and location.get("longitude") is not None) or bool(location.get("country"))


def _has_did_transparency(node: Dict[str, Any]) -> bool:
    issuer = str(node.get("issuerDid") or "")
    holder = str(node.get("holderDid") or "")
    return issuer.startswith("did:") and holder.startswith("did:")


def _graph_transparency_ok(graph: Dict[str, Any]) -> bool:
    continuity = (graph.get("continuity") or {}).get("verified")
    nodes = graph.get("nodes") or []
    return continuity is True and len(nodes) > 0


def _country_code(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip().lower()
    if len(text) == 2:
        return text
    mapping = {
        "democratic republic of the congo": "cd",
        "drc": "cd",
        "congo, democratic republic of the": "cd",
        "indonesia": "id",
        "chile": "cl",
        "australia": "au",
        "canada": "ca",
        "china": "cn",
        "argentina": "ar",
        "brazil": "br",
        "philippines": "ph",
        "south africa": "za",
    }
    return mapping.get(text)


def _top_flags(flags: List[str], limit: int = 5) -> List[str]:
    unique: List[str] = []
    for flag in flags:
        if flag not in unique:
            unique.append(flag)
    return unique[:limit]


def _build_narrative_seed(verdict: str, scores: Dict[str, float], flags: List[str]) -> str:
    return (
        f"ESG verdict={verdict}; "
        f"E={scores['E']:.2f}, S={scores['S']:.2f}, G={scores['G']:.2f}, composite={scores['composite']:.2f}. "
        f"Top flags: {', '.join(_top_flags(flags)) or 'none'}."
    )


def _summarize_aspect(name: str, score: float, detail: str) -> Dict[str, Any]:
    score_100 = _score_percent(score)
    return {
        "name": name,
        "score": score,
        "score100": score_100,
        "status": _status_from_score(score_100),
        "detail": detail,
    }


def _category_item(category: str, score: float, aspects: List[Dict[str, Any]]) -> Dict[str, Any]:
    score_100 = _score_percent(score)
    passing = sum(1 for aspect in aspects if aspect["score"] >= 0.999)
    aspect_summary = " ".join(f"{aspect['name']}: {aspect['detail']}" for aspect in aspects)
    return {
        "category": category,
        "title": f"{category} score",
        "status": _status_from_score(score_100),
        "score": score_100,
        "detail": (
            f"{score_100}/100. {passing}/{len(aspects)} checks fully met the requirement. {aspect_summary}"
            if aspects
            else f"{score_100}/100."
        ),
        "aspects": aspects,
    }


def evaluate_esg(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    root_cid = tool_input.get("rootCid")
    graph = tool_input.get("graph") or {}
    vcs_by_cid = tool_input.get("vcsByCid") or {}
    rulepack = _load_rulepack(tool_input.get("rulepackPath"))
    lookups = _load_lookups()
    extracted = build_esg_input(graph, vcs_by_cid)
    nodes = extracted.get("nodes") or []

    thresholds = rulepack.get("thresholds") or {}
    cert_signals = rulepack.get("certificationSignals") or {}
    country_risk = lookups.get("countryRisk") or {}

    coverage = {"countryFallbackNodes": 0}
    node_count = len(nodes)

    environmental_cert_nodes = 0
    environmental_biodiversity_nodes = 0
    social_workers_nodes = 0
    social_community_nodes = 0
    governance_did_nodes = 0
    governance_cert_nodes = 0

    for node in nodes:
        env_claims = node.get("environmentalClaims") or {}
        env_cert = _cert_signal(node, cert_signals.get("environmental") or [])
        social_cert = _cert_signal(node, cert_signals.get("social") or [])
        governance_cert = _cert_signal(node, cert_signals.get("governance") or [])

        has_environmental_disclosure = (
            any(env_claims.get(key) for key in ("energySource", "emissionsClaim", "climateClaim"))
            or env_cert
        ) and not bool(env_claims.get("highRiskEnergySource"))
        if has_environmental_disclosure:
            environmental_cert_nodes += 1

        location_ok = _has_location(node)
        risk_tags = set(node.get("operationTags") or [])
        environmental_risk_tags = sorted(risk_tags & ENVIRONMENTAL_RISK_TAGS)
        if location_ok and (not environmental_risk_tags or env_cert):
            environmental_biodiversity_nodes += 1

        if social_cert:
            social_workers_nodes += 1

        country_code = _country_code((node.get("location") or {}).get("country"))
        community_risk = 0.0
        if country_code:
            coverage["countryFallbackNodes"] += 1
            community_risk = float((country_risk.get(country_code) or {}).get("communityRisk") or 0.0)
        if country_code and (community_risk <= 0.40 or social_cert):
            social_community_nodes += 1

        if _has_did_transparency(node):
            governance_did_nodes += 1
        if governance_cert:
            governance_cert_nodes += 1

    graph_ok_score = 1.0 if _graph_transparency_ok(graph) and node_count > 0 else 0.0

    environmental_aspects = [
        _summarize_aspect(
            "Climate change",
            _score_ratio(environmental_cert_nodes, node_count),
            (
                f"{environmental_cert_nodes}/{node_count} nodes disclosed climate or emissions evidence "
                f"with no high-risk energy source, or an environmental certification without a high-risk energy source."
                if node_count
                else "No node evidence available."
            ),
        ),
        _summarize_aspect(
            "Biodiversity and land-use",
            _score_ratio(environmental_biodiversity_nodes, node_count),
            (
                f"{environmental_biodiversity_nodes}/{node_count} nodes had location evidence and no unmanaged biodiversity risk signals."
                if node_count
                else "No node evidence available."
            ),
        ),
    ]
    social_aspects = [
        _summarize_aspect(
            "Workers in the value chain",
            _score_ratio(social_workers_nodes, node_count),
            (
                f"{social_workers_nodes}/{node_count} nodes had worker-related certification coverage."
                if node_count
                else "No node evidence available."
            ),
        ),
        _summarize_aspect(
            "Affected communities",
            _score_ratio(social_community_nodes, node_count),
            (
                f"{social_community_nodes}/{node_count} nodes were in lower community-risk countries or had supporting social certification."
                if node_count
                else "No node evidence available."
            ),
        ),
    ]
    governance_aspects = [
        _summarize_aspect(
            "Business conduct and traceability",
            (graph_ok_score + _score_ratio(governance_did_nodes, node_count) + _score_ratio(governance_cert_nodes, node_count)) / 3.0
            if node_count
            else 0.0,
            (
                f"Graph continuity={'verified' if graph_ok_score == 1.0 else 'incomplete'}; "
                f"DID transparency on {governance_did_nodes}/{node_count} nodes; "
                f"governance-supporting certification on {governance_cert_nodes}/{node_count} nodes."
                if node_count
                else "No node evidence available."
            ),
        )
    ]

    environmental = sum(aspect["score"] for aspect in environmental_aspects) / 2.0
    social = sum(aspect["score"] for aspect in social_aspects) / 2.0
    governance = governance_aspects[0]["score"]
    composite = _clamp((environmental + social + governance) / 3.0)

    flags: List[str] = []
    if environmental_aspects[0]["score"] < 1.0:
        flags.append("environmental_climate_disclosure_incomplete")
    if environmental_aspects[1]["score"] < 1.0:
        flags.append("environmental_biodiversity_controls_incomplete")
    if social_aspects[0]["score"] < 1.0:
        flags.append("social_worker_controls_incomplete")
    if social_aspects[1]["score"] < 1.0:
        flags.append("social_community_controls_incomplete")
    if governance < 1.0:
        flags.append("governance_traceability_incomplete")

    findings = [
        _category_item("Environmental", environmental, environmental_aspects),
        _category_item("Social", social, social_aspects),
        _category_item("Governance", governance, governance_aspects),
    ]

    if composite >= float(thresholds.get("compliant") or 0.85):
        verdict = "COMPLIANT"
        success: Optional[bool] = True
    elif composite >= float(thresholds.get("review_required") or 0.55):
        verdict = "REVIEW_REQUIRED"
        success = None
    else:
        verdict = "NON_COMPLIANT"
        success = False

    scores = {
        "E": environmental,
        "S": social,
        "G": governance,
        "composite": composite,
    }
    confidence = 1.0
    breakdown = {
        "environmental": _score_percent(environmental),
        "social": _score_percent(social),
        "governance": _score_percent(governance),
    }

    claims = [
        {"type": "esg.environmental.score", "verified": environmental >= 0.80, "value": environmental},
        {"type": "esg.social.score", "verified": social >= 0.80, "value": social},
        {"type": "esg.governance.score", "verified": governance >= 0.80, "value": governance},
        {"type": "esg.composite.score", "verified": success is True, "value": composite},
        {"type": "esg.verdict", "verified": success is True, "value": verdict},
    ]

    narrative_seed = _build_narrative_seed(verdict, scores, flags)
    observation_lines = [f"{item['category']}: {item['detail']}" for item in findings]

    return {
        "status": "done",
        "success": success,
        "message": f"ESG assessment completed with verdict {verdict}.",
        "scores": scores,
        "verdict": verdict,
        "flags": _top_flags(flags, limit=20),
        "findings": findings,
        "claims": claims,
        "narrativeSeed": narrative_seed,
        "meta": {
            "rootCid": root_cid,
            "frameworkId": (rulepack.get("framework") or {}).get("id"),
            "frameworkVersion": (rulepack.get("framework") or {}).get("version"),
            "nodeCount": node_count,
            "confidence": confidence,
            "coverage": coverage,
            "aspects": {
                "environmental": environmental_aspects,
                "social": social_aspects,
                "governance": governance_aspects,
            },
        },
        "ui": {
            "score": _score_percent(composite),
            "findings": sum(1 for item in findings if item["status"] != "pass"),
            "detail": [
                f"Verdict: {verdict}",
                f"Composite ESG score: {_score_percent(composite)}/100",
                "Category weights: Environmental 1/3, Social 1/3, Governance 1/3",
            ],
            "observations": observation_lines,
            "actions": [
                {"text": "Add missing environmental or social evidence for nodes that did not meet the ESG checks.", "deadline": None}
                if any(item["status"] != "pass" for item in findings)
                else None,
                {"text": "Complete provenance continuity and DID metadata for every node in the supply chain.", "deadline": None}
                if governance < 1.0
                else None,
            ],
            "breakdown": breakdown,
            "items": findings,
        },
    }
