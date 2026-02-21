"""Resolver — walk parsed dicts and resolve ${...} variable interpolation."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Resolver:
    """Resolve ${...} interpolation references against a context dict."""

    def __init__(self, context: dict[str, Any] | None = None) -> None:
        self._context = context or {}

    def _resolve_ref(self, ref: str) -> Any:
        """Resolve a dotted reference (e.g., 'env.HOME') against the context."""
        parts = ref.split(".")
        current: Any = self._context

        for part in parts:
            try:
                current = current[part]
            except (KeyError, TypeError):
                try:
                    current = getattr(current, part)
                except AttributeError:
                    raise ValueError(f"undefined variable '{ref}'") from None

        if callable(current) and not isinstance(current, type):
            current = current()

        return current
