import json
from typing import Any, Dict


def extract_zkp_payload(vc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mirrors ev-battery-supplychain-ly/frontend/src/utils/verifyZKP.js (extractZKPProof).

    Supported locations:
    - credentialSubject.priceCommitment (current)
    - credentialSubject.price (legacy stringified JSON) -> price.zkpProof
    """
    subject = vc.get("credentialSubject") if isinstance(vc, dict) else None
    if not isinstance(subject, dict):
        raise ValueError("VC missing credentialSubject")

    price_commitment = subject.get("priceCommitment")
    if isinstance(price_commitment, dict) and price_commitment.get("commitment") and price_commitment.get("proof"):
        return {
            "commitment": price_commitment.get("commitment"),
            "proof": price_commitment.get("proof"),
            "protocol": price_commitment.get("protocol"),
            "version": price_commitment.get("version"),
            "encoding": price_commitment.get("encoding"),
            "verified": price_commitment.get("verified"),
            "description": price_commitment.get("description"),
            "proofType": price_commitment.get("proofType"),
            "bindingTag": price_commitment.get("bindingTag"),
            "bindingContext": price_commitment.get("bindingContext"),
        }

    price = subject.get("price")
    if isinstance(price, str):
        try:
            price = json.loads(price)
        except Exception:
            price = {}

    zkp = price.get("zkpProof") if isinstance(price, dict) else None
    if isinstance(zkp, dict) and zkp.get("commitment") and zkp.get("proof"):
        return {
            "commitment": zkp.get("commitment"),
            "proof": zkp.get("proof"),
            "protocol": zkp.get("protocol"),
            "version": zkp.get("version"),
            "encoding": zkp.get("encoding"),
            "verified": zkp.get("verified"),
            "description": zkp.get("description"),
            "proofType": zkp.get("proofType"),
            "bindingTag": zkp.get("bindingTag"),
            "bindingContext": zkp.get("bindingContext"),
        }

    raise ValueError(
        "ZKP proof is missing or malformed in VC (expected credentialSubject.priceCommitment or credentialSubject.price.zkpProof)"
    )


def extract_tx_hash_payload(vc: Dict[str, Any], field_name: str = "txHashCommitment") -> Dict[str, Any]:
    subject = vc.get("credentialSubject") if isinstance(vc, dict) else None
    if not isinstance(subject, dict):
        raise ValueError("VC missing credentialSubject")

    obj = subject.get(field_name)
    if not isinstance(obj, dict):
        raise ValueError(f"{field_name} is missing or malformed in VC")
    if not obj.get("commitment") or not obj.get("proof"):
        raise ValueError(f"{field_name} is missing commitment or proof")

    return {
        "commitment": obj.get("commitment"),
        "proof": obj.get("proof"),
        "protocol": obj.get("protocol"),
        "version": obj.get("version"),
        "encoding": obj.get("encoding"),
        "bindingTag": obj.get("bindingTag"),
        "bindingContext": obj.get("bindingContext"),
    }
