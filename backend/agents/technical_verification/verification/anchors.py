from typing import Any, Dict, List

from backend.agents.technical_verification.verification.node_runner import run_node_tool
from backend.paths import TECHNICAL_VERIFIER_TOOLS_DIR


def verify_vc_anchors(*, rpc_url: str, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    tool_path = TECHNICAL_VERIFIER_TOOLS_DIR / "check_vc_anchors.mjs"
    return run_node_tool(tool_path, {"rpcUrl": rpc_url, "nodes": nodes})


def verify_price_commitment_anchors(*, rpc_url: str, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    tool_path = TECHNICAL_VERIFIER_TOOLS_DIR / "check_price_commitment_anchors.mjs"
    return run_node_tool(tool_path, {"rpcUrl": rpc_url, "nodes": nodes})
