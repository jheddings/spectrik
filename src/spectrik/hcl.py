"""HCL loading engine — parse .hcl files into raw data dicts and workspace refs."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import hcl2

from .projects import Project
from .resolve import Resolver
from .workspace import BlueprintRef, OperationRef, ProjectRef, Workspace, WorkspaceRef

logger = logging.getLogger(__name__)

_STRATEGY_NAMES = frozenset(("present", "ensure", "absent"))


def _iter_blocks(
    data: dict[str, Any],
    key: str,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (name, block_data) pairs from an HCL2 labeled block list.

    HCL2 represents labeled blocks as a list of single-key dicts:
        {"blueprint": [{"base": {...}}, {"extended": {...}}]}

    This helper flattens that into: ("base", {...}), ("extended", {...})
    """
    for block in data.get(key, []):
        yield from block.items()


def _parse_op(strategy: str, spec_name: str, attrs: dict[str, Any]) -> OperationRef:
    """Create a single OperationRef from HCL strategy block data."""
    return OperationRef(name=spec_name, strategy=strategy, attrs=dict(attrs))


def _parse_ops(block_data: dict[str, Any]) -> list[OperationRef]:
    """Translate HCL strategy blocks into OperationRefs."""
    return [
        _parse_op(strategy, spec_name, attrs)
        for strategy in _STRATEGY_NAMES
        for spec_name, attrs in _iter_blocks(block_data, strategy)
    ]


def _parse_blueprint(name: str, data: dict[str, Any]) -> BlueprintRef:
    """Translate an HCL blueprint block into a BlueprintRef."""
    return BlueprintRef(
        name=name,
        includes=data.get("include", []),
        ops=_parse_ops(data),
        description=data.get("description", ""),
    )


def _parse_project(name: str, data: dict[str, Any]) -> ProjectRef:
    """Translate an HCL project block into a ProjectRef."""
    skip_keys = {"use", "include", "description"} | _STRATEGY_NAMES
    return ProjectRef(
        name=name,
        use=data.get("use", []),
        ops=_parse_ops(data),
        description=data.get("description", ""),
        attrs={k: v for k, v in data.items() if k not in skip_keys},
    )


def parse(
    file: Path,
    *,
    context: dict[str, Any] | None = None,
) -> list[WorkspaceRef]:
    """Parse an HCL file into workspace refs."""
    data = load(file, context=context)
    refs: list[WorkspaceRef] = []

    for block_type in data:
        match block_type:
            case "blueprint":
                refs.extend(
                    _parse_blueprint(name, block_data)
                    for name, block_data in _iter_blocks(data, block_type)
                )
            case "project":
                refs.extend(
                    _parse_project(name, block_data)
                    for name, block_data in _iter_blocks(data, block_type)
                )
            case _:
                raise ValueError(f"Unsupported block type: '{block_type}'")

    return refs


def scan[P: Project](
    path: str | Path,
    *,
    project_type: type[P] = Project,  # type: ignore[assignment]
    recurse: bool = True,
    context: dict[str, Any] | None = None,
) -> Workspace[P]:
    """Scan a directory for .hcl files and return a ready Workspace."""

    directory = Path(path)
    ws: Workspace[P] = Workspace(project_type=project_type)

    if not directory.is_dir():
        logger.warning("Directory '%s' does not exist; skipping scan", directory)
        return ws

    logger.info("Scanning '%s' (recurse=%s)", directory, recurse)
    glob = directory.rglob if recurse else directory.glob

    for hcl_file in glob("*.hcl"):
        ws.add(*parse(hcl_file, context=context))

    return ws


def load(
    file: Path,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and parse a single HCL file."""

    logger.info("Loading HCL file: %s", file)
    text = file.read_text()

    try:
        data = hcl2.loads(text)  # type: ignore[reportPrivateImportUsage]
    except Exception as exc:
        logger.error("Could not load file: %s", file, exc_info=exc)
        raise ValueError(f"{file}: {exc}") from exc

    if context:
        resolver = Resolver(context)
        try:
            data = resolver.resolve(data)
        except ValueError as exc:
            logger.error("Could not resolve file data: %s", file, exc_info=exc)
            raise ValueError(f"{file}: {exc}") from exc

    return data
