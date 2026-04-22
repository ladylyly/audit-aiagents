from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_key(value: Any) -> Optional[str]:
    text = _normalize_text(value)
    if not text:
        return None
    lowered = text.lower()
    return "_".join(part for part in "".join(ch if ch.isalnum() else " " for ch in lowered).split() if part)


def _get_path(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _first_present(obj: Dict[str, Any], paths: List[str]) -> Any:
    for path in paths:
        value = _get_path(obj, path)
        if value not in (None, "", [], {}):
            return value
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _extract_location(subject: Dict[str, Any]) -> Dict[str, Any]:
    latitude = _first_present(
        subject,
        [
            "location.latitude",
            "facilityLocation.latitude",
            "mineLocation.latitude",
            "coordinates.latitude",
            "gps.latitude",
            "site.latitude",
        ],
    )
    longitude = _first_present(
        subject,
        [
            "location.longitude",
            "facilityLocation.longitude",
            "mineLocation.longitude",
            "coordinates.longitude",
            "gps.longitude",
            "site.longitude",
        ],
    )
    country = _first_present(
        subject,
        [
            "countryCode",
            "country",
            "originCountry",
            "countryOfOrigin",
            "facilityLocation.country",
            "location.country",
            "site.country",
            "esgProfile.countryOfOperation",
        ],
    )
    region = _first_present(subject, ["region", "province", "state", "location.region", "site.region"])
    return {
        "latitude": _as_float(latitude),
        "longitude": _as_float(longitude),
        "country": _normalize_text(country),
        "region": _normalize_text(region),
    }


def _extract_material_tags(subject: Dict[str, Any]) -> List[str]:
    tags = subject.get("materialTags")
    out: List[str] = []
    if isinstance(tags, list):
        for tag in tags:
            normalized = _normalize_key(tag)
            if normalized and normalized not in out:
                out.append(normalized)
    material_type = _normalize_key(
        _first_present(subject, ["materialType", "material", "rawMaterialType", "commodity"])
    )
    if material_type and material_type not in out:
        out.append(material_type)
    return out


def _extract_certifications(subject: Dict[str, Any]) -> List[str]:
    out: List[str] = []

    def add_name(value: Any) -> None:
        normalized = _normalize_key(value)
        if normalized and normalized not in out:
            out.append(normalized)

    certifications = subject.get("certifications")
    if isinstance(certifications, list):
        for item in certifications:
            if isinstance(item, dict):
                add_name(item.get("name"))
            else:
                add_name(item)

    singleton = subject.get("certificateCredential")
    if isinstance(singleton, dict):
        add_name(singleton.get("name"))

    claims = subject.get("claims")
    if isinstance(claims, dict):
        nested = claims.get("certifications")
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    add_name(item.get("name"))

    return out


def _extract_environmental_claims(subject: Dict[str, Any]) -> Dict[str, Any]:
    price = subject.get("price")
    if isinstance(price, str):
        try:
            price = json.loads(price)
        except Exception:
            price = None

    energy_source = _first_present(
        subject,
        [
            "energySource",
            "energy.source",
            "emissions.energySource",
            "environment.energySource",
            "esgProfile.energySource",
        ],
    )
    emissions_claim = _first_present(
        subject,
        [
            "emissionsCertification",
            "emissionsClaim",
            "emissions.value",
            "environment.emissions",
            "claims.emissions",
            "esgProfile.emissionsClaim",
        ],
    )
    climate_claim = _first_present(
        subject,
        [
            "climateClaim",
            "sustainability.climate",
            "claims.climate",
            "carbonFootprint",
            "esgProfile.climateClaim",
        ],
    )
    has_price_commitment = isinstance(subject.get("priceCommitment"), dict) or (
        isinstance(price, dict) and bool(price.get("commitment"))
    )

    normalized_energy_source = _normalize_key(energy_source)

    return {
        "energySource": _normalize_text(energy_source),
        "energySourceTag": normalized_energy_source,
        "highRiskEnergySource": normalized_energy_source in {"coal", "coal_power", "coal_fired"},
        "emissionsClaim": _normalize_text(emissions_claim),
        "climateClaim": _normalize_text(climate_claim),
        "hasPriceCommitment": has_price_commitment,
    }


def extract_node_evidence(
    cid: str,
    vc: Dict[str, Any],
    graph_node: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    subject = vc.get("credentialSubject") if isinstance(vc, dict) else None
    subject = subject if isinstance(subject, dict) else {}

    location = _extract_location(subject)
    facility_role = _normalize_key(subject.get("facilityRole"))
    operation_tags = [_normalize_key(v) for v in subject.get("operationTags") or [] if _normalize_key(v)]
    did_issuer = _normalize_text(_get_path(vc, "issuer.id"))
    did_holder = _normalize_text(_get_path(vc, "holder.id"))
    certifications = _extract_certifications(subject)

    return {
        "cid": cid,
        "nodeIndex": (graph_node or {}).get("nodeIndex"),
        "productName": _normalize_text(subject.get("productName")),
        "productId": _normalize_text(subject.get("productId")),
        "productContract": _normalize_text(subject.get("productContract"))
        or _normalize_text((graph_node or {}).get("productContract")),
        "facilityRole": facility_role,
        "materialTags": _extract_material_tags(subject),
        "operationTags": operation_tags,
        "certifications": certifications,
        "location": location,
        "issuerDid": did_issuer or _normalize_text((graph_node or {}).get("issuerDid")),
        "holderDid": did_holder or _normalize_text((graph_node or {}).get("holderDid")),
        "environmentalClaims": _extract_environmental_claims(subject),
        "componentCount": len(subject.get("componentCredentials") or []),
    }


def build_esg_input(graph: Dict[str, Any], vcs_by_cid: Dict[str, Any]) -> Dict[str, Any]:
    node_map = {
        str(node.get("cid")): node
        for node in (graph.get("nodes") or [])
        if isinstance(node, dict) and node.get("cid")
    }

    nodes: List[Dict[str, Any]] = []
    for cid, vc in (vcs_by_cid or {}).items():
        if not isinstance(vc, dict):
            continue
        nodes.append(extract_node_evidence(str(cid), vc, node_map.get(str(cid))))

    return {
        "graph": graph or {},
        "nodes": nodes,
    }
