"""Fixtures shared by the TUI tests.

**A SESSION THE APP CANNOT CLOSE OUT FROM UNDER THE TEST.** `DossierApp` takes a
`session_factory` and uses it as a context manager, closing the session when it
is done. A test that hands it a live session gets that session closed halfway
through and fails somewhere unrelated, with an error about a detached instance
rather than about the app.

This wrapper was written once in `test_topology_tab.py` and needed a second time
the moment another UI test drove a real app. Put here rather than imported
across test modules, because a test importing another test file couples the two
in a way that breaks when either is renamed.

Note for whoever consolidates next: five modules under `tests/ui/` define their
own `session` fixture. Two are empty databases and duplicate `test_session` in
the parent conftest; three seed different project data and are genuinely
different fixtures that happen to share a name. Only the first two are
duplication.
"""

from __future__ import annotations

import pytest


class NoClose:
    """Hands out one session and refuses to close it."""

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def no_close():
    """The wrapper class, for `session_factory=lambda: no_close(session)`."""
    return NoClose
