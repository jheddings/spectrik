"""Runtime execution context for the build pipeline."""

from __future__ import annotations

from .event import Event


class Context[P]:
    """Runtime state passed through the build chain."""

    def __init__(
        self, target: P, *, dry_run: bool = False, continue_on_error: bool = False
    ) -> None:
        self.target = target
        self.dry_run = dry_run
        self.continue_on_error = continue_on_error

        self.on_spec_start = Event()
        self.on_spec_finish = Event()
        self.on_spec_applied = Event()
        self.on_spec_removed = Event()
        self.on_spec_skipped = Event()
        self.on_spec_failed = Event()
