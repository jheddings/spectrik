"""Tests for OperationRef."""

from __future__ import annotations

import pytest

from spectrik.context import Context
from spectrik.projects import Project
from spectrik.spec import Specification, _spec_registry
from spectrik.specop import Absent, Ensure, Present
from spectrik.workspace import OperationRef, Workspace


class TrackingSpec(Specification["Project"]):
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def equals(self, ctx: Context[Project]) -> bool:
        return False

    def apply(self, ctx: Context[Project]) -> None:
        pass

    def remove(self, ctx: Context[Project]) -> None:
        pass


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = _spec_registry.copy()
    _spec_registry.clear()
    _spec_registry["widget"] = TrackingSpec
    yield
    _spec_registry.clear()
    _spec_registry.update(saved)


class TestOperationRef:
    def test_resolve_ensure(self):
        ref = OperationRef(name="widget", strategy="ensure", attrs={"color": "red"})
        ws = Workspace()
        result = ref.resolve(ws)
        assert isinstance(result, Ensure)
        assert isinstance(result.spec, TrackingSpec)
        assert result.spec.kwargs == {"color": "red"}

    def test_resolve_present(self):
        ref = OperationRef(name="widget", strategy="present", attrs={"size": "large"})
        ws = Workspace()
        result = ref.resolve(ws)
        assert isinstance(result, Present)
        assert isinstance(result.spec, TrackingSpec)
        assert result.spec.kwargs == {"size": "large"}

    def test_resolve_absent(self):
        ref = OperationRef(name="widget", strategy="absent", attrs={"id": "42"})
        ws = Workspace()
        result = ref.resolve(ws)
        assert isinstance(result, Absent)
        assert isinstance(result.spec, TrackingSpec)
        assert result.spec.kwargs == {"id": "42"}

    def test_resolve_unknown_spec_raises(self):
        ref = OperationRef(name="nonexistent", strategy="ensure", attrs={})
        ws = Workspace()
        with pytest.raises(ValueError, match="Unknown spec type"):
            ref.resolve(ws)

    def test_label_defaults_none(self):
        ref = OperationRef(name="widget", strategy="ensure", attrs={})
        assert ref.label is None

    def test_label_set(self):
        ref = OperationRef(name="widget", strategy="ensure", attrs={}, label="my-label")
        assert ref.label == "my-label"
