"""HCL loading engine — parse .hcl files into Blueprints and Projects."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import hcl2

from spectrik.blueprints import Blueprint
from spectrik.projects import Project
from spectrik.specs import Absent, Ensure, Present, SpecOp, _spec_registry
from spectrik.workspace import Workspace

logger = logging.getLogger(__name__)

_STRATEGY_MAP: dict[str, type[SpecOp]] = {
    "present": Present,
    "ensure": Ensure,
    "absent": Absent,
}


def load(
    file: Path,
    *,
    resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Load and parse a single HCL file."""
    with file.open() as f:
        return hcl2.load(f)  # type: ignore[reportPrivateImportUsage]


def scan(
    directory: Path,
    *,
    resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Load and parse all .hcl files in a directory (sorted)."""
    if not directory.is_dir():
        return []
    results = []
    for hcl_file in sorted(directory.glob("*.hcl")):
        results.append(load(hcl_file, resolve_attrs=resolve_attrs))
    return results


def _decode_spec(
    spec_name: str,
    attrs: dict[str, Any],
    *,
    resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> Any:
    """Decode a spec block into a Specification instance using the registry."""
    if spec_name not in _spec_registry:
        raise ValueError(f"Unknown spec type: '{spec_name}'")
    if resolve_attrs:
        attrs = resolve_attrs(attrs)
    spec_cls = _spec_registry[spec_name]
    return spec_cls(**attrs)


def _parse_ops(
    block_data: dict[str, Any],
    *,
    resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
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
                spec_instance = _decode_spec(spec_name, dict(attrs), resolve_attrs=resolve_attrs)
                ops.append(strategy_cls(spec_instance))
    return ops


def _collect_pending_blueprints(raw_docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Extract blueprint name -> data mapping from parsed HCL documents."""
    pending: dict[str, dict[str, Any]] = {}
    for doc in raw_docs:
        for bp_block in doc.get("blueprint", []):
            for bp_name, bp_data in bp_block.items():
                pending[bp_name] = bp_data
    return pending


def _resolve_blueprint(
    name: str,
    pending: dict[str, dict[str, Any]],
    resolved: dict[str, Blueprint],
    resolving: set[str],
    *,
    resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
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
        included_bp = _resolve_blueprint(
            include_name, pending, resolved, resolving, resolve_attrs=resolve_attrs
        )
        ops.extend(included_bp.ops)

    # Parse own ops
    ops.extend(_parse_ops(bp_data, resolve_attrs=resolve_attrs))

    bp = Blueprint(name=name, ops=ops)
    resolved[name] = bp
    resolving.discard(name)
    return bp


def load_blueprints(
    base_path: Path,
    *,
    resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Blueprint]:
    """Scan base_path/blueprints/, resolve includes, return registry."""
    bp_dir = base_path / "blueprints"
    raw_docs = scan(bp_dir)
    pending = _collect_pending_blueprints(raw_docs)

    resolved: dict[str, Blueprint] = {}
    for name in pending:
        _resolve_blueprint(name, pending, resolved, set(), resolve_attrs=resolve_attrs)

    return resolved


def load_projects[P: Project](
    base_path: Path,
    blueprints: dict[str, Blueprint],
    *,
    project_type: type[P] = Project,  # type: ignore[assignment]
    resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, P]:
    """Scan base_path/projects/, resolve 'use' references, return registry."""
    proj_dir = base_path / "projects"
    raw_docs = scan(proj_dir)

    projects: dict[str, P] = {}
    for doc in raw_docs:
        for proj_block in doc.get("project", []):
            for proj_name, proj_data in proj_block.items():
                projects[proj_name] = _build_project(
                    proj_name,
                    proj_data,
                    blueprints,
                    project_type=project_type,
                    resolve_attrs=resolve_attrs,
                )

    return projects


def _build_project[P: Project](
    name: str,
    data: dict[str, Any],
    blueprints: dict[str, Blueprint],
    *,
    project_type: type[P] = Project,  # type: ignore[assignment]
    resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> P:
    """Build a single Project instance from parsed HCL data."""
    # Collect blueprints from 'use' references
    proj_blueprints: list[Blueprint] = []
    for bp_name in data.get("use", []):
        if bp_name not in blueprints:
            raise ValueError(f"Project '{name}' references unknown blueprint: '{bp_name}'")
        proj_blueprints.append(blueprints[bp_name])

    # Parse inline spec ops into an anonymous blueprint
    inline_ops = _parse_ops(data, resolve_attrs=resolve_attrs)
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


# ---------------------------------------------------------------------------
# ProjectLoader — high-level façade
# ---------------------------------------------------------------------------


class ProjectLoader[P: Project]:
    """Configured loader that turns an HCL directory into a Workspace."""

    def __init__(
        self,
        project_type: type[P],
        resolve_attrs: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.project_type = project_type
        self.resolve_attrs = resolve_attrs

    def load(self, base_path: Path) -> Workspace[P]:
        """Load blueprints and projects from base_path, return a Workspace."""
        blueprints = load_blueprints(base_path, resolve_attrs=self.resolve_attrs)
        projects = load_projects(
            base_path,
            blueprints,
            project_type=self.project_type,
            resolve_attrs=self.resolve_attrs,
        )
        return Workspace(projects)
