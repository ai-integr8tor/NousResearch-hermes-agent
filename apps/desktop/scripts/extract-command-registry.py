#!/usr/bin/env python3
"""Extract hermes_cli.commands.COMMAND_REGISTRY without importing Hermes.

The desktop tests use this helper so they can compare checked-in renderer data
against the Python registry without requiring PyYAML/prompt_toolkit to be
installed in the Node test environment.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any


FIELD_NAMES = (
    "name",
    "description",
    "category",
    "aliases",
    "args_hint",
    "subcommands",
    "cli_only",
    "gateway_only",
    "gateway_config_gate",
)

DEFAULTS: dict[str, Any] = {
    "aliases": (),
    "args_hint": "",
    "subcommands": (),
    "cli_only": False,
    "gateway_only": False,
    "gateway_config_gate": None,
}


def literal(node: ast.AST) -> Any:
    return ast.literal_eval(node)


def command_from_call(call: ast.Call) -> dict[str, Any] | None:
    if not isinstance(call.func, ast.Name) or call.func.id != "CommandDef":
        return None

    values = dict(DEFAULTS)
    for name, arg in zip(FIELD_NAMES, call.args, strict=False):
        values[name] = literal(arg)
    for kw in call.keywords:
        if kw.arg:
            values[kw.arg] = literal(kw.value)

    return {
        "name": values["name"],
        "description": values["description"],
        "category": values["category"],
        "aliases": list(values["aliases"]),
        "argsHint": values["args_hint"],
        "subcommands": list(values["subcommands"]),
        "cliOnly": bool(values["cli_only"]),
        "gatewayOnly": bool(values["gateway_only"]),
        "gatewayConfigGate": values["gateway_config_gate"],
    }


def extract_registry(source: str) -> list[dict[str, Any]]:
    module = ast.parse(source)

    for node in module.body:
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "COMMAND_REGISTRY" for target in node.targets
        ):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "COMMAND_REGISTRY":
            value = node.value

        if value is None:
            continue
        if not isinstance(value, ast.List):
            raise SystemExit("COMMAND_REGISTRY is not a list literal")

        commands: list[dict[str, Any]] = []
        for item in value.elts:
            if not isinstance(item, ast.Call):
                raise SystemExit("COMMAND_REGISTRY contains a non-call entry")
            command = command_from_call(item)
            if command is None:
                raise SystemExit("COMMAND_REGISTRY contains a non-CommandDef entry")
            commands.append(command)
        return commands

    raise SystemExit("COMMAND_REGISTRY assignment not found")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: extract-command-registry.py /path/to/hermes_cli/commands.py", file=sys.stderr)
        return 2

    commands_path = Path(sys.argv[1])
    commands = extract_registry(commands_path.read_text(encoding="utf-8"))
    print(json.dumps(commands, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
