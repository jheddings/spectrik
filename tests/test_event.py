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

        def handler():
            results.append("x")

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
