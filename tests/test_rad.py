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


def test_every_leaf_names_an_action():
    """A wedge with no action and no children is a dead end somebody committed."""
    for verb in resolve(None):
        for child in verb.children:
            assert child.action, f"{child.id} names no action"


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
    s.enter()
    intent = s.enter()
    assert isinstance(intent, Intent)
    assert intent.action == "view.deltas"
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
    s.enter()
    assert s.enter().path == (GO, "go.deltas")


def test_a_handler_is_called_with_the_intent():
    seen: list[Intent] = []
    s = session(on_intent=seen.append)
    s.open_at(None)
    s.enter()
    s.enter()
    assert len(seen) == 1 and seen[0].action == "view.deltas"


def test_keys_before_the_ring_is_open_do_nothing():
    s = session()
    assert s.rotate(+1) is None
    assert s.enter() is None
    assert s.back() is None


# --- the metering, which is rad's metric and not one invented here -----------


def test_ipa_counts_every_input_from_idle_to_commit():
    """open + enter + enter = 3. rad counts a keystroke as one input."""
    s = session()
    s.open_at(None)
    s.enter()
    assert s.enter().ipa == 3


def test_rotation_costs_an_input():
    s = session()
    s.open_at(None)
    s.rotate(+1)
    s.enter()
    assert s.enter().ipa == 4


def test_the_tally_resets_between_actions():
    """Otherwise the second action inherits the first one's cost and every
    figure after the first is wrong."""
    s = session()
    s.open_at(None); s.enter(); first = s.enter()
    s.open_at(None); s.enter(); second = s.enter()
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
    s.open_at(None); s.enter(); s.enter()
    report = s.cost_report()
    assert report["actions"] == 1
    assert report["ipa"] == 3
    assert report["apc"] == pytest.approx(1 / 3)


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
    s.open_at(None); s.enter()
    payload = s.enter().as_dict()
    assert payload["schema"] == 1
    assert payload["cost"]["ipa"] == 3
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
            # Selection is carried by the hub and a doubled border now, not by
            # brackets: the on-deck slot is what a reader checks.
            drawn = app.screen.query_one("#rad-ring").last_render
            lines = drawn.split(chr(10))
            assert "Do" in lines[len(lines) // 2], "the hub did not follow the selection"

            await pilot.press("enter")      # descend
            await pilot.pause()
            assert "Advance phase" in app.screen.query_one("#rad-ring").last_render

            await pilot.press("enter")      # commit
            await pilot.pause()
            assert type(app.screen).__name__ != "RingScreen", "ring did not close"
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
            await pilot.press("enter")      # Go
            await pilot.pause()
            await pilot.press("enter")      # Deltas
            await pilot.pause()
            assert app.query_one("#project-tabs").active == "tab-deltas"

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
            for _ in range(2):
                await self._open(pilot)
                await pilot.press("enter")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
            report = app._rad.cost_report()
            assert report["actions"] == 2
            assert report["ipa"] == 3
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


class TestRingLeavesTheDataVisible:
    """The ring is a pop-over, not a takeover.

    A `ModalScreen` covers the app by default, which hides the very data the
    menu is about to act on -- a menu whose options refer to a selection you can
    no longer see is worse than one costing an extra keystroke.
    """

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
            # The screen underneath is still mounted and still the dashboard --
            # the ring is stacked on it rather than replacing it.
            assert app.screen_stack[-2] is before
            assert app.screen.styles.background.a == 0, (
                "the ring's screen paints a ground and hides the dashboard")

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
