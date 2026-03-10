"""Project base model — the top-level build target."""

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import BaseModel, Field

from .blueprints import Blueprint
from .context import Context

logger = logging.getLogger(__name__)

_project_registry: dict[str, type[Project]] = {}


def project(name: str):
    """Register a Project subclass as an HCL block type."""

    def decorator[T: Project](cls: type[T]) -> type[T]:
        if name in _project_registry:
            raise ValueError(
                f"Duplicate project type: '{name}' is already registered "
                f"to {_project_registry[name].__name__}"
            )
        _project_registry[name] = cls
        return cls

    return decorator


def pre_build(method: Callable) -> Callable:
    """Mark a Project method to run before blueprint execution."""
    method._spectrik_hook = "pre_build"  # type: ignore[attr-defined]
    return method


def post_build(method: Callable) -> Callable:
    """Mark a Project method to run after blueprint execution."""
    method._spectrik_hook = "post_build"  # type: ignore[attr-defined]
    return method


def _collect_hooks(instance: Project, hook_name: str) -> list[Callable]:
    """Collect lifecycle hooks from instance's class hierarchy in MRO order."""
    seen: set[int] = set()
    hooks: list[Callable] = []
    for cls in reversed(type(instance).__mro__):
        for attr in vars(cls).values():
            if (
                callable(attr)
                and getattr(attr, "_spectrik_hook", None) == hook_name
                and id(attr) not in seen
            ):
                seen.add(id(attr))
                hooks.append(attr.__get__(instance))
    return hooks


class Project(BaseModel):
    """Base model that apps subclass with domain-specific fields."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str = ""
    blueprints: list[Blueprint] = Field(default_factory=list)

    def build(self, *, ctx: Context | None = None, **kwargs) -> bool:
        """Build all blueprints.

        If *ctx* is provided it is used directly; otherwise a new
        :class:`Context` is created from *kwargs*.
        """
        if ctx is None:
            ctx = Context(target=self, **kwargs)
        logger.info("Building project '%s'", self.name)

        try:
            for hook in _collect_hooks(self, "pre_build"):
                hook(ctx)

            results = [blueprint.build(ctx) for blueprint in self.blueprints]
            return all(results)
        finally:
            for hook in _collect_hooks(self, "post_build"):
                hook(ctx)


# Register base Project as the "project" block type
project("project")(Project)
