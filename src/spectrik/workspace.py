"""Workspace — a mutable, typed collection of parsed projects."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
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


@dataclass
class ProjectRef(WorkspaceRef):
    """A project reference — a named build target with blueprints and inline ops."""

    use: list[str]
    ops: list[OperationRef]
    description: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)

    def resolve(self, workspace: Workspace) -> Project:
        blueprints: list[Blueprint] = []

        for bp_name in self.use:
            bp_ref = workspace.blueprints[bp_name]
            blueprints.append(bp_ref.resolve(workspace))

        inline_ops = [op.resolve(workspace) for op in self.ops]
        if inline_ops:
            blueprints.append(Blueprint(name=f"{self.name}:inline", ops=inline_ops))

        return workspace.project_type(
            name=self.name,
            description=self.description,
            blueprints=blueprints,
            **self.attrs,
        )


class Workspace[P: Project](Mapping[str, P]):
    """Configured workspace that holds typed refs and resolves projects on access."""

    def __init__(
        self,
        project_type: type[P] = Project,  # type: ignore[assignment]
    ) -> None:
        self._project_type = project_type
        self._blueprint_refs: dict[str, BlueprintRef] = {}
        self._project_refs: dict[str, ProjectRef] = {}

    @property
    def project_type(self) -> type[P]:
        return self._project_type

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

    def __getitem__(self, name: str) -> P:
        return self._project_refs[name].resolve(self)  # type: ignore[return-value]

    def __contains__(self, name: object) -> bool:
        return name in self._project_refs

    def __iter__(self) -> Iterator[str]:
        return iter(self._project_refs)

    def __len__(self) -> int:
        return len(self._project_refs)

    @overload
    def get(self, name: str) -> P | None: ...
    @overload
    def get(self, name: str, default: P) -> P: ...
    @overload
    def get(self, name: str, default: None) -> P | None: ...
    def get(self, name: str, default: Any = None) -> P | None:
        if name not in self._project_refs:
            return default
        return self._project_refs[name].resolve(self)  # type: ignore[return-value]

    def filter(self, names: Iterable[str]) -> list[P]:
        """Return projects matching the given names, preserving input order."""
        return [self._project_refs[n].resolve(self) for n in names if n in self._project_refs]  # type: ignore[misc]

    def __repr__(self) -> str:
        type_name = self._project_type.__name__
        bp_count = len(self._blueprint_refs)
        proj_count = len(self._project_refs)
        return f"Workspace(project_type={type_name}, blueprints={bp_count}, projects={proj_count})"
