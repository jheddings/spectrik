"""Workspace — a typed Mapping of loaded projects."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, overload

from spectrik.projects import Project


class Workspace[P: Project](Mapping[str, P]):
    """Typed, read-only collection of projects returned by Workspace.load()."""

    def __init__(self, projects: dict[str, P]) -> None:
        self._projects = dict(projects)

    def __getitem__(self, name: str) -> P:
        return self._projects[name]

    def __contains__(self, name: object) -> bool:
        return name in self._projects

    def __iter__(self) -> Iterator[str]:
        return iter(self._projects)

    def __len__(self) -> int:
        return len(self._projects)

    @overload
    def get(self, name: str) -> P | None: ...
    @overload
    def get(self, name: str, default: P) -> P: ...
    @overload
    def get(self, name: str, default: None) -> P | None: ...
    def get(self, name: str, default: Any = None) -> P | None:
        return self._projects.get(name, default)

    @classmethod
    def load[T: Project](cls, project_type: type[T], base_path: Path) -> Workspace[T]:
        """Load blueprints and projects from base_path, return a Workspace."""
        from spectrik.hcl import load_blueprints, load_projects

        blueprints = load_blueprints(base_path)
        projects = load_projects(base_path, blueprints, project_type=project_type)
        return Workspace(projects)

    def filter(self, names: Iterable[str]) -> list[P]:
        """Return projects matching the given names, preserving input order."""
        return [p for n in names if (p := self._projects.get(n)) is not None]
