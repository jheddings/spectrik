# Progress Callbacks for Spec Execution (#20) — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-spec lifecycle events so consumers can hook into the build chain for granular progress reporting.

**Architecture:** A lightweight `Event` class (callable list, adapted from juliet) lives in `event.py`. Six event instances are added to `Context`. Each `SpecOp` strategy fires the appropriate events around its execution logic. `Project.build()` gains an optional `ctx` parameter.

**Tech Stack:** Python 3.12+, pytest, existing spectrik patterns.

---

### Task 1: Event class

**Files:**
- Create: `src/spectrik/event.py`
- Test: `tests/test_event.py`

**Step 1: Write the failing tests**

In `tests/test_event.py`:

```python
"""Tests for spectrik.event."""

from spectrik.event import Event


class TestEvent:
    def test_call_invokes_handlers(self):
        results = []
        event = Event()
        event += lambda x: results.append(x)
        event("hello")
        assert results == ["hello"]

    def test_multiple_handlers(self):
        results = []
        event = Event()
        event += lambda: results.append("a")
        event += lambda: results.append("b")
        event()
        assert results == ["a", "b"]

    def test_remove_handler(self):
        results = []
        handler = lambda: results.append("x")
        event = Event()
        event += handler
        event -= handler
        event()
        assert results == []

    def test_kwargs_passed(self):
        results = []
        event = Event()
        event += lambda key=None: results.append(key)
        event(key="val")
        assert results == ["val"]

    def test_repr(self):
        event = Event()
        assert "Event" in repr(event)
```

**Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_event.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'spectrik.event'`

**Step 3: Write the implementation**

In `src/spectrik/event.py`:

```python
"""Lightweight event system for lifecycle callbacks."""

from __future__ import annotations


class Event(list):
    """A callable list of event handlers.

    Register handlers with ``+=``, unregister with ``-=``, and fire
    by calling the event instance.  Adapted from juliet.
    """

    def __iadd__(self, handler):
        self.append(handler)
        return self

    def __isub__(self, handler):
        self.remove(handler)
        return self

    def __call__(self, *args, **kwargs):
        for handler in self:
            handler(*args, **kwargs)

    def __repr__(self):
        return f"Event({list.__repr__(self)})"
```

**Step 4: Run tests to verify they pass**

Run: `just test -- tests/test_event.py -v`
Expected: PASS (all 5 tests)

**Step 5: Commit**

```bash
git add src/spectrik/event.py tests/test_event.py
git commit -m "feat(event): add Event class for lifecycle callbacks (#20)"
```

---

### Task 2: Add events to Context

**Files:**
- Modify: `src/spectrik/context.py`
- Modify: `tests/test_context.py`

**Step 1: Write the failing tests**

Add to `tests/test_context.py`:

```python
from spectrik.event import Event

# Add these tests to the existing TestContext class:

    def test_has_on_spec_start(self):
        ctx = Context(target=FakeProject())
        assert isinstance(ctx.on_spec_start, Event)

    def test_has_on_spec_finish(self):
        ctx = Context(target=FakeProject())
        assert isinstance(ctx.on_spec_finish, Event)

    def test_has_on_spec_applied(self):
        ctx = Context(target=FakeProject())
        assert isinstance(ctx.on_spec_applied, Event)

    def test_has_on_spec_removed(self):
        ctx = Context(target=FakeProject())
        assert isinstance(ctx.on_spec_removed, Event)

    def test_has_on_spec_skipped(self):
        ctx = Context(target=FakeProject())
        assert isinstance(ctx.on_spec_skipped, Event)

    def test_has_on_spec_failed(self):
        ctx = Context(target=FakeProject())
        assert isinstance(ctx.on_spec_failed, Event)
```

**Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_context.py -v`
Expected: FAIL — `AttributeError: 'Context' object has no attribute 'on_spec_start'`

**Step 3: Modify Context**

In `src/spectrik/context.py`, replace the entire file:

```python
"""Runtime execution context for the build pipeline."""

from __future__ import annotations

from .event import Event


class Context[P]:
    """Runtime state passed through the build chain."""

    def __init__(self, target: P, *, dry_run: bool = False) -> None:
        self.target = target
        self.dry_run = dry_run

        self.on_spec_start = Event()
        self.on_spec_finish = Event()
        self.on_spec_applied = Event()
        self.on_spec_removed = Event()
        self.on_spec_skipped = Event()
        self.on_spec_failed = Event()
```

**Step 4: Run tests to verify they pass**

Run: `just test -- tests/test_context.py -v`
Expected: PASS (all 10 tests)

**Step 5: Commit**

```bash
git add src/spectrik/context.py tests/test_context.py
git commit -m "feat(context): add spec lifecycle events (#20)"
```

---

### Task 3: Fire events from SpecOps

**Files:**
- Modify: `src/spectrik/specop.py`
- Modify: `tests/test_specs.py`

**Step 1: Write the failing tests**

Add a new test class to `tests/test_specs.py`:

```python
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

    def test_full_event_sequence(self):
        events = []
        ctx = _make_ctx()
        ctx.on_spec_start += lambda c, op: events.append("start")
        ctx.on_spec_applied += lambda c, op: events.append("applied")
        ctx.on_spec_finish += lambda c, op: events.append("finish")
        op = Ensure(ExistsButNotEqual())
        op(ctx)
        assert events == ["start", "applied", "finish"]
```

**Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_specs.py::TestSpecOpEvents -v`
Expected: FAIL — events lists are empty (events not fired yet)

**Step 3: Modify SpecOps to fire events**

Replace the contents of `src/spectrik/specop.py`:

```python
"""SpecOp strategies."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .context import Context
from .spec import Specification

logger = logging.getLogger(__name__)


class SpecOp[P](ABC):
    """Wraps a Specification with conditional execution logic."""

    def __init__(self, spec: Specification[P]) -> None:
        self.spec = spec

    @abstractmethod
    def __call__(self, ctx: Context[P]) -> None: ...


class Present[P](SpecOp[P]):
    """Apply only if resource doesn't exist."""

    def __call__(self, ctx: Context[P]) -> None:
        spec_name = type(self.spec).__name__
        ctx.on_spec_start(ctx, self)
        try:
            if self.spec.exists(ctx):
                logger.debug("Skipping %s; already exists", spec_name)
                ctx.on_spec_skipped(ctx, self, "already exists")
            elif ctx.dry_run:
                logger.info("[DRY RUN] Would apply %s", spec_name)
                ctx.on_spec_skipped(ctx, self, "dry run; would apply")
            else:
                logger.info("Applying %s", spec_name)
                self.spec.apply(ctx)
                ctx.on_spec_applied(ctx, self)
        except Exception as exc:
            ctx.on_spec_failed(ctx, self, exc)
            raise
        finally:
            ctx.on_spec_finish(ctx, self)


class Ensure[P](SpecOp[P]):
    """Apply if current state doesn't match."""

    def __call__(self, ctx: Context[P]) -> None:
        spec_name = type(self.spec).__name__
        ctx.on_spec_start(ctx, self)
        try:
            if self.spec.equals(ctx):
                logger.debug("Skipping %s; up to date", spec_name)
                ctx.on_spec_skipped(ctx, self, "up to date")
            elif ctx.dry_run:
                logger.info("[DRY RUN] Would apply %s", spec_name)
                ctx.on_spec_skipped(ctx, self, "dry run; would apply")
            else:
                logger.info("Applying %s", spec_name)
                self.spec.apply(ctx)
                ctx.on_spec_applied(ctx, self)
        except Exception as exc:
            ctx.on_spec_failed(ctx, self, exc)
            raise
        finally:
            ctx.on_spec_finish(ctx, self)


class Absent[P](SpecOp[P]):
    """Remove if resource exists."""

    def __call__(self, ctx: Context[P]) -> None:
        spec_name = type(self.spec).__name__
        ctx.on_spec_start(ctx, self)
        try:
            if self.spec.exists(ctx):
                if ctx.dry_run:
                    logger.info("[DRY RUN] Would remove %s", spec_name)
                    ctx.on_spec_skipped(ctx, self, "dry run; would remove")
                else:
                    logger.info("Removing %s", spec_name)
                    self.spec.remove(ctx)
                    ctx.on_spec_removed(ctx, self)
            else:
                logger.debug("Skipping removal of %s; not present", spec_name)
                ctx.on_spec_skipped(ctx, self, "not present")
        except Exception as exc:
            ctx.on_spec_failed(ctx, self, exc)
            raise
        finally:
            ctx.on_spec_finish(ctx, self)
```

**Step 4: Run tests to verify they pass**

Run: `just test -- tests/test_specs.py -v`
Expected: PASS (all tests including existing ones)

**Step 5: Commit**

```bash
git add src/spectrik/specop.py tests/test_specs.py
git commit -m "feat(specop): fire lifecycle events during spec execution (#20)"
```

---

### Task 4: Optional ctx parameter on Project.build()

**Files:**
- Modify: `src/spectrik/projects.py`
- Modify: `tests/test_projects.py`

**Step 1: Write the failing test**

Add to the `TestProject` class in `tests/test_projects.py`:

```python
    def test_build_with_ctx(self):
        events = []
        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test-proj", blueprints=[bp])
        ctx = Context(target=proj)
        ctx.on_spec_applied += lambda c, op: events.append("applied")
        proj.build(ctx=ctx)
        assert s.applied is True
        assert events == ["applied"]

    def test_build_with_ctx_preserves_dry_run(self):
        s = TrackingSpec()
        bp = Blueprint(name="bp", ops=[Ensure(s)])
        proj = Project(name="test-proj", blueprints=[bp])
        ctx = Context(target=proj, dry_run=True)
        proj.build(ctx=ctx)
        assert s.applied is False
```

**Step 2: Run tests to verify they fail**

Run: `just test -- tests/test_projects.py::TestProject::test_build_with_ctx -v`
Expected: FAIL — `build()` does not accept `ctx` kwarg (it goes into `**kwargs` and creates a new Context)

**Step 3: Modify Project.build()**

In `src/spectrik/projects.py`, replace the `build` method:

```python
    def build(self, *, ctx: Context | None = None, **kwargs) -> None:
        """Build all blueprints.

        If *ctx* is provided it is used directly; otherwise a new
        :class:`Context` is created from *kwargs*.
        """
        if ctx is None:
            ctx = Context(target=self, **kwargs)
        logger.info("Building project '%s'", self.name)
        for blueprint in self.blueprints:
            blueprint.build(ctx)
```

**Step 4: Run all tests to verify they pass**

Run: `just test -v`
Expected: PASS (all tests across all files)

**Step 5: Commit**

```bash
git add src/spectrik/projects.py tests/test_projects.py
git commit -m "feat(project): accept optional ctx in build() (#20)"
```

---

### Task 5: Export Event from public API

**Files:**
- Modify: `src/spectrik/__init__.py`

**Step 1: Add the export**

Add to `src/spectrik/__init__.py` after the Context import:

```python
from .event import Event as Event
```

**Step 2: Run full test suite**

Run: `just test -v`
Expected: PASS

**Step 3: Run preflight**

Run: `just preflight`
Expected: PASS

**Step 4: Commit**

```bash
git add src/spectrik/__init__.py
git commit -m "feat: export Event from public API (#20)"
```
