"""HCL loading engine — parse .hcl files into Blueprints and Projects."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .workspace import Workspace

import hcl2

from .blueprints import Blueprint
from .projects import Project
from .spec import _spec_registry
from .specop import Absent, Ensure, Present, SpecOp

logger = logging.getLogger(__name__)

_STRATEGY_MAP: dict[str, type[SpecOp]] = {
    "present": Present,
    "ensure": Ensure,
    "absent": Absent,
}

_VAR_PATTERN = re.compile(r"\$\{(?:env\.(\w+)|(\w+))\}")

_BUILTIN_VARS: dict[str, Callable[[], str]] = {
    "CWD": os.getcwd,
}


def scan[P: Project](
    path: str | Path,
    *,
    project_type: type[P] = Project,  # type: ignore[assignment]
    recurse: bool = True,
) -> Workspace[P]:
    """Scan a directory for .hcl files and return a ready Workspace."""
    from .workspace import Workspace

    ws = Workspace(project_type=project_type)
    ws.scan(path, recurse=recurse)
    return ws


def load(
    file: Path,
) -> dict[str, Any]:
    """Load and parse a single HCL file."""
    with file.open() as f:
        return hcl2.load(f)  # type: ignore[reportPrivateImportUsage]


def _expand_var(match: re.Match) -> str:
    """Expand a single ${...} variable reference."""
    env_name = match.group(1)
    builtin_name = match.group(2)
    if env_name is not None:
        if env_name not in os.environ:
            logger.warning("Environment variable '%s' is not set", env_name)
        return os.environ.get(env_name, "")
    if builtin_name is not None and builtin_name in _BUILTIN_VARS:
        return _BUILTIN_VARS[builtin_name]()
    logger.warning("Unknown variable '%s'", builtin_name)
    return match.group(0)


def _interpolate_value(value: Any) -> Any:
    """Expand ${env.VAR} and ${CWD} references in a string value."""
    if isinstance(value, str) and "${" in value:
        return _VAR_PATTERN.sub(_expand_var, value)
    return value


def _interpolate_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """Expand variable references in all attribute values."""
    return {k: _interpolate_value(v) for k, v in attrs.items()}


def _decode_spec(
    spec_name: str,
    attrs: dict[str, Any],
) -> Any:
    """Decode a spec block into a Specification instance using the registry."""
    if spec_name not in _spec_registry:
        raise ValueError(f"Unknown spec type: '{spec_name}'")
    attrs = _interpolate_attrs(attrs)
    spec_cls = _spec_registry[spec_name]
    return spec_cls(**attrs)


def _parse_ops(
    block_data: dict[str, Any],
) -> list[SpecOp]:
    """Parse strategy blocks (present/ensure/absent) from a blueprint or project block.

    HCL2 structure for strategy blocks:
        {"ensure": [{"widget": {"color": "blue"}}, ...], ...}
    """
    ops: list[SpecOp] = []
    for strategy_name, strategy_cls in _STRATEGY_MAP.items():
        for spec_block in block_data.get(strategy_name, []):
            # Each spec_block is {"spec_name": {attrs}}
            for spec_name, attrs in spec_block.items():
                spec_instance = _decode_spec(spec_name, dict(attrs))
                ops.append(strategy_cls(spec_instance))
    return ops


def _resolve_blueprint(
    name: str,
    pending: dict[str, dict[str, Any]],
    resolved: dict[str, Blueprint],
    resolving: set[str],
) -> Blueprint:
    """Recursively resolve a single blueprint, handling includes."""
    if name in resolved:
        return resolved[name]
    if name in resolving:
        raise ValueError(f"Circular include detected: '{name}'")
    if name not in pending:
        raise ValueError(f"Unknown blueprint: '{name}'")
    resolving.add(name)

    bp_data = pending[name]
    ops: list[SpecOp] = []

    # Resolve includes first
    for include_name in bp_data.get("include", []):
        included_bp = _resolve_blueprint(include_name, pending, resolved, resolving)
        ops.extend(included_bp.ops)

    # Parse own ops
    ops.extend(_parse_ops(bp_data))

    bp = Blueprint(name=name, ops=ops)
    resolved[name] = bp
    resolving.discard(name)
    return bp


def _build_project[P: Project](
    name: str,
    data: dict[str, Any],
    blueprints: dict[str, Blueprint],
    *,
    project_type: type[P] = Project,  # type: ignore[assignment]
) -> P:
    """Build a single Project instance from parsed HCL data."""
    # Collect blueprints from 'use' references
    proj_blueprints: list[Blueprint] = []
    for bp_name in data.get("use", []):
        if bp_name not in blueprints:
            raise ValueError(f"Project '{name}' references unknown blueprint: '{bp_name}'")
        proj_blueprints.append(blueprints[bp_name])

    # Parse inline spec ops into an anonymous blueprint
    inline_ops = _parse_ops(data)
    if inline_ops:
        proj_blueprints.append(Blueprint(name=f"{name}:inline", ops=inline_ops))

    # Build project kwargs
    proj_kwargs: dict[str, Any] = {"name": name, "blueprints": proj_blueprints}

    # Pass through non-structural fields
    skip_keys = {"use", "include"} | set(_STRATEGY_MAP.keys())
    for key, value in data.items():
        if key not in skip_keys:
            proj_kwargs[key] = value

    return project_type(**proj_kwargs)
