"""Tests for spectrik.specs."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from spectrik.context import Context
from spectrik.spec import Specification, spec
from spectrik.specop import Absent, Ensure, Present


class FakeProject(BaseModel):
    name: str = "test"


# -- Concrete spec for testing --


class AlwaysEqual(Specification["FakeProject"]):
    def equals(self, ctx: Context[FakeProject]) -> bool:
        return True

    def apply(self, ctx: Context[FakeProject]) -> None:
        pass

    def remove(self, ctx: Context[FakeProject]) -> None:
        pass


class NeverEqual(Specification["FakeProject"]):
    def equals(self, ctx: Context[FakeProject]) -> bool:
        return False

    def exists(self, ctx: Context[FakeProject]) -> bool:
        return False

    def apply(self, ctx: Context[FakeProject]) -> None:
        self._applied = True

    def remove(self, ctx: Context[FakeProject]) -> None:
        self._removed = True


class SensitiveSpec(Specification["FakeProject"]):
    """A spec that cannot check equality (e.g. secrets)."""

    def apply(self, ctx: Context[FakeProject]) -> None:
        self._applied = True

    def remove(self, ctx: Context[FakeProject]) -> None:
        self._removed = True


class IrreversibleSpec(Specification["FakeProject"]):
    """A spec that does not implement remove()."""

    def equals(self, ctx: Context[FakeProject]) -> bool:
        return False

    def exists(self, ctx: Context[FakeProject]) -> bool:
        return True

    def apply(self, ctx: Context[FakeProject]) -> None:
        self._applied = True


class ExistsButNotEqual(Specification["FakeProject"]):
    """Resource exists but is out of date."""

    def equals(self, ctx: Context[FakeProject]) -> bool:
        return False

    def exists(self, ctx: Context[FakeProject]) -> bool:
        return True

    def apply(self, ctx: Context[FakeProject]) -> None:
        self._applied = True

    def remove(self, ctx: Context[FakeProject]) -> None:
        self._removed = True


def _make_ctx(dry_run: bool = False) -> Context[FakeProject]:
    return Context(target=FakeProject(), dry_run=dry_run)


# -- Specification tests --


class TestSpecification:
    def test_equals_defaults_to_not_implemented(self):
        s = SensitiveSpec()
        ctx = _make_ctx()
        assert s.equals(ctx) is NotImplemented

    def test_exists_defaults_to_equals(self):
        s = AlwaysEqual()
        ctx = _make_ctx()
        assert s.exists(ctx) is True

    def test_exists_falls_back_when_equals_not_implemented(self):
        s = SensitiveSpec()
        ctx = _make_ctx()
        assert s.exists(ctx) is False

    def test_exists_overridable(self):
        s = ExistsButNotEqual()
        ctx = _make_ctx()
        assert s.exists(ctx) is True
        assert s.equals(ctx) is False

    def test_remove_defaults_to_not_implemented(self):
        s = IrreversibleSpec()
        ctx = _make_ctx()
        import pytest

        with pytest.raises(NotImplementedError, match="does not support removal"):
            s.remove(ctx)

    def test_remove_is_not_abstract(self):
        """Specs without remove() can be instantiated."""
        s = IrreversibleSpec()
        assert s is not None


# -- Present tests --


class TestPresent:
    def test_skips_when_exists(self):
        s = AlwaysEqual()
        op = Present(s)
        ctx = _make_ctx()
        op(ctx)  # should not raise

    def test_applies_when_not_exists(self):
        s = NeverEqual()
        op = Present(s)
        ctx = _make_ctx()
        op(ctx)
        assert s._applied is True

    def test_dry_run_skips_apply(self):
        s = NeverEqual()
        op = Present(s)
        ctx = _make_ctx(dry_run=True)
        op(ctx)
        assert not hasattr(s, "_applied")


# -- Ensure tests --


class TestEnsure:
    def test_skips_when_equal(self):
        s = AlwaysEqual()
        op = Ensure(s)
        ctx = _make_ctx()
        op(ctx)  # should not raise

    def test_applies_when_not_equal(self):
        s = ExistsButNotEqual()
        op = Ensure(s)
        ctx = _make_ctx()
        op(ctx)
        assert s._applied is True

    def test_applies_when_equals_not_implemented(self):
        s = SensitiveSpec()
        op = Ensure(s)
        ctx = _make_ctx()
        op(ctx)
        assert s._applied is True

    def test_dry_run_skips_when_equals_not_implemented(self):
        s = SensitiveSpec()
        op = Ensure(s)
        ctx = _make_ctx(dry_run=True)
        op(ctx)
        assert not hasattr(s, "_applied")

    def test_dry_run_skips_apply(self):
        s = ExistsButNotEqual()
        op = Ensure(s)
        ctx = _make_ctx(dry_run=True)
        op(ctx)
        assert not hasattr(s, "_applied")


# -- Absent tests --


class TestAbsent:
    def test_removes_when_exists(self):
        s = ExistsButNotEqual()
        op = Absent(s)
        ctx = _make_ctx()
        op(ctx)
        assert s._removed is True

    def test_skips_when_not_exists(self):
        s = NeverEqual()
        op = Absent(s)
        ctx = _make_ctx()
        op(ctx)
        assert not hasattr(s, "_removed")

    def test_dry_run_skips_remove(self):
        s = ExistsButNotEqual()
        op = Absent(s)
        ctx = _make_ctx(dry_run=True)
        op(ctx)
        assert not hasattr(s, "_removed")

    def test_raises_when_remove_not_implemented(self):
        import pytest

        s = IrreversibleSpec()
        op = Absent(s)
        ctx = _make_ctx()
        with pytest.raises(NotImplementedError, match="does not support removal"):
            op(ctx)


# -- FailingSpec for event tests --


class ExistsButFailsRemove(Specification["FakeProject"]):
    """A spec that exists but raises on remove."""

    def equals(self, ctx: Context[FakeProject]) -> bool:
        return False

    def exists(self, ctx: Context[FakeProject]) -> bool:
        return True

    def apply(self, ctx: Context[FakeProject]) -> None:
        pass

    def remove(self, ctx: Context[FakeProject]) -> None:
        raise RuntimeError("remove boom")


class FailingSpec(Specification["FakeProject"]):
    """A spec that raises on apply."""

    def equals(self, ctx: Context[FakeProject]) -> bool:
        return False

    def exists(self, ctx: Context[FakeProject]) -> bool:
        return False

    def apply(self, ctx: Context[FakeProject]) -> None:
        raise RuntimeError("boom")

    def remove(self, ctx: Context[FakeProject]) -> None:
        raise RuntimeError("boom")


# -- SpecOp event tests --


class TestSpecOpEvents:
    def test_present_fires_start_and_finish(self):
        events = []
        ctx = _make_ctx()
        ctx.on_spec_start += lambda c, op: events.append("start")
        ctx.on_spec_finish += lambda c, op: events.append("finish")
        op = Present(AlwaysEqual())
        op(ctx)
        assert events == ["start", "finish"]

    def test_present_fires_applied(self):
        events = []
        ctx = _make_ctx()
        ctx.on_spec_applied += lambda c, op: events.append("applied")
        op = Present(NeverEqual())
        op(ctx)
        assert events == ["applied"]

    def test_present_fires_skipped_when_exists(self):
        reasons = []
        ctx = _make_ctx()
        ctx.on_spec_skipped += lambda c, op, reason: reasons.append(reason)
        op = Present(AlwaysEqual())
        op(ctx)
        assert reasons == ["already exists"]

    def test_present_fires_skipped_on_dry_run(self):
        reasons = []
        ctx = _make_ctx(dry_run=True)
        ctx.on_spec_skipped += lambda c, op, reason: reasons.append(reason)
        op = Present(NeverEqual())
        op(ctx)
        assert reasons == ["dry run; would apply"]

    def test_ensure_fires_applied(self):
        events = []
        ctx = _make_ctx()
        ctx.on_spec_applied += lambda c, op: events.append("applied")
        op = Ensure(ExistsButNotEqual())
        op(ctx)
        assert events == ["applied"]

    def test_ensure_fires_skipped_when_equal(self):
        reasons = []
        ctx = _make_ctx()
        ctx.on_spec_skipped += lambda c, op, reason: reasons.append(reason)
        op = Ensure(AlwaysEqual())
        op(ctx)
        assert reasons == ["up to date"]

    def test_ensure_fires_applied_when_equals_not_implemented(self):
        events = []
        ctx = _make_ctx()
        ctx.on_spec_applied += lambda c, op: events.append("applied")
        op = Ensure(SensitiveSpec())
        op(ctx)
        assert events == ["applied"]

    def test_ensure_fires_skipped_on_dry_run_when_equals_not_implemented(self):
        reasons = []
        ctx = _make_ctx(dry_run=True)
        ctx.on_spec_skipped += lambda c, op, reason: reasons.append(reason)
        op = Ensure(SensitiveSpec())
        op(ctx)
        assert reasons == ["dry run; would apply (equality unknown)"]

    def test_ensure_fires_skipped_on_dry_run(self):
        reasons = []
        ctx = _make_ctx(dry_run=True)
        ctx.on_spec_skipped += lambda c, op, reason: reasons.append(reason)
        op = Ensure(ExistsButNotEqual())
        op(ctx)
        assert reasons == ["dry run; would apply"]

    def test_absent_fires_removed(self):
        events = []
        ctx = _make_ctx()
        ctx.on_spec_removed += lambda c, op: events.append("removed")
        op = Absent(ExistsButNotEqual())
        op(ctx)
        assert events == ["removed"]

    def test_absent_fires_skipped_when_not_exists(self):
        reasons = []
        ctx = _make_ctx()
        ctx.on_spec_skipped += lambda c, op, reason: reasons.append(reason)
        op = Absent(NeverEqual())
        op(ctx)
        assert reasons == ["not present"]

    def test_absent_fires_skipped_on_dry_run(self):
        reasons = []
        ctx = _make_ctx(dry_run=True)
        ctx.on_spec_skipped += lambda c, op, reason: reasons.append(reason)
        op = Absent(ExistsButNotEqual())
        op(ctx)
        assert reasons == ["dry run; would remove"]

    def test_failed_event_fires_and_reraises(self):
        import pytest

        errors = []
        ctx = _make_ctx()
        ctx.on_spec_failed += lambda c, op, err: errors.append(str(err))
        op = Present(FailingSpec())
        with pytest.raises(RuntimeError, match="boom"):
            op(ctx)
        assert errors == ["boom"]

    def test_finish_fires_even_on_failure(self):
        import pytest

        events = []
        ctx = _make_ctx()
        ctx.on_spec_finish += lambda c, op: events.append("finish")
        op = Present(FailingSpec())
        with pytest.raises(RuntimeError):
            op(ctx)
        assert events == ["finish"]

    def test_ensure_failed_event_fires_and_reraises(self):
        import pytest

        errors = []
        ctx = _make_ctx()
        ctx.on_spec_failed += lambda c, op, err: errors.append(str(err))
        op = Ensure(FailingSpec())
        with pytest.raises(RuntimeError, match="boom"):
            op(ctx)
        assert errors == ["boom"]

    def test_absent_failed_event_fires_and_reraises(self):
        import pytest

        errors = []
        ctx = _make_ctx()
        ctx.on_spec_failed += lambda c, op, err: errors.append(str(err))
        op = Absent(ExistsButFailsRemove())
        with pytest.raises(RuntimeError, match="remove boom"):
            op(ctx)
        assert errors == ["remove boom"]

    def test_full_event_sequence(self):
        events = []
        ctx = _make_ctx()
        ctx.on_spec_start += lambda c, op: events.append("start")
        ctx.on_spec_applied += lambda c, op: events.append("applied")
        ctx.on_spec_finish += lambda c, op: events.append("finish")
        op = Ensure(ExistsButNotEqual())
        op(ctx)
        assert events == ["start", "applied", "finish"]


# -- Logging tests --


class TestSpecOpLogging:
    def test_present_logs_skip(self, caplog):
        s = AlwaysEqual()
        op = Present(s)
        with caplog.at_level(logging.DEBUG, logger="spectrik.specop"):
            op(_make_ctx())
        assert "already exists" in caplog.text

    def test_ensure_logs_skip(self, caplog):
        s = AlwaysEqual()
        op = Ensure(s)
        with caplog.at_level(logging.DEBUG, logger="spectrik.specop"):
            op(_make_ctx())
        assert "up to date" in caplog.text

    def test_absent_logs_skip(self, caplog):
        s = NeverEqual()
        op = Absent(s)
        with caplog.at_level(logging.DEBUG, logger="spectrik.specop"):
            op(_make_ctx())
        assert "not present" in caplog.text

    def test_present_logs_dry_run(self, caplog):
        s = NeverEqual()
        op = Present(s)
        with caplog.at_level(logging.INFO, logger="spectrik.specop"):
            op(_make_ctx(dry_run=True))
        assert "DRY RUN" in caplog.text

    def test_ensure_logs_equality_unknown(self, caplog):
        s = SensitiveSpec()
        op = Ensure(s)
        with caplog.at_level(logging.INFO, logger="spectrik.specop"):
            op(_make_ctx())
        assert "equality unknown" in caplog.text

    def test_ensure_logs_dry_run(self, caplog):
        s = ExistsButNotEqual()
        op = Ensure(s)
        with caplog.at_level(logging.INFO, logger="spectrik.specop"):
            op(_make_ctx(dry_run=True))
        assert "DRY RUN" in caplog.text

    def test_absent_logs_dry_run(self, caplog):
        s = ExistsButNotEqual()
        op = Absent(s)
        with caplog.at_level(logging.INFO, logger="spectrik.specop"):
            op(_make_ctx(dry_run=True))
        assert "DRY RUN" in caplog.text


# -- @spec() decorator tests --


class TestSpecDecorator:
    def test_registers_class(self):
        from spectrik.spec import _spec_registry

        @spec("test_widget")
        class Widget(AlwaysEqual):
            pass

        assert _spec_registry["test_widget"] is Widget

    def test_returns_class_unchanged(self):
        @spec("test_gadget")
        class Gadget(AlwaysEqual):
            pass

        assert Gadget.__name__ == "Gadget"
