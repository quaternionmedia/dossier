"""Three views became parts of others, and the evidence that said so.

**A TOP-LEVEL VIEW IS A CELL IN THE RING**, and the ring has eight per level.
Spending one on a reading that duplicates another is not a tidiness question:
it is the difference between a menu that fits and a menu that needs a level
nobody wanted. Measured against 115 synced repositories before the merges:

- 156 open pull requests, 156 open deltas, **138 the same item** by
  `(project, pr_number)`.
- **5 component links** across all 115, drawn twice -- once as a tree and once
  as a table -- on two different tabs.
- Branches read from the sync and branch hygiene read from the clones: one
  subject, two sources, and a reader had to choose the tab before they knew
  which side of the question they were on.

What these tests protect is that nothing was *lost* to the merges. Each one
names the half that a tidier-looking version would have dropped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from textual.widgets import DataTable

from dossier import facets
from dossier.tui.app import DossierApp

APP = Path("src/dossier/tui/app.py")

GONE = frozenset({"tab-prs", "tab-components", "tab-hygiene"})


def _composed() -> set[str]:
    text = APP.read_text(encoding="utf-8")
    return set(re.findall(r'TabPane\([^)]*id="(tab-[a-z-]+)"', text))


# --- the three that went ------------------------------------------------------


def test_the_merged_views_are_not_composed_any_more():
    """Mutation: put any of the three TabPanes back and this fails."""
    still_here = sorted(GONE & _composed())
    assert not still_here, f"{still_here} was merged but is still a tab"


def test_nothing_points_a_reader_at_a_tab_that_is_gone():
    """A navigation target that no longer exists is a click into nothing.

    The overview links rows to the tab holding their detail, and the project
    tree's folders do the same. Both had to be repointed.

    Mutation: leave one `"section": "tab-prs"` behind and this fails.
    """
    text = APP.read_text(encoding="utf-8")
    composed = _composed()
    referenced = set(re.findall(r'"section": "(tab-[a-z-]+)"', text))
    referenced |= set(re.findall(r'_activate_tab\("(tab-[a-z-]+)"\)', text))
    dangling = sorted(referenced - composed)
    assert not dangling, f"navigates to tabs that do not exist: {dangling}"


def test_every_facet_still_has_somewhere_to_be_drawn():
    """A facet whose tab was removed would read as an empty section forever."""
    composed = _composed()
    for facet in facets.FACETS:
        assert facet.tab in composed, f"{facet.key} points at {facet.tab}"


# --- what each merge had to keep ---------------------------------------------
#
# The first merge's half is asserted where the org-scope fixture lives:
# `tests/core/test_overview.py::test_a_pull_request_no_delta_claims_is_still_on_deck`.


def test_the_components_pane_moved_rather_than_went():
    """THE HALF THE SECOND MERGE COULD HAVE DROPPED.

    The Components tab was not only a second drawing of the links -- it held
    the buttons that create and remove them, and the panel showing what can be
    observed above what was declared. A merge that deleted the tab would have
    deleted the only way to edit a component.

    Mutation: remove the components pane from the Dossier tab and this fails.
    """
    text = APP.read_text(encoding="utf-8")
    dossier_tab = text[text.index('TabPane("Dossier"'):
                       text.index('TabPane("Details"')]
    for needed in ('id="components-table"', 'id="btn-add-component"',
                   'id="btn-link-parent"', 'id="btn-remove-component"',
                   "IntersectionsPanel", 'id="component-tree"'):
        assert needed in dossier_tab, f"{needed} did not move with the tab"


def test_both_branch_readings_are_on_the_branches_tab():
    """THE HALF THE THIRD MERGE COULD HAVE DROPPED.

    `BY_TAB` was one-to-one, so pointing hygiene at `tab-branches` used to
    replace the branches facet outright -- silently, with no error and one
    fewer entry.

    Mutation: make `_by_tab` keep one facet per tab and this fails.
    """
    on_branches = [f.key for f in facets.BY_TAB["tab-branches"]]
    assert on_branches == ["branches", "hygiene"], on_branches

    text = APP.read_text(encoding="utf-8")
    tab = text[text.index('TabPane("Branches"'):text.index('TabPane("Dep')]
    assert 'id="branches-table"' in tab and 'id="hygiene-table"' in tab
    assert "hygiene-heading" in tab, (
        "two tables with no heading between them is one table with a gap")


# --- and the tab still opens instantly ----------------------------------------


@pytest.mark.asyncio
async def test_the_sync_reading_is_drawn_before_the_clones_are_read(
        test_session, monkeypatch, no_close):
    """THE ONE THIS EXISTS FOR.

    Hygiene spawns git in every clone on the machine. Rendering both readings
    inline would make opening Branches cost what the overview was taught not to
    pay on its startup path, and process spawn is the cost that grows worst on
    the hardware this has to run on.

    Asserted on ordering and on the loading state, never on a duration: a
    timing test on this machine passes with the survey inline.

    Mutation: call `_render_facet_for_project` for hygiene directly in
    `_load_branches_tab` and this fails.
    """
    order: list[str] = []

    original_render = DossierApp._render_facet_for_project

    def render(self, facet, project, limit=None):
        order.append(facet.key)
        return original_render(self, facet, project, limit)

    def begin(self):
        order.append("worker")

    monkeypatch.setattr(DossierApp, "_render_facet_for_project", render)
    monkeypatch.setattr(DossierApp, "_read_hygiene", lambda self, p=None: begin(self))

    app = DossierApp(session_factory=lambda: no_close(test_session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        app._load_branches_tab(_AnyProject())
        await pilot.pause()
        loading = app.query_one("#hygiene-table", DataTable).loading

    assert order == ["branches", "worker"], order
    assert loading is True, "the second table did not say it was still reading"


class _AnyProject:
    """The branches facet takes an id and a name; nothing here reads more."""

    id = 1
    name = "org/one"
    full_name = "org/one"
