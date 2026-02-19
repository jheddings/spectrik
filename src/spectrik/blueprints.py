"""Blueprint model — a named collection of spec operations."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field

from .context import Context
from .specop import SpecOp

logger = logging.getLogger(__name__)


class Blueprint(BaseModel):
    """A named collection of spec operations."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    ops: list[SpecOp[Any]] = Field(default_factory=list)

    def __iter__(self) -> Iterator[SpecOp[Any]]:
        return iter(self.ops)

    def build(self, ctx: Context) -> None:
        """Execute all operations in this blueprint."""
        logger.debug("Building blueprint '%s'", self.name)
        for op in self.ops:
            op(ctx)
