"""Resolver — walk parsed dicts and resolve ${...} variable interpolation."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_INTERP_PATTERN = re.compile(r"\$\$\{|(\$\{([^{}]+)\})")


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

    def _resolve_value(self, value: str) -> str | Any:
        """Resolve ${...} interpolations in a single string value.

        If the entire string is a single ${ref}, returns the resolved object
        directly (preserving type). If ${ref} is embedded in a larger string,
        the resolved value is stringified. Use $${...} for literal ${...}.
        """
        # Fast path: no interpolation
        if "${" not in value:
            return value

        # Check if the entire string is a single interpolation
        match = re.fullmatch(r"\$\{([^{}]+)\}", value)
        if match:
            return self._resolve_ref(match.group(1).strip())

        # Mixed string: replace each interpolation with its stringified value
        def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
            if m.group(0) == "$${":
                return "${"
            ref = m.group(2).strip()
            return str(self._resolve_ref(ref))

        return _INTERP_PATTERN.sub(_replace, value)

    def resolve(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively walk a parsed dict and resolve all ${...} interpolations."""
        return self._walk(data)

    def _walk(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._walk(item) for item in obj]
        if isinstance(obj, str):
            return self._resolve_value(obj)
        return obj
