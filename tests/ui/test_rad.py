"""rad in a terminal: the state machine, the metering, and the ring.

WHAT IS ACTUALLY UNDER TEST. Not that a menu appears -- that every key is
metered exactly once, that the four durable verbs are the four durable verbs, and
that the cost figures reconcile. A ring that looked right and under-counted its
inputs would report an IPA better than the truth, which is worse than reporting
none: the number is the thing the design is steered by.

THE SEAM IS TESTED TOO. `session.py` must import nothing from Textual, because
that is the whole reason extracting this package later is a move rather than a
rewrite. Asserted on the source, since the failure is an import line existing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dossier.rad import resolve
from dossier.rad.session import (
    DO,
    DURABLE_VERBS,
    GO,
    L0,
    L1,
    L2,
    L3,
    REACH,
    SHOW,
    Intent,
    RadSession,
    Wedge,
    budget_for,
)


def session(on_intent=None) -> RadSession:
    return RadSession(resolve=resolve, on_intent=on_intent)


# --- the durable palette -----------------------------------------------------


def test_the_top_level_is_the_four_durable_verbs():
    """Fixed, and identical in every host. A fifth is a contract change."""
    assert [w.id for w in resolve(None)] == [GO, DO, SHOW, REACH]


def test_every_top_level_verb_is_a_submenu():
    assert all(w.is_submenu for w in resolve(None))


def _walk_wedges(wedges, path=()):
    for wedge in wedges:
        here = (*path, wedge.label)
        yield wedge, here
        yield from _walk_wedges(wedge.children, here)


def test_every_leaf_names_an_action():
    """A wedge with no action and no children is a dead end somebody committed.

    **AT EVERY DEPTH, NOT JUST THE SECOND.** This looked one level down when
    the ring was two levels deep; `Go` now holds a group level, so a dead
    wedge three levels in would have passed a check that never reached it.
    """
    for wedge, path in _walk_wedges(resolve(None)):
        assert wedge.action or wedge.children, (
            f"{' > '.join(path)} names no action and opens nothing")
        assert not (wedge.action and wedge.children), (
            f"{' > '.join(path)} both commits and opens")


def first_leaf():
    """The wedge the highlight lands on if you only ever press enter.

    Returns `(wedge, depth)`, where depth is how many enters reach it.
    """
    wedge, depth = resolve()[0], 1
    while wedge.children:
        wedge, depth = wedge.children[0], depth + 1
    return wedge, depth


def first_leaf_path():
    """The ids walked through to reach it, for asserting on the whole path."""
    ids, wedge = [], resolve()[0]
    while True:
        ids.append(wedge.id)
        if not wedge.children:
            return tuple(ids)
        wedge = wedge.children[0]


def commit_first(s):
    """Enter until something commits, however deep the ring is.

    **DEPTH-AGNOSTIC ON PURPOSE.** These tests pressed enter exactly twice
    because the ring was exactly two levels; when `Go` grew a group level,
    eleven of them failed on the shape of the menu rather than on the state
    machine they exist to test. What is under test is that entering a wedge
    with children opens it and entering one without commits -- which is a
    property of the machine at any depth.
    """
    for _ in range(8):
        found = s.enter()
        if found is not None:
            return found
    raise AssertionError("nothing committed within eight levels")


def test_no_verb_exceeds_the_keyboard_budget():
    """Reported, not enforced -- but a *top-level* breach would mean the palette
    itself is over budget on its first use, which is worth failing on."""
    top = resolve(None)
    for verb in top:
        reach = 1 + (len(top) // 2) + 1 + (len(verb.children) // 2) + 1
        assert reach <= budget_for(len(top)) + budget_for(len(verb.children))


def test_the_context_argument_is_accepted_now_so_it_need_not_change_later():
    assert resolve("anything") == resolve(None)


# --- the state machine -------------------------------------------------------


def test_a_session_starts_closed():
    assert session().is_open is False
    assert session().view is None


def test_opening_shows_the_top_level():
    view = session().open_at(None)
    assert view is not None
    assert [w.id for w in view.wedges] == [GO, DO, SHOW, REACH]
    assert view.highlighted == 0


def test_a_resolver_with_nothing_leaves_the_ring_closed():
    """An empty ring is a dead end somebody has to escape from, and it reads as
    a broken menu rather than an absent one."""
    empty = RadSession(resolve=lambda ctx: ())
    assert empty.open_at(None) is None
    assert empty.is_open is False


def test_rotation_wraps_because_a_ring_has_no_ends():
    s = session()
    s.open_at(None)
    for _ in range(len(resolve(None))):
        s.rotate(+1)
    assert s.view.highlighted == 0
    s.rotate(-1)
    assert s.view.highlighted == len(resolve(None)) - 1


def test_entering_a_submenu_descends_rather_than_committing():
    s = session()
    s.open_at(None)
    assert s.enter() is None
    assert s.view.path == (GO,)
    assert s.view.highlighted == 0


def test_entering_a_leaf_commits_an_intent_and_closes():
    s = session()
    s.open_at(None)
    intent = commit_first(s)
    assert isinstance(intent, Intent)
    # Derived, not hardcoded: what sits first under `Go` is dossier's to
    # choose, and pinning its name here would make a menu edit look like a
    # broken state machine.
    assert intent.action == first_leaf()[0].action
    assert s.is_open is False


def test_back_climbs_one_level_then_closes():
    s = session()
    s.open_at(None)
    s.enter()
    assert s.back() is not None
    assert s.view.path == ()
    assert s.back() is None
    assert s.is_open is False


def test_the_intent_carries_the_verb_it_was_reached_through():
    """`Reach` and `Go` are different messages even when the leaf is similar."""
    s = session()
    s.open_at(None)
    s.rotate(+3)          # Reach
    s.enter()
    assert s.enter().verb == REACH


def test_the_intent_carries_the_whole_path():
    s = session()
    s.open_at(None)
    assert commit_first(s).path == first_leaf_path()


def test_a_handler_is_called_with_the_intent():
    seen: list[Intent] = []
    s = session(on_intent=seen.append)
    s.open_at(None)
    commit_first(s)
    assert len(seen) == 1
    assert seen[0].action == first_leaf()[0].action


def test_keys_before_the_ring_is_open_do_nothing():
    s = session()
    assert s.rotate(+1) is None
    assert s.enter() is None
    assert s.back() is None


# --- the metering, which is rad's metric and not one invented here -----------


def test_ipa_counts_every_input_from_idle_to_commit():
    """open, then one enter per level. rad counts a keystroke as one input.

    Derived from the menu's depth rather than typed: the figure was 3 when the
    ring was two levels and is 4 now that `Go` holds a group, and neither is a
    fact about the meter.
    """
    s = session()
    s.open_at(None)
    assert commit_first(s).ipa == 1 + first_leaf()[1]


def test_rotation_costs_an_input():
    s = session()
    s.open_at(None)
    s.rotate(+1)
    intent = commit_first(s)
    # **THE COMMITTED PATH, NOT `Go`'S DEPTH.** Rotating moves to another verb,
    # and the verbs are not all the same depth -- `Go` holds a group level and
    # `Do` does not. Reading the depth off the intent asks the question the
    # test means: open, rotate, and one enter per level it actually walked.
    assert intent.ipa == 2 + len(intent.path)


def test_the_tally_resets_between_actions():
    """Otherwise the second action inherits the first one's cost and every
    figure after the first is wrong."""
    s = session()
    s.open_at(None); first = commit_first(s)
    s.open_at(None); second = commit_first(s)
    assert first.ipa == second.ipa


def test_an_unrecognised_key_is_charged_at_l0_and_not_l1():
    """The abstraction ledger has to stay honest about keys the menu ignored."""
    s = session()
    s.open_at(None)
    before = dict(s.meter.counts)
    s.meter.raw(recognized=False)
    assert s.meter.counts[L0] == before[L0] + 1
    assert s.meter.counts[L1] == before[L1]


def test_the_ledger_reconciles():
    s = session()
    s.open_at(None); s.rotate(+1); s.enter(); s.enter()
    assert s.meter.reconciles()
    assert s.meter.counts[L3] == 1
    assert s.meter.counts[L2] >= s.meter.counts[L3]


def test_the_report_gives_ipa_and_its_inverse():
    s = session()
    s.open_at(None); commit_first(s)
    cost = 1 + first_leaf()[1]
    report = s.cost_report()
    assert report["actions"] == 1
    assert report["ipa"] == cost
    assert report["apc"] == pytest.approx(1 / cost)


def test_the_report_names_over_budget_actions_without_failing():
    """rad calls an over-budget verb a resolver design error. While the palette
    is settling this is pressure, not a gate -- so it is reported."""
    s = session()
    s.open_at(None)
    for _ in range(9):
        s.rotate(+1)
    s.enter()
    s.enter()
    report = s.cost_report()
    assert report["ipa"] > report["budget_top_level"]
    assert report["over_budget"]


def test_the_budget_is_rads_formula():
    assert budget_for(4) == 1 + 2 + 1
    assert budget_for(3) == 1 + 2 + 1
    assert budget_for(8) == 1 + 4 + 1


# --- geometry belongs to the session, not the widget -------------------------


def test_the_first_wedge_sits_at_twelve_oclock():
    import math

    view = session().open_at(None)
    assert view.angle_of(0) == pytest.approx(-math.pi / 2)


def test_the_wedges_are_evenly_spaced():
    view = session().open_at(None)
    gaps = [view.angle_of(i + 1) - view.angle_of(i) for i in range(len(view.wedges) - 1)]
    assert all(g == pytest.approx(gaps[0]) for g in gaps)


# --- the seam ----------------------------------------------------------------


def test_the_session_imports_nothing_from_textual():
    """The whole reason extracting this package later is a move and not a
    rewrite. Asserted on the source, because the failure is an import existing."""
    import dossier.rad.session as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    imports = "\n".join(line for line in source.splitlines()
                        if line.strip().startswith(("import ", "from ")))
    assert "textual" not in imports.lower()


def test_the_intent_serialises_to_a_message():
    s = session()
    s.open_at(None)
    payload = commit_first(s).as_dict()
    assert payload["schema"] == 1
    assert payload["cost"]["ipa"] == 1 + first_leaf()[1]
    assert payload["clock"] is None, "the clock is stubbed, not implemented"


def test_a_wedge_with_children_is_a_submenu_and_one_without_is_not():
    assert Wedge("a", "A", children=(Wedge("b", "B"),)).is_submenu
    assert not Wedge("a", "A", action="x").is_submenu


def test_the_durable_verbs_are_declared_once():
    assert [v[0] for v in DURABLE_VERBS] == [GO, DO, SHOW, REACH]


# --- the ring inside the real app -------------------------------------------


class TestRingInTheApp:
    """Driven through Textual's Pilot: the real app, the real screen, real keys.

    This is the part that proves the thing works rather than merely computes.
    """

    async def _open(self, pilot):
        """Open the ring and wait for it to become the current screen.

        Two pauses, not one: pushing a modal screen and that screen becoming
        `app.screen` are separate steps in Textual's loop, and asserting after
        one of them reads the previous screen -- which looks exactly like a
        menu that never opened.
        """
        await pilot.press("m")
        await pilot.pause()
        await pilot.pause()

    @pytest.mark.asyncio
    async def test_m_opens_a_centered_ring_showing_the_four_verbs(self):
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        app = DossierApp(session_factory=lambda: Session(engine))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await self._open(pilot)
            assert type(app.screen).__name__ == "RingScreen"
            drawn = app.screen.query_one("#rad-ring").last_render
            for label in ("Go", "Do", "Show", "Reach"):
                assert label in drawn

    @pytest.mark.asyncio
    async def test_arrows_move_the_highlight_and_enter_descends_then_commits(self):
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        app = DossierApp(session_factory=lambda: Session(engine))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await self._open(pilot)
            await pilot.press("right")      # Do
            await pilot.pause()
            # The centre no longer follows the selection: it backs out, at every
            # depth, so a reader never has to check what it means. Selection is
            # carried by the doubled border on the cell itself.
            drawn = app.screen.query_one("#rad-ring").last_render
            lines = drawn.split(chr(10))
            # The doubled border sits on the lines above and below the label,
            # not on the label's own line.
            row = next(i for i, line in enumerate(lines) if "Do" in line)
            column = lines[row].index("Do")
            assert "=" in lines[row - 1][max(0, column - 4):column + 4], (
                "the highlight did not move to Do")
            assert "close" in drawn, "the centre should offer to close at the top level"

            await pilot.press("enter")      # descend
            await pilot.pause()
            inside = app.screen.query_one("#rad-ring").last_render
            # STILL DRAWN, AND STILL ON ITS CELL. A menu that drops what it
            # cannot do renumbers everything after it, and the numbers are
            # written down in `docs/rad-commands.md`.
            assert "Advance phase" in inside
            assert "8 Advance phase" in inside, "it moved off cell 8"

            await pilot.press("enter")      # commit
            await pilot.pause()
            assert type(app.screen).__name__ != "RingScreen", "ring did not close"
            # **`delta.advance`, AND IT USED TO BE `project.sync`.** Entering a
            # submenu lands on the first wedge this app can act on, and until
            # the actions were reconciled into one dispatch table that was
            # Sync -- advance and note were in the ring, greyed, while buttons
            # did exactly them. All four under Do are wired now, so the
            # landing moved to the first cell. The behaviour did not change;
            # what the app can do did.
            assert app._rad.intents[-1].action == "delta.advance"

    @pytest.mark.asyncio
    async def test_escape_backs_out_a_level_then_closes(self):
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        app = DossierApp(session_factory=lambda: Session(engine))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await self._open(pilot)
            await pilot.press("enter")      # into Go
            await pilot.pause()
            await pilot.press("escape")     # back to top
            await pilot.pause()
            assert "Reach" in app.screen.query_one("#rad-ring").last_render
            await pilot.press("escape")     # closed
            await pilot.pause()
            assert type(app.screen).__name__ != "RingScreen"

    @pytest.mark.asyncio
    async def test_a_go_wedge_actually_changes_the_view(self):
        """The host half of the contract: rad decided, we applied."""
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        app = DossierApp(session_factory=lambda: Session(engine))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await self._open(pilot)
            leaf, depth = first_leaf()
            for _ in range(depth):
                await pilot.press("enter")
                await pilot.pause()
            expected = DossierApp.RAD_VIEWS[leaf.action]
            assert app.query_one("#project-tabs").active == expected

    @pytest.mark.asyncio
    async def test_the_cost_ledger_survives_across_actions(self):
        """One session for the app's lifetime, so IPA averages over real use."""
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        app = DossierApp(session_factory=lambda: Session(engine))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            depth = first_leaf()[1]
            for _ in range(2):
                await self._open(pilot)
                for _ in range(depth):
                    await pilot.press("enter")
                    await pilot.pause()
            report = app._rad.cost_report()
            assert report["actions"] == 2
            assert report["ipa"] == 1 + depth
            assert report["reconciles"] is True


# --- layout and the token layer ----------------------------------------------


class TestRingLayout:
    """Aesthetics that can be asserted: fit, no collisions, tokens only.

    A ring is a visual thing and most of it is judgement, but three properties
    are not: it must fit, nothing may overlap the hub, and no colour may be a
    literal. Those are the ones that break silently.
    """

    def _drawn(self, wedge_count: int = 4) -> str:
        from dossier.rad.ring import Ring
        from dossier.rad.session import RadSession, Wedge

        wedges = tuple(
            Wedge(f"w{i}", f"Item {i}", action=f"a{i}") for i in range(wedge_count)
        )
        s = RadSession(resolve=lambda ctx: wedges)
        view = s.open_at(None)
        ring = Ring()
        ring.render_view(view)
        return ring.last_render

    def test_the_ring_fits_its_grid(self):
        from dossier.rad.ring import GRID_COLS, GRID_ROWS

        for count in (2, 3, 4, 5, 6, 8):
            drawn = self._drawn(count)
            lines = drawn.split("\n")
            assert len(lines) <= GRID_ROWS, f"{count} wedges overflowed vertically"
            assert max(len(l) for l in lines) <= GRID_COLS, f"{count} overflowed wide"

    def test_no_wedge_lands_on_the_hubs_rule(self):
        """A wedge on the rule row reads as part of the rule."""
        for count in (2, 3, 4, 5, 6, 8):
            lines = self._drawn(count).split("\n")
            rule_rows = [i for i, l in enumerate(lines) if l.strip().startswith("-")]
            for row in rule_rows:
                assert lines[row].strip().strip("-") == "", (
                    f"{count} wedges: something shares the rule row: {lines[row]!r}")

    def test_the_selected_node_is_marked_in_the_plain_text(self):
        """rad treats accessibility as foundation. A selection carried by
        colour alone is invisible to a reader who cannot see it, so the border
        says it too."""
        drawn = self._drawn()
        assert "+===" in drawn, "the selected node has no doubled border"
        assert "+---" in drawn, "unselected nodes lost their border"

    def test_every_node_has_a_border(self):
        drawn = self._drawn(4)
        assert drawn.count("|") >= 4 * 2, "a node is missing its sides"

    def test_every_glyph_survives_a_cp1252_console(self):
        """This repository has already lost a demo to a folder emoji a Windows
        console could not encode. A ring that raises UnicodeEncodeError is not
        a prettier ring."""
        for count in (2, 3, 4, 6, 8):
            self._drawn(count).encode("cp1252")

    def test_the_markup_names_only_role_tokens(self):
        """rad's theme record: nothing paints outside the token layer. Every
        colour in the markup must be a value some role resolves to."""
        import re

        from dossier.rad.ring import Ring
        from dossier.rad.session import RadSession
        from dossier.rad.tokens import roles as role_tokens

        s = RadSession(resolve=resolve)
        view = s.open_at(None)
        markup = Ring().render_view(view)
        allowed = set(vars(role_tokens()).values())
        used = set(re.findall(r"\[(?:bold )?(#[0-9a-fA-F]{6})\]", markup))
        assert used, "nothing was coloured at all"
        assert used <= allowed, f"colours outside the role layer: {used - allowed}"

    def test_every_theme_resolves_every_role(self):
        from dossier.rad.tokens import Roles, roles as role_tokens, themes

        for theme in themes():
            resolved = role_tokens(theme)
            assert isinstance(resolved, Roles)
            for name, value in vars(resolved).items():
                assert value.startswith("#"), f"{theme}.{name} is not a colour"

    def test_an_unknown_theme_falls_back_rather_than_raising(self):
        from dossier.rad.tokens import DEFAULT_THEME, roles as role_tokens

        assert role_tokens("no-such-theme") == role_tokens(DEFAULT_THEME)

    def test_the_contrast_theme_uses_one_foreground(self):
        """Its whole point is >= 7:1 with no decorative colour.

        Ground roles are excluded, and that is not a loophole: a panel needs a
        background, and in `contrast` that background is black precisely so the
        white foregrounds clear 7:1 against it."""
        from dossier.rad.tokens import roles as role_tokens

        resolved = vars(role_tokens("contrast"))
        grounds = {"panel_bg"}
        foregrounds = {k: v for k, v in resolved.items() if k not in grounds}
        assert set(foregrounds.values()) <= {"#ffffff", "#f0f0f0"}
        assert resolved["panel_bg"] == "#000000"

    def test_the_panel_has_a_ground_of_its_own_in_every_theme(self):
        """The screen is transparent so the dashboard shows through. A panel
        without its own background would put the ring's text on top of the
        dashboard's, which is unreadable however good the colours are."""
        from dossier.rad.tokens import roles as role_tokens, themes

        for theme in themes():
            resolved = role_tokens(theme)
            assert resolved.panel_bg.startswith("#")
            assert resolved.panel_bg != resolved.wedge_label, (
                f"{theme}: the panel ground and its label are the same colour")


def _drawn_words(app) -> set[str]:
    """The text actually rendered, read out of an exported screenshot.

    THIS IS THE ASSERTION THAT MATTERS, and the first version of these tests did
    not make it. They checked `styles.background.a == 0` -- the mechanism -- and
    passed while the dashboard was completely hidden, because the layout
    containers inside the screen were painting their own ground. Checking the
    style is checking that the lever was pulled; this checks that something
    moved.
    """
    import re

    return set(re.findall(r">([^<>]{3,})<", app.export_screenshot()))


class TestRingLeavesTheDataVisible:
    """The ring is a pop-over, not a takeover.

    A `ModalScreen` covers the app by default, which hides the very data the
    menu is about to act on -- a menu whose options refer to a selection you can
    no longer see is worse than one costing an extra keystroke.
    """

    @pytest.mark.asyncio
    async def test_the_dashboards_text_is_still_drawn_behind_the_ring(self):
        """Most of the dashboard survives. Not all: the panel is opaque and
        covers what is directly under it, which is the point of a panel."""
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        app = DossierApp(session_factory=lambda: Session(engine))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            before = _drawn_words(app)
            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()
            after = _drawn_words(app)

            assert any("Go" in w for w in after), "the ring is not drawn"
            survived = before & after

            # A bare survival ratio is a proxy that moves with the density of
            # whatever tab is open: the same panel covers the same cells, so a
            # denser page loses a larger share of its words to it. What the
            # ring must not do is cover the page's frame, and that claim holds
            # at any density -- so it is asserted by name, and the ratio is
            # kept only as a floor.
            for edge in ("Quit", "Refresh", "Projects"):
                assert any(edge in word for word in after), (
                    f"{edge!r} is at the edge of the screen and the ring covered it")
            assert len(survived) > len(before) * 0.5, (
                f"only {len(survived)} of {len(before)} dashboard words survived; "
                f"the ring is covering the data it acts on")

    @pytest.mark.asyncio
    async def test_the_dashboard_still_renders_behind_the_ring(self):
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        app = DossierApp(session_factory=lambda: Session(engine))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            before = app.screen
            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()

            assert type(app.screen).__name__ == "RingScreen"
            assert app.screen_stack[-2] is before

    @pytest.mark.asyncio
    async def test_the_panel_itself_is_opaque(self):
        """The screen is transparent; the panel must not be, or the ring's text
        sits on top of the dashboard's."""
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        app = DossierApp(session_factory=lambda: Session(engine))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()
            ring = app.screen.query_one("#rad-ring")
            assert ring.styles.background.a == 1, "the panel is see-through"

    @pytest.mark.asyncio
    async def test_the_ring_is_only_as_big_as_it_needs_to_be(self):
        """Sized to its content, not to the terminal."""
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        app = DossierApp(session_factory=lambda: Session(engine))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()
            ring = app.screen.query_one("#rad-ring")
            assert ring.size.width < 120, "the panel spans the terminal"
            assert ring.size.height < 40, "the panel is as tall as the terminal"


class TestTheRingIsRecorded:
    """The ring, rendered, as a byproduct of asserting what it does.

    `governance/qm/records/DRAFT-one-executable-walkthrough.md` §4: what prose
    cannot hold is emitted by the test that asserts the behaviour, against the
    real production component, and **recorded rather than compared**. The
    picture is a byproduct of the render those assertions ran against, so it
    cannot drift from the code without a test failing first.

    It rides `uv run pytest`, deliberately. This repository's other screenshots
    are written only when `--screenshots` is passed, and the record's evidence
    is that artifacts needing a remembered command go stale while the ones
    riding the command people already run do not.

    Nothing here compares an image. A comparison would fail on a font, a
    terminal size or a colour change and teach a reader to regenerate without
    looking; the assertions below are what protect the behaviour.
    """

    OUTPUT = Path("docs/screenshots")

    def _record(self, app, name: str) -> None:
        """Write the recording, with the run-to-run id normalised out.

        **TEXTUAL NAMES ITS CSS CLASSES AFTER A PER-RUN NUMBER**, and that
        number appears in every rule and every element, so a recording that had
        not changed at all still produced a two-hundred-line diff on every
        commit. Four hundred lines of noise across the two ring recordings, in
        every pull request that happened to run the suite.

        Replacing it with the recording's own name makes the file a function of
        what is on screen, which is what it was always supposed to be: a diff
        now means the picture changed.
        """
        import re

        self.OUTPUT.mkdir(parents=True, exist_ok=True)
        drawn = app.export_screenshot(
            title=f"dossier — {name.replace('_', ' ')}")
        drawn = re.sub(r"terminal-\d+-", f"{name.replace('_', '-')}-", drawn)
        (self.OUTPUT / f"{name}.svg").write_text(drawn, encoding="utf-8")

    async def _app(self):
        from sqlmodel import Session, SQLModel, create_engine

        from dossier.models.schemas import Project
        from dossier.tui import DossierApp

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        session = Session(engine)
        for name in ("quaternionmedia/dossier", "quaternionmedia/qmcp",
                     "quaternionmedia/rad"):
            session.add(Project(name=name, full_name=name,
                                github_owner="quaternionmedia",
                                description="a repository",
                                github_language="Python"))
        session.commit()

        class Borrowed:
            def __enter__(self):
                return session

            def __exit__(self, *exc):
                return False

        return DossierApp(session_factory=lambda: Borrowed())

    @pytest.mark.asyncio
    async def test_the_ring_opens_over_the_dashboard_and_is_recorded(self):
        app = await self._app()
        async with app.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()

            drawn = app.export_screenshot()
            for verb in ("Go", "Do", "Show", "Reach"):
                assert verb in drawn, f"{verb} is not on the ring"
            self._record(app, "rad_ring_top_level")

    @pytest.mark.asyncio
    async def test_one_level_in_shows_that_verbs_children_and_is_recorded(self):
        from dossier.rad import resolve

        app = await self._app()
        async with app.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            drawn = app.export_screenshot()
            first_child = resolve()[0].children[0].label
            assert first_child in drawn, (
                f"{first_child!r} should be showing after entering the first verb")
            self._record(app, "rad_ring_one_level_in")

    @pytest.mark.asyncio
    async def test_two_levels_in_shows_a_view_and_is_recorded(self):
        """THE LEVEL THAT DID NOT EXIST BEFORE.

        `Go` held six views and now holds four groups that hold eighteen, so
        the picture a reader needs is the one showing a group opened. Without
        it the README documents a two-level ring and ships a photograph of it.
        """
        from dossier.rad import resolve

        app = await self._app()
        async with app.run_test(size=(120, 34)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            drawn = app.export_screenshot()
            group = resolve()[0].children[0]
            assert group.children, "the first verb's first child holds nothing"
            leaf = group.children[0].label
            assert leaf in drawn, (
                f"{leaf!r} should be showing two levels in")
            self._record(app, "rad_ring_two_levels_in")

    def test_every_recording_exists_after_the_tests_above(self):
        """They ride the ordinary test command, so a run leaves them current.

        This asserts the artifact, not the picture: an image comparison would
        fail on a font change and teach a reader to regenerate without looking.
        """
        for name in ("rad_ring_top_level", "rad_ring_one_level_in",
                     "rad_ring_two_levels_in"):
            path = self.OUTPUT / f"{name}.svg"
            assert path.is_file(), f"{path} was not recorded"
            assert path.stat().st_size > 0


class TestGreyedOutWedges:
    """Unavailable wedges, as drawn. The state has to survive losing colour."""

    def _view(self):
        from dossier.rad.session import RadSession, Wedge

        palette = (
            Wedge("a", "Alive", action="live"),
            Wedge("d", "Dead", action="dead"),
        )
        session = RadSession(resolve=lambda c=None: palette,
                             available=lambda w: w.action == "live")
        session.open_at()
        return session.view

    def test_the_border_says_unavailable_without_any_colour(self):
        """THE ONE THAT MATTERS.

        `contrast` has no fainter ink to grey with, by design, and a
        sixteen-colour terminal approximates everything. A state carried by
        colour alone is a wedge that looks ordinary and refuses to be chosen.
        `last_render` is the plain grid, before any markup.

        Mutation: draw unavailable nodes with the ordinary rule and this fails.
        """
        from dossier.rad.ring import Ring

        ring = Ring()
        ring.render_view(self._view())
        lines = ring.last_render.split(chr(10))

        dead_row = next(i for i, line in enumerate(lines) if "Dead" in line)
        live_row = next(i for i, line in enumerate(lines) if "Alive" in line)
        assert "." in lines[dead_row - 1], "no dotted rule above the dead wedge"
        assert "." not in lines[live_row - 1], (
            "the available wedge was drawn dotted too, so the rule says nothing")

    def test_an_unavailable_wedge_is_painted_in_its_own_role(self):
        from dossier.rad.ring import Ring
        from dossier.rad.tokens import roles as role_tokens

        markup = Ring().render_view(self._view())
        faint = role_tokens().wedge_label_unavailable
        assert f"[{faint}]" in markup, "nothing used the unavailable role"

    def test_the_contrast_theme_greys_with_the_border_and_not_with_colour(self):
        """Its rule is >= 7:1 with no decorative colour, so `ink_faint` there is
        `ink_dim`. The dotted border is what carries the state, and the test
        above proves the border is drawn regardless of theme."""
        from dossier.rad.tokens import roles as role_tokens

        contrast = role_tokens("contrast")
        assert contrast.wedge_label_unavailable == contrast.wedge_label
        radical = role_tokens("radical")
        assert radical.wedge_label_unavailable != radical.wedge_label, (
            "every other theme must actually look different")

    def test_the_centre_is_never_drawn_unavailable(self):
        """Backing out works at every level, including one where nothing else
        does. A greyed `5` would strand a reader in the ring."""
        from dossier.rad.ring import Ring

        ring = Ring()
        ring.render_view(self._view())
        lines = ring.last_render.split(chr(10))
        centre_row = next(i for i, line in enumerate(lines) if "close" in line)

        # The centre's own columns, not the whole row: three boxes share every
        # row of this grid, so a dotted rule somewhere on the line belongs to
        # whichever cell sits over it. A first version of this test read the
        # line and failed on the dead wedge's border two columns to the right.
        start = lines[centre_row].index("5 close") - 2
        end = lines[centre_row].index("|", start + 3) + 1
        above = lines[centre_row - 1][start:end]
        assert "-" in above, f"expected the ordinary rule, got {above!r}"
        assert "." not in above, f"the centre was drawn dotted: {above!r}"
