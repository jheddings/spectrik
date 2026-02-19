"""Workspace — a mutable, typed collection of HCL-loaded projects."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, overload

from .projects import Project

logger = logging.getLogger(__name__)


class Workspace[P: Project](Mapping[str, P]):
    """Configured workspace that accumulates HCL data and resolves projects on access.

    Construct with an optional project_type (defaults to Project), then call
    load() or scan() to add HCL data. Projects are resolved fresh on each
    Mapping access.
    """

    def __init__(self, project_type: type[P] = Project) -> None:  # type: ignore[assignment]
        self._project_type = project_type
        self._pending_blueprints: dict[str, dict[str, Any]] = {}
        self._pending_projects: dict[str, dict[str, Any]] = {}

    def load(self, file: str | Path) -> None:
        """Parse a single HCL file and extract blueprint/project blocks.

        Raises ValueError if any blueprint or project name is already loaded.
        """
        from spectrik.hcl import load as hcl_load

        path = Path(file)
        logger.info("Loading '%s'", path)
        doc = hcl_load(path)

        # Extract blueprint blocks
        for bp_block in doc.get("blueprint", []):
            for bp_name, bp_data in bp_block.items():
                if bp_name in self._pending_blueprints:
                    raise ValueError(f"Duplicate blueprint: '{bp_name}'")
                logger.debug("Found blueprint '%s'", bp_name)
                self._pending_blueprints[bp_name] = bp_data

        # Extract project blocks
        for proj_block in doc.get("project", []):
            for proj_name, proj_data in proj_block.items():
                if proj_name in self._pending_projects:
                    raise ValueError(f"Duplicate project: '{proj_name}'")
                logger.debug("Found project '%s'", proj_name)
                self._pending_projects[proj_name] = proj_data

    def scan(self, path: str | Path, *, recurse: bool = True) -> None:
        """Discover .hcl files in a directory and load each one.

        With recurse=True (default), walks subdirectories. Files are
        processed in sorted order for deterministic behavior.
        """
        directory = Path(path)
        if not directory.is_dir():
            logger.warning("Directory '%s' does not exist; skipping scan", directory)
            return

        logger.info("Scanning '%s' (recurse=%s)", directory, recurse)

        if recurse:
            hcl_files = sorted(directory.rglob("*.hcl"))
        else:
            hcl_files = sorted(directory.glob("*.hcl"))

        for hcl_file in hcl_files:
            self.load(hcl_file)

    def _resolve(self) -> dict[str, P]:
        """Resolve all pending blueprints and build typed project instances."""
        from spectrik.hcl import _build_project, _resolve_blueprint

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
