import json
import os
import subprocess
from typing import Any, Dict, Optional

from backend.paths import ZKP_CLI_PATH


def _default_cli_path() -> str:
    return os.fspath(ZKP_CLI_PATH)


def verify_value_commitment(
    *,
    commitment_hex: str,
    proof_hex: str,
    binding_tag_hex: Optional[str] = None,
    cli_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Local-only (no HTTP) ZKP verification by calling the vendored Rust CLI.
    """
    cli = cli_path or os.getenv("ZKP_CLI_PATH") or _default_cli_path()
    if not os.path.exists(cli):
        return {
            "skipped": True,
            "verified": None,
            "reason": f"zkp-cli not found at {cli}. Build it with: (cd tools/zkp-backend && cargo build --release --bin zkp-cli)",
        }

    payload: Dict[str, Any] = {
        "op": "verify-value-commitment",
        "commitment": commitment_hex,
        "proof": proof_hex,
    }
    if binding_tag_hex:
        payload["binding_tag_hex"] = binding_tag_hex

    proc = subprocess.run(
        [cli],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if proc.returncode != 0:
        return {
            "skipped": False,
            "verified": False,
            "error": proc.stderr.decode("utf-8", errors="replace"),
        }

    return _parse_cli_json(proc.stdout.decode("utf-8", errors="replace"))


def verify_tx_hash_commitment(
    *,
    commitment_hex: str,
    proof_hex: str,
    binding_tag_hex: Optional[str] = None,
    cli_path: Optional[str] = None,
) -> Dict[str, Any]:
    cli = cli_path or os.getenv("ZKP_CLI_PATH") or _default_cli_path()
    if not os.path.exists(cli):
        return {
            "skipped": True,
            "verified": None,
            "reason": f"zkp-cli not found at {cli}. Build it with: (cd tools/zkp-backend && cargo build --release --bin zkp-cli)",
        }

    payload: Dict[str, Any] = {
        "op": "verify-tx-hash-commitment",
        "commitment": commitment_hex,
        "proof": proof_hex,
    }
    if binding_tag_hex:
        payload["binding_tag_hex"] = binding_tag_hex

    proc = subprocess.run(
        [cli],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if proc.returncode != 0:
        return {
            "skipped": False,
            "verified": False,
            "error": proc.stderr.decode("utf-8", errors="replace"),
        }

    return _parse_cli_json(proc.stdout.decode("utf-8", errors="replace"))


def _parse_cli_json(stdout: str) -> Dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}

    start = text.rfind("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"zkp-cli did not return JSON. Raw stdout: {text[:500]}")
    return json.loads(text[start : end + 1])
