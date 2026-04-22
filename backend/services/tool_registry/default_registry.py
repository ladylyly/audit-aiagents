from typing import Any, Dict

from backend.agents.certification.evaluator import evaluate_certifications
from backend.agents.compliance.evaluator import evaluate_compliance
from backend.agents.esg.evaluator import evaluate_esg
from backend.agents.technical_verification.verification.technical_verify import verify_all
from backend.paths import CONTRACT_TOOL_DIR
from backend.services.tool_registry.certification_explanations import (
    explain_findings as explain_certification_findings,
)
from backend.services.tool_registry.compliance_explanations import (
    explain_findings as explain_compliance_findings,
)
from backend.services.tool_registry.esg_explanations import explain_assessment
from backend.services.tool_registry.registry import ToolRegistry
from backend.services.tool_registry.technical_explanations import (
    explain_failures as explain_technical_failures,
)


def create_default_registry() -> ToolRegistry:
    implementations = {
        "technical.explain_failures@v1": explain_technical_failures,
        "compliance.explain_findings@v1": explain_compliance_findings,
        "esg.explain_assessment@v1": explain_assessment,
        "certification.explain_findings@v1": explain_certification_findings,
        "compliance.verify@v1": evaluate_compliance,
        "certification.verify@v1": evaluate_certifications,
        "esg.verify@v1": evaluate_esg,
        "technical.verify_all@v1": _impl_verify_all,
    }

    reg = ToolRegistry(contracts_dir=str(CONTRACT_TOOL_DIR), implementations=implementations)
    reg.load()
    return reg


def _impl_verify_all(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    root_cid = tool_input.get("rootCid")
    options = tool_input.get("options") if isinstance(tool_input.get("options"), dict) else {}
    return verify_all(str(root_cid), options=options)
