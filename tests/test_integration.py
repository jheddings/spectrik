"""End-to-end integration test for spectrik."""

from __future__ import annotations

from pathlib import Path

import spectrik.hcl as hcl
from spectrik import Blueprint, Context, Ensure, Project, Specification
from spectrik.spec import _spec_registry


class AppProject(Project):
    repo: str = ""


class CountingSpec(Specification["AppProject"]):
    apply_count = 0
    remove_count = 0

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        CountingSpec.apply_count = 0
        CountingSpec.remove_count = 0

    def equals(self, ctx: Context[AppProject]) -> bool:
        return False

    def apply(self, ctx: Context[AppProject]) -> None:
        CountingSpec.apply_count += 1

    def remove(self, ctx: Context[AppProject]) -> None:
        CountingSpec.remove_count += 1


def _write_hcl(tmp_path: Path, filename: str, content: str) -> Path:
    f = tmp_path / filename
    f.write_text(content)
    return f


class TestEndToEnd:
    def setup_method(self):
        self._saved = _spec_registry.copy()
        _spec_registry.clear()
        _spec_registry["counter"] = CountingSpec

    def teardown_method(self):
        _spec_registry.clear()
        _spec_registry.update(self._saved)

    def test_full_pipeline(self, tmp_path):
        """Load HCL via Workspace, build project, verify specs executed."""
        _write_hcl(
            tmp_path,
            "blueprints.hcl",
            """
            blueprint "base" {
                ensure "counter" { id = "1" }
                ensure "counter" { id = "2" }
            }
        """,
        )
        _write_hcl(
            tmp_path,
            "projects.hcl",
            """
            project "myapp" {
                description = "Test app"
                repo = "owner/myapp"
                use = ["base"]
                ensure "counter" { id = "3" }
            }
        """,
        )

        ws = hcl.scan(tmp_path, project_type=AppProject)

        proj = ws["myapp"]
        assert proj.repo == "owner/myapp"

        proj.build()
        assert CountingSpec.apply_count == 3

    def test_full_pipeline_dry_run(self, tmp_path):
        """Dry run should not apply any specs."""
        _write_hcl(
            tmp_path,
            "config.hcl",
            """
            blueprint "base" {
                ensure "counter" { id = "1" }
            }
            project "myapp" {
                use = ["base"]
            }
        """,
        )

        ws = hcl.scan(tmp_path, project_type=AppProject)

        ws["myapp"].build(dry_run=True)
        assert CountingSpec.apply_count == 0

    def test_hcl_scan_convenience(self, tmp_path):
        """Test hcl.scan() convenience function."""
        _write_hcl(
            tmp_path,
            "config.hcl",
            """
            blueprint "base" {
                ensure "counter" { id = "1" }
            }
            project "myapp" {
                use = ["base"]
                repo = "owner/myapp"
            }
        """,
        )

        ws = hcl.scan(tmp_path, project_type=AppProject)
        proj = ws["myapp"]
        assert isinstance(proj, AppProject)
        assert proj.repo == "owner/myapp"

        proj.build()
        assert CountingSpec.apply_count == 1

    def test_full_pipeline_with_jinja2_context(self, tmp_path):
        """Jinja2 context flows through scan -> workspace -> load -> parse -> build."""
        _write_hcl(
            tmp_path,
            "config.hcl",
            """
            blueprint "base" {
                ensure "counter" { id = "{{ prefix }}-1" }
            }
            {% for name in apps %}
            project "{{ name }}" {
                description = "Generated app"
                use = ["base"]
            }
            {% endfor %}
        """,
        )

        ws = hcl.scan(
            tmp_path,
            project_type=AppProject,
            context={"prefix": "prod", "apps": ["web", "api"]},
        )
        assert len(ws) == 2
        assert "web" in ws
        assert "api" in ws

        ws["web"].build()
        assert CountingSpec.apply_count == 1

    def test_programmatic_api(self):
        """Test building specs/blueprints/projects without HCL."""
        s = CountingSpec(id="manual")
        bp = Blueprint(name="manual-bp", ops=[Ensure(s)])
        proj = AppProject(name="manual-proj", repo="test/repo", blueprints=[bp])
        proj.build()
        assert CountingSpec.apply_count == 1
