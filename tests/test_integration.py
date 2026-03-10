"""End-to-end integration test for spectrik."""

from __future__ import annotations

from pathlib import Path

import spectrik.hcl as hcl
from spectrik import Blueprint, Context, Ensure, Project, Specification
from spectrik.projects import _project_registry, project
from spectrik.spec import _spec_registry


@project("app")
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
        self._saved_specs = _spec_registry.copy()
        _spec_registry.clear()
        _spec_registry["counter"] = CountingSpec
        self._saved_projects = _project_registry.copy()

    def teardown_method(self):
        _spec_registry.clear()
        _spec_registry.update(self._saved_specs)
        _project_registry.clear()
        _project_registry.update(self._saved_projects)

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
            app "myapp" {
                description = "Test app"
                repo = "owner/myapp"
                use = ["base"]
                ensure "counter" { id = "3" }
            }
        """,
        )

        ws = hcl.scan(tmp_path)

        proj = ws["myapp"]
        assert isinstance(proj, AppProject)
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
            app "myapp" {
                use = ["base"]
            }
        """,
        )

        ws = hcl.scan(tmp_path)

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
            app "myapp" {
                use = ["base"]
                repo = "owner/myapp"
            }
        """,
        )

        ws = hcl.scan(tmp_path)
        proj = ws["myapp"]
        assert isinstance(proj, AppProject)
        assert proj.repo == "owner/myapp"

        proj.build()
        assert CountingSpec.apply_count == 1

    def test_full_pipeline_with_interpolation_context(self, tmp_path):
        """Interpolation context flows through scan -> workspace -> load -> parse -> build."""
        _write_hcl(
            tmp_path,
            "config.hcl",
            """
            blueprint "base" {
                ensure "counter" { id = "${prefix}-1" }
            }
            app "web" {
                description = "${env} app"
                use = ["base"]
            }
        """,
        )

        ws = hcl.scan(
            tmp_path,
            context={"prefix": "prod", "env": "production"},
        )
        assert len(ws) == 1
        assert "web" in ws
        assert ws["web"].description == "production app"

        ws["web"].build()
        assert CountingSpec.apply_count == 1

    def test_mixed_project_types(self, tmp_path):
        """Multiple project types coexist in one workspace."""

        @project("other")
        class OtherProject(Project):
            endpoint: str = ""

        _write_hcl(
            tmp_path,
            "apps.hcl",
            """
            app "web" {
                repo = "owner/web"
                ensure "counter" { id = "1" }
            }
            """,
        )
        _write_hcl(
            tmp_path,
            "services.hcl",
            """
            other "api" {
                endpoint = "https://api.example.com"
                ensure "counter" { id = "2" }
            }
            """,
        )

        ws = hcl.scan(tmp_path)
        assert len(ws) == 2

        web = ws["web"]
        assert isinstance(web, AppProject)
        assert web.repo == "owner/web"

        api = ws["api"]
        assert isinstance(api, OtherProject)
        assert api.endpoint == "https://api.example.com"

        # select by type
        apps = ws.select(project_type=AppProject)
        assert len(apps) == 1
        assert apps[0].name == "web"

        # build all — resolve first, then reset counters and build
        all_projects = list(ws.values())
        CountingSpec.apply_count = 0
        CountingSpec.remove_count = 0
        for proj in all_projects:
            proj.build()
        assert CountingSpec.apply_count == 2

    def test_programmatic_api(self):
        """Test building specs/blueprints/projects without HCL."""
        s = CountingSpec(id="manual")
        bp = Blueprint(name="manual-bp", ops=[Ensure(s)])
        proj = AppProject(name="manual-proj", repo="test/repo", blueprints=[bp])
        proj.build()
        assert CountingSpec.apply_count == 1
