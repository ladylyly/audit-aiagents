import glob
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

import jsonschema
import yaml


@dataclass(frozen=True)
class ToolContract:
    tool_id: str
    contract: Dict[str, Any]

    @property
    def input_schema(self) -> Dict[str, Any]:
        return self.contract.get("input_schema") or {}

    @property
    def output_schema(self) -> Dict[str, Any]:
        return self.contract.get("output_schema") or {}


class ToolRegistry:

    def __init__(self, contracts_dir: str, implementations: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]):
        self.contracts_dir = contracts_dir
        self.implementations = implementations
        self.contracts: Dict[str, ToolContract] = {}

    def load(self) -> None:
        pattern = os.path.join(self.contracts_dir, "*.yaml")
        for path in glob.glob(pattern):
            with open(path, "r", encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            tool_id = doc.get("tool_id")
            if not tool_id:
                continue
            self.contracts[tool_id] = ToolContract(tool_id=tool_id, contract=doc)

    def list_tools(self) -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "tool_id": t.tool_id,
                    "description": t.contract.get("description", ""),
                    "category": t.contract.get("category", ""),
                }
                for t in self.contracts.values()
            ]
        }

    def execute(self, tool_id: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        contract = self.contracts.get(tool_id)
        if not contract:
            raise KeyError(f"Unknown tool_id: {tool_id}")
        impl = self.implementations.get(tool_id)
        if not impl:
            raise KeyError(f"No implementation registered for tool_id: {tool_id}")

        self._validate(contract.input_schema, tool_input, where=f"{tool_id} input")
        output = impl(tool_input)
        self._validate(contract.output_schema, output, where=f"{tool_id} output")
        return output

    def _validate(self, schema: Dict[str, Any], instance: Any, *, where: str) -> None:
        if not schema:
            return
        try:
            jsonschema.validate(instance=instance, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Schema validation failed for {where}: {e.message}") from e

