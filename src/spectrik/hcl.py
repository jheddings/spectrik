"""HCL loading engine — parse .hcl files into raw data dicts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import hcl2
import jinja2

from .projects import Project
from .workspace import Workspace

logger = logging.getLogger(__name__)


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
    pattern_func = directory.rglob if recurse else directory.glob
    for hcl_file in sorted(pattern_func("*.hcl")):
        ws.load(load(hcl_file, context=context))

    return ws


def load(
    file: Path,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and parse a single HCL file, rendering Jinja2 templates with context."""
    text = file.read_text()
    ctx = context if context is not None else {}
    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    try:
        template = env.from_string(text)
        text = template.render(ctx)
    except jinja2.TemplateError as exc:
        raise ValueError(f"{file}: {exc}") from exc
    return hcl2.loads(text)  # type: ignore[reportPrivateImportUsage]
