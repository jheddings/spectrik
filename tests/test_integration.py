"""End-to-end integration test for spectrik."""

from __future__ import annotations

from pathlib import Path

from spectrik import Blueprint, Context, Ensure, Project, Specification
from spectrik.hcl import load_blueprints, load_projects
from spectrik.specs import _spec_registry


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


def _write_hcl(tmp_path: Path, subdir: str, filename: str, content: str) -> Path:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    f = d / filename
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
        """Load HCL, build project, verify specs executed."""
        _write_hcl(tmp_path, "blueprints", "base.hcl", '''
            blueprint "base" {
                ensure "counter" { id = "1" }
                ensure "counter" { id = "2" }
            }
        ''')
        _write_hcl(tmp_path, "projects", "app.hcl", '''
            project "myapp" {
                description = "Test app"
                repo = "owner/myapp"
                use = ["base"]
                ensure "counter" { id = "3" }
            }
        ''')

        blueprints = load_blueprints(tmp_path)
        projects = load_projects(tmp_path, blueprints, project_type=AppProject)

        proj = projects["myapp"]
        assert proj.repo == "owner/myapp"

        proj.build()
        assert CountingSpec.apply_count == 3

    def test_full_pipeline_dry_run(self, tmp_path):
        """Dry run should not apply any specs."""
        _write_hcl(tmp_path, "blueprints", "base.hcl", '''
            blueprint "base" {
                ensure "counter" { id = "1" }
            }
        ''')
        _write_hcl(tmp_path, "projects", "app.hcl", '''
            project "myapp" {
                use = ["base"]
            }
        ''')

        blueprints = load_blueprints(tmp_path)
        projects = load_projects(tmp_path, blueprints, project_type=AppProject)

        projects["myapp"].build(dry_run=True)
        assert CountingSpec.apply_count == 0

    def test_programmatic_api(self):
        """Test building specs/blueprints/projects without HCL."""
        s = CountingSpec(id="manual")
        bp = Blueprint(name="manual-bp", ops=[Ensure(s)])
        proj = AppProject(name="manual-proj", repo="test/repo", blueprints=[bp])
        proj.build()
        assert CountingSpec.apply_count == 1
