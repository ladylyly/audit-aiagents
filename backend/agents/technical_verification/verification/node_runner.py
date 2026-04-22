import json
import subprocess
from pathlib import Path
from typing import Any, Dict


def run_node_tool(tool_path: str | Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    tool_path = Path(tool_path)
    if not tool_path.exists():
        raise FileNotFoundError(f"Node tool not found: {tool_path}")

    proc = subprocess.run(
        ["node", str(tool_path)],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"Node tool failed: {tool_path}\n{proc.stderr.decode('utf-8', errors='replace')}"
        )

    out = proc.stdout.decode("utf-8")
    return json.loads(out or "{}")
