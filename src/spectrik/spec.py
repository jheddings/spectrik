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

    def equals(self, ctx: Context[P]) -> bool:
        """Current state matches desired state.

        Override in subclasses that can check equality.  The default
        returns ``NotImplemented``, signaling that equality cannot be
        determined (e.g. for sensitive values like secrets).
        """
        return NotImplemented  # type: ignore[return-value]

    def exists(self, ctx: Context[P]) -> bool:
        """Resource exists (defaults to equals).

        When ``equals()`` returns ``NotImplemented``, this falls back
        to ``False`` (existence unknown → assume absent).
        """
        result = self.equals(ctx)
        if result is NotImplemented:
            return False
        return result

    @abstractmethod
    def apply(self, ctx: Context[P]) -> None:
        """Create or update resource."""

    def remove(self, ctx: Context[P]) -> None:
        """Delete resource.

        Override in subclasses that support removal.  The default raises
        ``NotImplementedError`` for specs representing irreversible resources.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support removal")
