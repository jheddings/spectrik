"""Specification ABC, SpecOp strategies, and spec registration."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from spectrik.context import Context

logger = logging.getLogger(__name__)

# -- Spec Registry --

_spec_registry: dict[str, type] = {}


def spec(name: str):
    """Register a Specification class as an HCL block decoder."""

    def decorator(cls):
        _spec_registry[name] = cls
        return cls

    return decorator


# -- Specification ABC --


class Specification[P](ABC):
    """Base class for all configuration specs."""

    @abstractmethod
    def equals(self, ctx: Context[P]) -> bool:
        """Current state matches desired state."""

    def exists(self, ctx: Context[P]) -> bool:
        """Resource exists (defaults to equals)."""
        return self.equals(ctx)

    @abstractmethod
    def apply(self, ctx: Context[P]) -> None:
        """Create or update resource."""

    @abstractmethod
    def remove(self, ctx: Context[P]) -> None:
        """Delete resource."""


# -- SpecOp Strategies --


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
