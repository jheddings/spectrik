"""HCL loading engine — parse .hcl files into raw data dicts and workspace refs."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import hcl2
from hcl2 import SerializationOptions

from .resolve import Resolver
from .workspace import BlueprintRef, OperationRef, ProjectRef, Workspace, WorkspaceRef

logger = logging.getLogger(__name__)

_STRATEGY_NAMES = frozenset(("present", "ensure", "absent"))
_SERIALIZATION_OPTS = SerializationOptions(
    strip_string_quotes=True,
    explicit_blocks=False,
)


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


def _parse_op(
    strategy: str,
    spec_name: str,
    attrs: dict[str, Any],
    *,
    source: Path | None = None,
) -> OperationRef:
    """Create a single OperationRef from HCL strategy block data."""
    return OperationRef(name=spec_name, strategy=strategy, attrs=dict(attrs), source=source)


def _parse_ops(
    block_data: dict[str, Any],
    *,
    source: Path | None = None,
) -> list[OperationRef]:
    """Translate HCL strategy blocks into OperationRefs."""
    return [
        _parse_op(strategy, spec_name, attrs, source=source)
        for strategy in _STRATEGY_NAMES
        for spec_name, attrs in _iter_blocks(block_data, strategy)
    ]


def _parse_blueprint(
    name: str,
    data: dict[str, Any],
    *,
    source: Path | None = None,
) -> BlueprintRef:
    """Translate an HCL blueprint block into a BlueprintRef."""
    return BlueprintRef(
        name=name,
        includes=data.get("include", []),
        ops=_parse_ops(data, source=source),
        description=data.get("description", ""),
    )


def _parse_project(
    name: str,
    data: dict[str, Any],
    *,
    type_name: str = "project",
    source: Path | None = None,
) -> ProjectRef:
    """Translate an HCL project block into a ProjectRef."""
    skip_keys = {"use", "include", "description"} | _STRATEGY_NAMES
    return ProjectRef(
        name=name,
        type_name=type_name,
        use=data.get("use", []),
        ops=_parse_ops(data, source=source),
        description=data.get("description", ""),
        attrs={k: v for k, v in data.items() if k not in skip_keys},
    )


def _extract_variables(
    data: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Extract and resolve variable/variables blocks from parsed HCL data.

    Processes ``variable`` blocks first (in order), then ``variables``
    blocks.  Within each block, values are resolved against the Python
    *context* plus any previously resolved variables (under ``var``).

    Resolved entries are removed from *data* (mutates in place).
    """
    resolved: dict[str, Any] = {}

    def _resolve_single(raw: Any) -> Any:
        """Resolve a single value using the current context + resolved vars."""
        # resolve() expects a dict; wrap/unwrap to resolve a single value
        resolver = Resolver({**context, "var": resolved})
        return resolver.resolve({"_": raw})["_"]

    for block in data.pop("variable", []):
        for name, body in block.items():
            if "value" not in body:
                raise ValueError(f"variable '{name}' is missing a 'value' attribute")
            resolved[name] = _resolve_single(body["value"])
            logger.debug("Resolved variable '%s'", name)

    for block in data.pop("variables", []):
        for name, value in block.items():
            resolved[name] = _resolve_single(value)
            logger.debug("Resolved variable '%s'", name)

    return resolved


def parse(
    file: Path,
    *,
    context: dict[str, Any] | None = None,
) -> list[WorkspaceRef]:
    """Parse an HCL file into workspace refs."""
    from .projects import _project_registry

    data = load(file, context=context)
    refs: list[WorkspaceRef] = []

    for block_type in data:
        if block_type == "blueprint":
            refs.extend(
                _parse_blueprint(name, block_data, source=file)
                for name, block_data in _iter_blocks(data, block_type)
            )
        elif block_type in _project_registry:
            refs.extend(
                _parse_project(name, block_data, type_name=block_type, source=file)
                for name, block_data in _iter_blocks(data, block_type)
            )
        else:
            raise ValueError(f"Unsupported block type: '{block_type}'")

    return refs


def scan(
    path: str | Path,
    *,
    recurse: bool = True,
    context: dict[str, Any] | None = None,
) -> Workspace:
    """Scan a directory for .hcl files and return a ready Workspace."""

    directory = Path(path)
    ws = Workspace()

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
        data = hcl2.loads(text, serialization_options=_SERIALIZATION_OPTS)
    except Exception as exc:
        logger.error("Could not load file: %s", file, exc_info=exc)
        raise ValueError(f"{file}: {exc}") from exc

    base_context = context or {}

    try:
        variables = _extract_variables(data, base_context)
    except ValueError as exc:
        raise ValueError(f"{file}: {exc}") from exc

    if variables:
        if "var" in base_context:
            logger.warning(
                "context key 'var' is reserved for HCL variables and will be overwritten"
            )
        full_context = {**base_context, "var": variables}
    else:
        full_context = base_context

    if full_context:
        resolver = Resolver(full_context)
        try:
            data = resolver.resolve(data)
        except ValueError as exc:
            logger.error("Could not resolve file data: %s", file, exc_info=exc)
            raise ValueError(f"{file}: {exc}") from exc

    return data
