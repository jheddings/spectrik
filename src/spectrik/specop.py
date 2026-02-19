"""SpecOp strategies."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .context import Context
from .spec import Specification

logger = logging.getLogger(__name__)


class SpecOp[P](ABC):
    """Wraps a Specification with conditional execution logic."""

    def __init__(self, spec: Specification[P]) -> None:
        self.spec = spec

    @abstractmethod
    def __call__(self, ctx: Context[P]) -> None: ...


class Present[P](SpecOp[P]):
    """Apply only if resource doesn't exist."""

    def __call__(self, ctx: Context[P]) -> None:
        spec_name = type(self.spec).__name__
        if self.spec.exists(ctx):
            logger.debug("Skipping %s; already exists", spec_name)
        elif ctx.dry_run:
            logger.info("[DRY RUN] Would apply %s", spec_name)
        else:
            logger.info("Applying %s", spec_name)
            self.spec.apply(ctx)


class Ensure[P](SpecOp[P]):
    """Apply if current state doesn't match."""

    def __call__(self, ctx: Context[P]) -> None:
        spec_name = type(self.spec).__name__
        if self.spec.equals(ctx):
            logger.debug("Skipping %s; up to date", spec_name)
        elif ctx.dry_run:
            logger.info("[DRY RUN] Would apply %s", spec_name)
        else:
            logger.info("Applying %s", spec_name)
            self.spec.apply(ctx)


class Absent[P](SpecOp[P]):
    """Remove if resource exists."""

    def __call__(self, ctx: Context[P]) -> None:
        spec_name = type(self.spec).__name__
        if self.spec.exists(ctx):
            if ctx.dry_run:
                logger.info("[DRY RUN] Would remove %s", spec_name)
            else:
                logger.info("Removing %s", spec_name)
                self.spec.remove(ctx)
        else:
            logger.debug("Skipping removal of %s; not present", spec_name)
