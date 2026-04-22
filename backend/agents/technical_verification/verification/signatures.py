from typing import Any, Dict, Optional

from backend.agents.technical_verification.verification.node_runner import run_node_tool
from backend.paths import TECHNICAL_VERIFIER_TOOLS_DIR


def verify_vc_signature(vc: Dict[str, Any], *, contract_address: Optional[str] = None) -> Dict[str, Any]:
    tool_path = TECHNICAL_VERIFIER_TOOLS_DIR / "verify_vc_signature.mjs"

    payload: Dict[str, Any] = {"vc": vc}
    if contract_address:
        payload["contractAddress"] = contract_address

    return run_node_tool(tool_path, payload)
