"""Project base model — the top-level build target."""

from __future__ import annotations

import logging

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
        results = [blueprint.build(ctx) for blueprint in self.blueprints]
        return all(results)


# Register base Project as the "project" block type
project("project")(Project)
