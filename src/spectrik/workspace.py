"""Workspace — a mutable, typed collection of parsed projects."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, overload

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


@dataclass
class WorkspaceRef(ABC):
    """Base class for all workspace references."""

    name: str

    @abstractmethod
    def resolve(self, workspace: Workspace) -> Any:
        """Return a ready-to-use instance using the workspace as context."""


@dataclass
class OperationRef(WorkspaceRef):
    """A configuration operation — a spec type + strategy + attributes."""

    strategy: str
    attrs: dict[str, Any]
    label: str | None = None

    def resolve(self, workspace: Workspace) -> SpecOp:
        if self.name not in _spec_registry:
            raise ValueError(f"Unknown spec type: '{self.name}'")
        spec_cls = _spec_registry[self.name]
        spec_instance = spec_cls(**self.attrs)
        strategy_cls = _STRATEGY_MAP[self.strategy]
        return strategy_cls(spec_instance)


@dataclass
class BlueprintRef(WorkspaceRef):
    """A blueprint reference — a named collection of operations with optional includes."""

    includes: list[str]
    ops: list[OperationRef]
    description: str = ""

    def resolve(
        self,
        workspace: Workspace,
        _resolving: set[str] | None = None,
    ) -> Blueprint:
        resolving = _resolving or set()
        if self.name in resolving:
            raise ValueError(f"Circular include detected: '{self.name}'")
        resolving.add(self.name)

        all_ops: list[SpecOp] = []

        for inc_name in self.includes:
            included_ref = workspace.blueprints[inc_name]
            included_bp = included_ref.resolve(workspace, resolving)
            all_ops.extend(included_bp.ops)

        all_ops.extend(op.resolve(workspace) for op in self.ops)

        resolving.discard(self.name)
        return Blueprint(name=self.name, ops=all_ops)


def _decode_spec(
    spec_name: str,
    attrs: dict[str, Any],
) -> Any:
    """Decode a spec block into a Specification instance using the registry."""
    if spec_name not in _spec_registry:
        raise ValueError(f"Unknown spec type: '{spec_name}'")
    spec_cls = _spec_registry[spec_name]
    logger.debug("Decoding spec '%s' -> %s", spec_name, spec_cls.__name__)
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
    logger.debug("Resolving blueprint '%s'", name)
    resolving.add(name)

    bp_data = pending[name]
    ops: list[SpecOp] = []

    # Resolve includes first
    for include_name in bp_data.get("include", []):
        logger.debug("Blueprint '%s' includes '%s'", name, include_name)
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
    """Build a single Project instance from parsed data."""
    logger.debug("Building project '%s' as %s", name, project_type.__name__)
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


class Workspace[P: Project](Mapping[str, P]):
    """Configured workspace that accumulates parsed data and resolves projects on access."""

    def __init__(
        self,
        project_type: type[P] = Project,  # type: ignore[assignment]
    ) -> None:
        self._project_type = project_type
        self._pending_blueprints: dict[str, dict[str, Any]] = {}
        self._pending_projects: dict[str, dict[str, Any]] = {}
        self._blueprint_refs: dict[str, BlueprintRef] = {}

    @property
    def blueprints(self) -> dict[str, BlueprintRef]:
        """Return the blueprint ref registry."""
        return self._blueprint_refs

    def add(self, ref: WorkspaceRef) -> None:
        """Register a workspace reference."""
        if isinstance(ref, BlueprintRef):
            self._blueprint_refs[ref.name] = ref

    def load(self, data: dict[str, Any]) -> None:
        """Extract blueprint and project blocks from a parsed data dict.

        Raises ValueError if any blueprint or project name is already loaded.
        """
        for bp_block in data.get("blueprint", []):
            for bp_name, bp_data in bp_block.items():
                if bp_name in self._pending_blueprints:
                    raise ValueError(f"Duplicate blueprint: '{bp_name}'")
                logger.debug("Found blueprint '%s'", bp_name)
                self._pending_blueprints[bp_name] = bp_data

        for proj_block in data.get("project", []):
            for proj_name, proj_data in proj_block.items():
                if proj_name in self._pending_projects:
                    raise ValueError(f"Duplicate project: '{proj_name}'")
                logger.debug("Found project '%s'", proj_name)
                self._pending_projects[proj_name] = proj_data

    def _resolve(self) -> dict[str, P]:
        """Resolve all pending blueprints and build typed project instances."""
        logger.debug(
            "Resolving %d blueprint(s) and %d project(s)",
            len(self._pending_blueprints),
            len(self._pending_projects),
        )

        # Resolve blueprints
        resolved_bps: dict[str, Any] = {}
        for name in self._pending_blueprints:
            _resolve_blueprint(name, self._pending_blueprints, resolved_bps, set())

        # Build projects
        projects: dict[str, P] = {}
        for proj_name, proj_data in self._pending_projects.items():
            projects[proj_name] = _build_project(
                proj_name,
                proj_data,
                resolved_bps,
                project_type=self._project_type,
            )
        return projects

    def __getitem__(self, name: str) -> P:
        return self._resolve()[name]

    def __contains__(self, name: object) -> bool:
        return name in self._pending_projects

    def __iter__(self) -> Iterator[str]:
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._pending_projects)

    @overload
    def get(self, name: str) -> P | None: ...
    @overload
    def get(self, name: str, default: P) -> P: ...
    @overload
    def get(self, name: str, default: None) -> P | None: ...
    def get(self, name: str, default: Any = None) -> P | None:
        return self._resolve().get(name, default)

    def filter(self, names: Iterable[str]) -> list[P]:
        """Return projects matching the given names, preserving input order."""
        resolved = self._resolve()
        return [p for n in names if (p := resolved.get(n)) is not None]

    def __repr__(self) -> str:
        type_name = self._project_type.__name__
        bp_count = len(self._pending_blueprints)
        proj_count = len(self._pending_projects)
        return f"Workspace(project_type={type_name}, blueprints={bp_count}, projects={proj_count})"
