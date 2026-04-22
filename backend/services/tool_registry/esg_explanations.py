from typing import Any, Dict, List

from backend.integrations.llm_client import LLMClient


def explain_assessment(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    return LLMClient().enrich_esg_assessment(
        verdict=str(tool_input.get("verdict") or "UNKNOWN"),
        scores=tool_input.get("scores") or {},
        narrative_seed=str(tool_input.get("narrativeSeed") or ""),
        findings=[x for x in (tool_input.get("findings") or []) if isinstance(x, dict)][:40],
        context={
            "rootCid": tool_input.get("rootCid"),
            "flags": [str(x) for x in (tool_input.get("flags") or []) if isinstance(x, str)],
            "coverage": tool_input.get("coverage") or {},
        },
    )
