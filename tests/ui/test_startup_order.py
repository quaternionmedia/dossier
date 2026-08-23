"""The shell paints before the data arrives.

**RESPONSIVENESS AND DATA COMPLETENESS ARE NOT THE SAME REQUIREMENT**, and only
one of them has to be instant. `on_mount` used to finish by building the whole
project tree and selecting the last project, which loads that project's tabs —
so nothing was on screen until every row had been read. Profiled at start:
1.5 seconds inside `textual/widgets/_tree.py` and twenty-four thousand ORM row
loads, before the first frame.

A stated requirement is running on very underpowered hardware, where that gap is
not a fraction of a second.

These tests assert the *ordering*, never a duration. A timing assertion on a
developer's machine passes with the coupling restored.
"""

from __future__ import annotations

import pytest
from textual.widgets import Tree

from dossier.tui.app import DossierApp


@pytest.mark.asyncio
async def test_the_tree_is_not_built_during_mount(test_session, monkeypatch,
                                                  no_close):
    """THE ONE THIS EXISTS FOR.

    `on_mount` must return with the shell composed and the sidebar not yet
    filled. Asserted by when `_restore_view_state` runs, which is what reads
    the projects.

    Mutation: call `_restore_view_state` directly from `on_mount` and this
    fails.
    """
    order: list[str] = []

    original_mount = DossierApp.on_mount
    original_restore = DossierApp._restore_view_state

    def on_mount(self):
        original_mount(self)
        order.append("mounted")

    def restore(self):
        order.append("restored")
        return original_restore(self)

    monkeypatch.setattr(DossierApp, "on_mount", on_mount)
    monkeypatch.setattr(DossierApp, "_restore_view_state", restore)

    app = DossierApp(session_factory=lambda: no_close(test_session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()

    assert order[:1] == ["mounted"], order
    assert "restored" in order, "the sidebar never filled at all"


@pytest.mark.asyncio
async def test_the_sidebar_says_it_is_loading_rather_than_looking_empty(
        test_session, monkeypatch, no_close):
    """An empty sidebar is a claim that there are no projects.

    The loading state is set during mount and cleared by the restore, so a
    reader waiting on a slow machine is told which of the two they are seeing.

    Mutation: drop the `loading = True` in `on_mount` and this fails.
    """
    seen: list[bool] = []
    original = DossierApp._restore_view_state

    def restore(self):
        # Sampled at the moment the data work begins, which is the window a
        # person on slow hardware is actually looking at.
        try:
            seen.append(self.query_one("#project-tree", Tree).loading)
        except Exception:                          # noqa: BLE001
            seen.append(False)
        return original(self)

    monkeypatch.setattr(DossierApp, "_restore_view_state", restore)

    app = DossierApp(session_factory=lambda: no_close(test_session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        after = app.query_one("#project-tree", Tree).loading

    assert seen == [True], f"the tree was not marked loading: {seen}"
    assert after is False, "the loading state was never cleared"


@pytest.mark.asyncio
async def test_the_shell_is_on_screen_before_the_data(test_session, no_close):
    """The skeleton is what makes waiting tolerable, so it has to exist.

    Mutation: compose the tabs only after the restore and this fails.
    """
    app = DossierApp(session_factory=lambda: no_close(test_session))
    async with app.run_test(size=(160, 50)) as pilot:
        # Before any pause: mount has run, the after-refresh work has not.
        assert app.query("#project-tabs"), "no tab bar in the first frame"
        assert app.query("#project-tree"), "no sidebar in the first frame"
        await pilot.pause()
