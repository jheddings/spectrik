"""Tests for spectrik.hcl."""

from __future__ import annotations

from pathlib import Path

import pytest

from spectrik.context import Context
from spectrik.hcl import load, load_blueprints, load_projects, scan
from spectrik.projects import Project
from spectrik.specs import Specification, _spec_registry

# -- Test fixtures --


class SampleProject(Project):
    repo: str = ""
    homepage: str = ""


class TrackingSpec(Specification["SampleProject"]):
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.applied = False

    def equals(self, ctx: Context[SampleProject]) -> bool:
        return False

    def apply(self, ctx: Context[SampleProject]) -> None:
        self.applied = True

    def remove(self, ctx: Context[SampleProject]) -> None:
        pass


def _write_hcl(tmp_path: Path, subdir: str, filename: str, content: str) -> Path:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    f = d / filename
    f.write_text(content)
    return f


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear spec registry before and after each test."""
    saved = _spec_registry.copy()
    _spec_registry.clear()

    # Register our test spec
    _spec_registry["widget"] = TrackingSpec

    yield

    _spec_registry.clear()
    _spec_registry.update(saved)


# -- Low-level API tests --


class TestLoad:
    def test_load_single_file(self, tmp_path):
        _write_hcl(tmp_path, ".", "test.hcl", '''
            blueprint "my-bp" {
                ensure "widget" {
                    color = "red"
                }
            }
        ''')
        result = load(tmp_path / "test.hcl")
        assert "blueprint" in result

    def test_load_with_resolve_attrs(self, tmp_path):
        _write_hcl(tmp_path, ".", "test.hcl", '''
            blueprint "my-bp" {
                ensure "widget" {
                    color = "original"
                }
            }
        ''')

        def resolver(attrs):
            return {k: v.upper() if isinstance(v, str) else v for k, v in attrs.items()}

        result = load(tmp_path / "test.hcl", resolve_attrs=resolver)
        assert result is not None


class TestScan:
    def test_scan_directory(self, tmp_path):
        _write_hcl(tmp_path, "bps", "a.hcl", '''
            blueprint "alpha" {}
        ''')
        _write_hcl(tmp_path, "bps", "b.hcl", '''
            blueprint "beta" {}
        ''')
        results = scan(tmp_path / "bps")
        assert len(results) == 2

    def test_scan_sorted_order(self, tmp_path):
        _write_hcl(tmp_path, "bps", "z.hcl", '''
            blueprint "zulu" {}
        ''')
        _write_hcl(tmp_path, "bps", "a.hcl", '''
            blueprint "alpha" {}
        ''')
        results = scan(tmp_path / "bps")
        assert len(results) == 2

    def test_scan_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        results = scan(d)
        assert results == []

    def test_scan_missing_dir(self, tmp_path):
        results = scan(tmp_path / "nonexistent")
        assert results == []


# -- Blueprint loading tests --


class TestLoadBlueprints:
    def test_simple_blueprint(self, tmp_path):
        _write_hcl(tmp_path, "blueprints", "test.hcl", '''
            blueprint "simple" {
                ensure "widget" {
                    color = "blue"
                }
            }
        ''')
        bps = load_blueprints(tmp_path)
        assert "simple" in bps
        assert len(bps["simple"].ops) == 1

    def test_multiple_strategies(self, tmp_path):
        _write_hcl(tmp_path, "blueprints", "test.hcl", '''
            blueprint "multi" {
                present "widget" { color = "red" }
                ensure "widget" { color = "green" }
                absent "widget" { color = "blue" }
            }
        ''')
        bps = load_blueprints(tmp_path)
        assert len(bps["multi"].ops) == 3

    def test_blueprint_include(self, tmp_path):
        _write_hcl(tmp_path, "blueprints", "a_base.hcl", '''
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        ''')
        _write_hcl(tmp_path, "blueprints", "b_derived.hcl", '''
            blueprint "derived" {
                include = ["base"]
                ensure "widget" { color = "blue" }
            }
        ''')
        bps = load_blueprints(tmp_path)
        assert "derived" in bps
        # included ops come first, then own ops
        assert len(bps["derived"].ops) == 2

    def test_unknown_spec_raises(self, tmp_path):
        _write_hcl(tmp_path, "blueprints", "test.hcl", '''
            blueprint "bad" {
                ensure "nonexistent_spec" {
                    foo = "bar"
                }
            }
        ''')
        with pytest.raises(ValueError, match="nonexistent_spec"):
            load_blueprints(tmp_path)

    def test_resolve_attrs_callback(self, tmp_path):
        _write_hcl(tmp_path, "blueprints", "test.hcl", '''
            blueprint "resolved" {
                ensure "widget" {
                    color = "REPLACE_ME"
                }
            }
        ''')

        def resolver(attrs):
            return {k: "replaced" if v == "REPLACE_ME" else v for k, v in attrs.items()}

        bps = load_blueprints(tmp_path, resolve_attrs=resolver)
        assert "resolved" in bps
        # Verify the spec got the resolved value
        op = bps["resolved"].ops[0]
        assert op.spec.kwargs.get("color") == "replaced"

    def test_empty_blueprint(self, tmp_path):
        _write_hcl(tmp_path, "blueprints", "test.hcl", '''
            blueprint "empty" {}
        ''')
        bps = load_blueprints(tmp_path)
        assert "empty" in bps
        assert len(bps["empty"].ops) == 0


# -- Project loading tests --


class TestLoadProjects:
    def test_simple_project(self, tmp_path):
        _write_hcl(tmp_path, "projects", "test.hcl", '''
            project "myproj" {
                description = "A test project"
            }
        ''')
        projs = load_projects(tmp_path, blueprints={})
        assert "myproj" in projs
        assert projs["myproj"].description == "A test project"

    def test_project_use_blueprints(self, tmp_path):
        _write_hcl(tmp_path, "blueprints", "test.hcl", '''
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        ''')
        _write_hcl(tmp_path, "projects", "test.hcl", '''
            project "myproj" {
                use = ["base"]
            }
        ''')
        bps = load_blueprints(tmp_path)
        projs = load_projects(tmp_path, bps)
        assert len(projs["myproj"].blueprints) == 1
        assert projs["myproj"].blueprints[0].name == "base"

    def test_project_inline_specs(self, tmp_path):
        _write_hcl(tmp_path, "projects", "test.hcl", '''
            project "myproj" {
                ensure "widget" { color = "red" }
            }
        ''')
        projs = load_projects(tmp_path, blueprints={})
        assert len(projs["myproj"].blueprints) == 1

    def test_project_custom_type(self, tmp_path):
        _write_hcl(tmp_path, "projects", "test.hcl", '''
            project "myproj" {
                description = "test"
                repo = "owner/repo"
                homepage = "https://example.com"
            }
        ''')
        projs = load_projects(tmp_path, blueprints={}, project_type=SampleProject)
        proj = projs["myproj"]
        assert isinstance(proj, SampleProject)
        assert proj.repo == "owner/repo"
        assert proj.homepage == "https://example.com"

    def test_project_use_and_inline_combined(self, tmp_path):
        _write_hcl(tmp_path, "blueprints", "test.hcl", '''
            blueprint "base" {
                ensure "widget" { color = "red" }
            }
        ''')
        _write_hcl(tmp_path, "projects", "test.hcl", '''
            project "myproj" {
                use = ["base"]
                ensure "widget" { color = "blue" }
            }
        ''')
        bps = load_blueprints(tmp_path)
        projs = load_projects(tmp_path, bps)
        # use blueprints first, then inline
        assert len(projs["myproj"].blueprints) == 2

    def test_unknown_blueprint_in_use_raises(self, tmp_path):
        _write_hcl(tmp_path, "projects", "test.hcl", '''
            project "myproj" {
                use = ["nonexistent"]
            }
        ''')
        with pytest.raises(ValueError, match="nonexistent"):
            load_projects(tmp_path, blueprints={})
