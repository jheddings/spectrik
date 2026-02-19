"""Specification ABC, SpecOp strategies, and spec registration."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .context import Context

_spec_registry: dict[str, type] = {}


def spec(name: str):
    """Register a Specification class as an HCL block decoder."""

    def decorator(cls):
        _spec_registry[name] = cls
        return cls

    return decorator


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
