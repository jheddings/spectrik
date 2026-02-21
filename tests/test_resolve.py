"""Tests for spectrik.resolve — variable interpolation on parsed dicts."""

import pytest

from spectrik.resolve import Resolver


class TestResolveRef:
    """Test _resolve_ref: dotted reference resolution against context."""

    def test_bare_reference(self):
        r = Resolver({"name": "myapp"})
        assert r._resolve_ref("name") == "myapp"

    def test_dotted_reference_dict(self):
        r = Resolver({"env": {"HOME": "/home/user"}})
        assert r._resolve_ref("env.HOME") == "/home/user"

    def test_dotted_reference_getattr(self):
        class Config:
            region = "us-east-1"

        r = Resolver({"config": Config()})
        assert r._resolve_ref("config.region") == "us-east-1"

    def test_deeply_nested(self):
        r = Resolver({"a": {"b": {"c": "deep"}}})
        assert r._resolve_ref("a.b.c") == "deep"

    def test_undefined_raises(self):
        r = Resolver({"name": "myapp"})
        with pytest.raises(ValueError, match="missing"):
            r._resolve_ref("missing")

    def test_undefined_nested_raises(self):
        r = Resolver({"env": {"HOME": "/home"}})
        with pytest.raises(ValueError, match="MISSING"):
            r._resolve_ref("env.MISSING")

    def test_callable_value(self):
        r = Resolver({"cwd": lambda: "/tmp/work"})
        assert r._resolve_ref("cwd") == "/tmp/work"

    def test_callable_not_invoked_on_intermediate(self):
        """Callables at intermediate positions are not invoked during traversal."""
        r = Resolver({"get_value": lambda: "result"})
        with pytest.raises(ValueError, match="get_value.attr"):
            r._resolve_ref("get_value.attr")
