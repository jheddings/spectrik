"""Workspace — a mutable, typed collection of parsed projects."""

from __future__ import annotations

import logging
import warnings
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self, overload

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
    source: Path | None = None

    def resolve(self, workspace: Workspace) -> SpecOp:
        if self.name not in _spec_registry:
            msg = f"Unknown spec type: '{self.name}'"
            if self.source is not None:
                msg += f" in {self.source}"
            msg += " — ensure the module registering this spec is imported"
            raise ValueError(msg)
        if self.strategy not in _STRATEGY_MAP:
            raise ValueError(f"Unknown strategy: '{self.strategy}'")
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

    def resolve(self, workspace: Workspace) -> Blueprint:
        return self._resolve(workspace, set())

    def _resolve(self, workspace: Workspace, resolving: set[str]) -> Blueprint:
        if self.name in resolving:
            raise ValueError(f"Circular include detected: '{self.name}'")
        resolving.add(self.name)

        all_ops: list[SpecOp] = []

        for inc_name in self.includes:
            included_ref = workspace.blueprints[inc_name]
            included_bp = included_ref._resolve(workspace, resolving)
            all_ops.extend(included_bp.ops)

        all_ops.extend(op.resolve(workspace) for op in self.ops)

        resolving.discard(self.name)
        return Blueprint(name=self.name, ops=all_ops)


@dataclass
class ProjectRef(WorkspaceRef):
    """A project reference — a named build target with blueprints and inline ops."""

    use: list[str]
    ops: list[OperationRef]
    type_name: str = "project"
    description: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)

    def resolve(self, workspace: Workspace) -> Project:
        from .projects import _project_registry

        if self.type_name not in _project_registry:
            raise ValueError(
                f"Unknown project type: '{self.type_name}'"
                " — ensure the module registering this project type is imported"
            )

        project_cls = _project_registry[self.type_name]

        blueprints: list[Blueprint] = []

        for bp_name in self.use:
            bp_ref = workspace.blueprints[bp_name]
            blueprints.append(bp_ref.resolve(workspace))

        inline_ops = [op.resolve(workspace) for op in self.ops]
        if inline_ops:
            blueprints.append(Blueprint(name=f"{self.name}:inline", ops=inline_ops))

        return project_cls(
            name=self.name,
            description=self.description,
            blueprints=blueprints,
            **self.attrs,
        )


class Workspace(Mapping[str, Project]):
    """Configured workspace that holds refs and resolves projects on access."""

    def __init__(self) -> None:
        self._blueprint_refs: dict[str, BlueprintRef] = {}
        self._project_refs: dict[str, ProjectRef] = {}

    @property
    def blueprints(self) -> Mapping[str, BlueprintRef]:
        return self._blueprint_refs

    @property
    def projects(self) -> Mapping[str, ProjectRef]:
        return self._project_refs

    def add(self, *refs: WorkspaceRef) -> None:
        """Add one or more refs to the workspace."""
        for ref in refs:
            match ref:
                case BlueprintRef():
                    if ref.name in self._blueprint_refs:
                        raise ValueError(f"Duplicate blueprint: '{ref.name}'")
                    logger.debug("Added blueprint '%s'", ref.name)
                    self._blueprint_refs[ref.name] = ref
                case ProjectRef():
                    if ref.name in self._project_refs:
                        raise ValueError(f"Duplicate project: '{ref.name}'")
                    logger.debug("Added project '%s'", ref.name)
                    self._project_refs[ref.name] = ref
                case _:
                    raise TypeError(
                        f"Unsupported ref type: {type(ref).__name__}. "
                        f"Expected BlueprintRef or ProjectRef."
                    )

    def __iadd__(self, ref: WorkspaceRef) -> Self:
        self.add(ref)
        return self

    def __getitem__(self, name: str) -> Project:
        return self._project_refs[name].resolve(self)

    def __contains__(self, name: object) -> bool:
        return name in self._project_refs

    def __iter__(self) -> Iterator[str]:
        return iter(self._project_refs)

    def __len__(self) -> int:
        return len(self._project_refs)

    @overload
    def get(self, name: str) -> Project | None: ...
    @overload
    def get(self, name: str, default: Project) -> Project: ...
    @overload
    def get(self, name: str, default: None) -> Project | None: ...
    def get(self, name: str, default: Any = None) -> Project | None:
        if name not in self._project_refs:
            return default
        return self._project_refs[name].resolve(self)

    def filter(self, names: Iterable[str]) -> list[Project]:
        """Return projects matching the given names, preserving input order.

        .. deprecated::
            Use :meth:`select` instead.
        """
        warnings.warn(
            "filter() is deprecated, use select() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.select(names=names)

    def select(
        self,
        *,
        name: str | None = None,
        names: Iterable[str] | None = None,
        project_type: type[Project] | None = None,
    ) -> list[Project]:
        """Return projects matching the given criteria.

        All filters are combined (intersection). With no filters, returns
        all projects.
        """
        target_names: list[str] | None = None
        if name is not None or names is not None:
            merged: list[str] = []
            if name is not None:
                merged.append(name)
            if names is not None:
                merged.extend(names)
            target_names = merged

        if target_names is not None:
            projects = [
                self._project_refs[n].resolve(self) for n in target_names if n in self._project_refs
            ]
        else:
            projects = list(self.values())

        if project_type is not None:
            projects = [p for p in projects if isinstance(p, project_type)]

        return projects

    def __repr__(self) -> str:
        bp_count = len(self._blueprint_refs)
        proj_count = len(self._project_refs)
        return f"Workspace(blueprints={bp_count}, projects={proj_count})"
