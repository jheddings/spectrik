"""Project base model — the top-level build target."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from .blueprints import Blueprint
from .context import Context

logger = logging.getLogger(__name__)


class Project(BaseModel):
    """Base model that apps subclass with domain-specific fields."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str = ""
    blueprints: list[Blueprint] = Field(default_factory=list)

    def build(self, *, ctx: Context | None = None, **kwargs) -> None:
        """Build all blueprints.

        If *ctx* is provided it is used directly; otherwise a new
        :class:`Context` is created from *kwargs*.
        """
        if ctx is None:
            ctx = Context(target=self, **kwargs)
        logger.info("Building project '%s'", self.name)
        for blueprint in self.blueprints:
            blueprint.build(ctx)
