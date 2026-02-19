"""Tests for spectrik.workspace."""

from __future__ import annotations

import pytest

from spectrik.projects import Project
from spectrik.workspace import Workspace


class TestWorkspaceConstruction:
    def test_default_project_type(self):
        ws = Workspace()
        assert ws._project_type is Project

    def test_custom_project_type(self):
        class Custom(Project):
            extra: str = ""

        ws = Workspace(project_type=Custom)
        assert ws._project_type is Custom

    def test_empty_workspace_len(self):
        ws = Workspace()
        assert len(ws) == 0

    def test_empty_workspace_iter(self):
        ws = Workspace()
        assert list(ws) == []

    def test_empty_workspace_contains(self):
        ws = Workspace()
        assert "anything" not in ws

    def test_getitem_empty_raises(self):
        ws = Workspace()
        with pytest.raises(KeyError):
            ws["missing"]

    def test_get_empty_returns_none(self):
        ws = Workspace()
        assert ws.get("missing") is None

    def test_repr_empty(self):
        ws = Workspace()
        assert "Workspace" in repr(ws)
        assert "blueprints=0" in repr(ws)
        assert "projects=0" in repr(ws)

    def test_repr_with_custom_type(self):
        class Custom(Project):
            extra: str = ""

        ws = Workspace(project_type=Custom)
        assert "Custom" in repr(ws)
