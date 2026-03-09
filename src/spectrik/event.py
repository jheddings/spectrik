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
