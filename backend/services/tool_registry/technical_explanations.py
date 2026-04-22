from typing import Any, Dict

from backend.integrations.llm_client import LLMClient


def explain_failures(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    failures = tool_input.get("failures") or []
    context = tool_input.get("context") or {}
    return LLMClient().diagnose_technical_failures(failures=failures, context=context)
