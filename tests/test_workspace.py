"""Tests for spectrik.workspace."""

from __future__ import annotations

import pytest

from spectrik.projects import Project
from spectrik.workspace import Workspace


class TestWorkspace:
    def test_getitem(self):
        ws = Workspace({"a": Project(name="a"), "b": Project(name="b")})
        assert ws["a"].name == "a"

    def test_getitem_missing_raises(self):
        ws = Workspace({})
        with pytest.raises(KeyError):
            ws["missing"]

    def test_contains(self):
        ws = Workspace({"a": Project(name="a")})
        assert "a" in ws
        assert "b" not in ws

    def test_iter_yields_keys(self):
        ws = Workspace({"a": Project(name="a"), "b": Project(name="b")})
        assert list(ws) == ["a", "b"]

    def test_len(self):
        ws = Workspace({"a": Project(name="a"), "b": Project(name="b")})
        assert len(ws) == 2

    def test_len_empty(self):
        ws = Workspace({})
        assert len(ws) == 0

    def test_get_existing(self):
        ws = Workspace({"a": Project(name="a")})
        result = ws.get("a")
        assert result is not None
        assert result.name == "a"

    def test_get_missing_returns_none(self):
        ws = Workspace({})
        assert ws.get("missing") is None

    def test_get_missing_returns_default(self):
        fallback = Project(name="fallback")
        ws = Workspace({})
        assert ws.get("missing", fallback) is fallback

    def test_filter(self):
        ws = Workspace(
            {
                "a": Project(name="a"),
                "b": Project(name="b"),
                "c": Project(name="c"),
            }
        )
        result = ws.filter(["a", "c"])
        assert len(result) == 2
        assert result[0].name == "a"
        assert result[1].name == "c"

    def test_filter_skips_missing(self):
        ws = Workspace({"a": Project(name="a")})
        result = ws.filter(["a", "missing"])
        assert len(result) == 1

    def test_filter_empty_names(self):
        ws = Workspace({"a": Project(name="a")})
        result = ws.filter([])
        assert result == []

    def test_values(self):
        ws = Workspace({"a": Project(name="a"), "b": Project(name="b")})
        names = [p.name for p in ws.values()]
        assert names == ["a", "b"]

    def test_items(self):
        ws = Workspace({"a": Project(name="a")})
        pairs = list(ws.items())
        assert pairs[0] == ("a", ws["a"])

    def test_keys(self):
        ws = Workspace({"a": Project(name="a"), "b": Project(name="b")})
        assert list(ws.keys()) == ["a", "b"]
