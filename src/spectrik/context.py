"""Runtime execution context for the build pipeline."""

from __future__ import annotations


class Context[P]:
    """Runtime state passed through the build chain."""

    def __init__(self, target: P, *, dry_run: bool = False) -> None:
        self.target = target
        self.dry_run = dry_run
