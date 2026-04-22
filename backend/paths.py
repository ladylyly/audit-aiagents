from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parent

BACKEND_ENV_PATH = BACKEND_ROOT / ".env"

DATA_ROOT = REPO_ROOT / "data"
DATA_GENERATED_DIR = DATA_ROOT / "generated"
DATA_REPORTS_DIR = DATA_ROOT / "reports"

CONTRACTS_ROOT = REPO_ROOT / "contracts"
CONTRACT_TOOL_DIR = CONTRACTS_ROOT / "tools"

TECHNICAL_VERIFIER_TOOLS_DIR = BACKEND_ROOT / "integrations" / "technical_verifier_tools"
COMPLIANCE_ASSETS_DIR = BACKEND_ROOT / "assets" / "compliance"
ESG_ASSETS_DIR = BACKEND_ROOT / "assets" / "esg"
CERTIFICATION_ASSETS_DIR = BACKEND_ROOT / "assets" / "certification"

THESIS_ROOT = REPO_ROOT / "thesis"
THESIS_SOURCES_DIR = THESIS_ROOT / "sources"

ZKP_BACKEND_DIR = REPO_ROOT / "tools" / "zkp-backend"
ZKP_CLI_PATH = ZKP_BACKEND_DIR / "target" / "release" / "zkp-cli"
