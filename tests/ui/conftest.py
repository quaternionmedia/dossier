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


@pytest.fixture(autouse=True)
def _no_live_harness(monkeypatch):
    """**THE HARNESS TAB POLLS THE HARNESS OVER THE NETWORK, AND A TEST MUST NOT
    DEPEND ON ONE BEING UP.** Its live half runs in a worker thread; when a dev
    harness *is* up, that worker does real I/O, and under the parallel suite the
    thread slows unrelated screenshot captures into an intermittent failure. So
    it is stubbed for every UI test -- the client is tested against a mock in
    `tests/core/test_harness_run.py` and the panel update it feeds is driven
    directly in `test_harness_console.py`, neither of which needs a live worker.
    """
    from dossier.tui.app import DossierApp
    monkeypatch.setattr(DossierApp, "_refresh_harness_live",
                        lambda self: None, raising=False)
    # The Dossier tab is the default, so its harness-topology pane fires on
    # every selection; stub that worker for the same reason -- a live fetch
    # against a dev harness slows unrelated captures. The delta-link pane
    # beside it is dossier's own data and still draws.
    monkeypatch.setattr(DossierApp, "_run_dossier_topology",
                        lambda self, subject: None, raising=False)
