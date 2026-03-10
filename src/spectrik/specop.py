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
        try:
            ctx.on_spec_start(ctx, self)
            if self.spec.exists(ctx):
                logger.debug("Skipping %s; already exists", spec_name)
                ctx.on_spec_skipped(ctx, self, "already exists")
            elif ctx.dry_run:
                logger.info("[DRY RUN] Would apply %s", spec_name)
                ctx.on_spec_skipped(ctx, self, "dry run; would apply")
            else:
                logger.info("Applying %s", spec_name)
                self.spec.apply(ctx)
                ctx.on_spec_applied(ctx, self)
        except Exception as exc:
            ctx.on_spec_failed(ctx, self, exc)
            raise
        finally:
            ctx.on_spec_finish(ctx, self)


class Ensure[P](SpecOp[P]):
    """Apply if current state doesn't match."""

    def __call__(self, ctx: Context[P]) -> None:
        spec_name = type(self.spec).__name__
        try:
            ctx.on_spec_start(ctx, self)
            if self.spec.equals(ctx):
                logger.debug("Skipping %s; up to date", spec_name)
                ctx.on_spec_skipped(ctx, self, "up to date")
            elif ctx.dry_run:
                logger.info("[DRY RUN] Would apply %s", spec_name)
                ctx.on_spec_skipped(ctx, self, "dry run; would apply")
            else:
                logger.info("Applying %s", spec_name)
                self.spec.apply(ctx)
                ctx.on_spec_applied(ctx, self)
        except Exception as exc:
            ctx.on_spec_failed(ctx, self, exc)
            raise
        finally:
            ctx.on_spec_finish(ctx, self)


class Absent[P](SpecOp[P]):
    """Remove if resource exists."""

    def __call__(self, ctx: Context[P]) -> None:
        spec_name = type(self.spec).__name__
        try:
            ctx.on_spec_start(ctx, self)
            if self.spec.exists(ctx):
                if ctx.dry_run:
                    logger.info("[DRY RUN] Would remove %s", spec_name)
                    ctx.on_spec_skipped(ctx, self, "dry run; would remove")
                else:
                    logger.info("Removing %s", spec_name)
                    self.spec.remove(ctx)
                    ctx.on_spec_removed(ctx, self)
            else:
                logger.debug("Skipping removal of %s; not present", spec_name)
                ctx.on_spec_skipped(ctx, self, "not present")
        except Exception as exc:
            ctx.on_spec_failed(ctx, self, exc)
            raise
        finally:
            ctx.on_spec_finish(ctx, self)
