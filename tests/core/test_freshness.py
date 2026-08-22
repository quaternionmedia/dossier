"""Whether the view in front of you is still true, and what would fix it.

The tests worth reading are the first two. Never-synced and stale are different
states, and a plan that reaches the network has to say what it would touch
before it touches it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier.freshness import (
    NOT_FROM_SYNC,
    STALE_AFTER_HOURS,
    Plan,
    Subject,
    plan_for,
)
from dossier.models.schemas import Project

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def add(session, name, *, owner="org", synced=None):
    project = Project(name=name, full_name=name, github_owner=owner,
                      description="a repository", github_language="Python",
                      last_synced_at=synced)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


# --- never is not stale, and neither is zero ---------------------------------


def test_never_synced_is_its_own_state_not_an_infinite_age():
    """THE ONE THAT MATTERS.

    A repository nobody has ever synced has no age. Calling that "stale" makes
    a first-time setup read as a hundred out-of-date repositories, and calling
    it fresh hides it entirely. It is `never`, it sorts ahead of everything
    stale, and `age_hours` is None rather than 0.

    Mutation: return `float("inf")` for a missing timestamp and this fails --
    the state becomes "stale" and `age_hours` stops being None.
    """
    subject = Subject(name="org/one", age_hours=None)
    assert subject.state == "never"
    assert subject.ago == "never"
    assert subject.age_hours is not 0  # noqa: F632 -- identity is the point
    assert subject.age_hours is None


def test_a_just_synced_repository_is_fresh_and_zero_hours_is_a_real_age():
    """Zero is a measurement here, not a missing value: synced a moment ago.
    It must not be confused with never, in either direction."""
    subject = Subject(name="org/one", age_hours=0.0)
    assert subject.state == "fresh"
    assert subject.ago == "just now"


def test_the_threshold_is_the_one_the_overview_already_uses():
    """A second definition of `stale` on the same screen is two screens."""
    from dossier.overview import STALE_AFTER_DAYS

    assert STALE_AFTER_HOURS == STALE_AFTER_DAYS * 24
    assert Subject("a", STALE_AFTER_HOURS - 1).state == "fresh"
    assert Subject("a", STALE_AFTER_HOURS + 1).state == "stale"


# --- the plan says what it would touch ----------------------------------------


def test_a_plan_names_every_subject_before_anything_is_fetched(session):
    """THE OTHER ONE THAT MATTERS.

    Refreshing the org overview reaches every repository in scope. A menu item
    that does that silently because somebody pressed two keys is what
    `DRAFT-no-unattended-spending.md` is about, so the count is available
    before the work rather than after it.

    Mutation: have `plan_for` perform the sync and this fails on the network.
    """
    add(session, "org/fresh", synced=NOW - timedelta(hours=1))
    add(session, "org/old", synced=NOW - timedelta(days=90))
    add(session, "org/new")

    plan = plan_for(session, owner="org", now=NOW)
    assert len(plan.subjects) == 3
    assert {s.name for s in plan.never} == {"org/new"}
    assert {s.name for s in plan.stale} == {"org/old"}
    assert {s.name for s in plan.fresh} == {"org/fresh"}


def test_wanted_puts_never_synced_first_then_the_stalest(session):
    """What a narrow refresh does first. A repository with no data at all is
    the one making the view wrong in the way a reader notices."""
    add(session, "org/older", synced=NOW - timedelta(days=200))
    add(session, "org/old", synced=NOW - timedelta(days=60))
    add(session, "org/new")
    add(session, "org/fine", synced=NOW - timedelta(hours=2))

    wanted = [s.name for s in plan_for(session, owner="org", now=NOW).wanted]
    assert wanted == ["org/new", "org/older", "org/old"]
    assert "org/fine" not in wanted


def test_the_oldest_subject_is_what_makes_the_view_stale(session):
    add(session, "org/a", synced=NOW - timedelta(days=3))
    add(session, "org/b", synced=NOW - timedelta(days=40))
    assert plan_for(session, owner="org", now=NOW).oldest.name == "org/b"


def test_never_synced_wins_over_any_age(session):
    """It is the stronger claim about the view being wrong, and it has no
    number to compare against."""
    add(session, "org/ancient", synced=NOW - timedelta(days=900))
    add(session, "org/new")
    assert plan_for(session, owner="org", now=NOW).oldest.name == "org/new"


# --- scope --------------------------------------------------------------------


def test_a_selected_project_narrows_the_plan_to_that_project(session):
    """Selecting a repository scopes every tab to it, so a refresh asked for
    from that screen means that repository and not its ninety neighbours."""
    add(session, "org/one", synced=NOW - timedelta(days=90))
    chosen = add(session, "org/two", synced=NOW - timedelta(days=90))

    plan = plan_for(session, project=chosen, now=NOW)
    assert [s.name for s in plan.subjects] == ["org/two"]
    assert plan.scope == "org/two"


def test_an_owner_narrows_the_plan_to_that_owner(session):
    add(session, "org/one", owner="org")
    add(session, "other/one", owner="other")

    plan = plan_for(session, owner="org", now=NOW)
    assert [s.name for s in plan.subjects] == ["org/one"]


def test_with_no_scope_the_plan_is_everything(session):
    add(session, "org/one", owner="org")
    add(session, "other/one", owner="other")

    plan = plan_for(session, now=NOW)
    assert len(plan.subjects) == 2
    assert plan.scope == "every repository"


# --- views a sync does not feed -----------------------------------------------


def test_a_view_a_sync_does_not_feed_says_what_does(session):
    """An empty plan and an inapplicable one read identically on screen unless
    one of them says so. Deltas arrive by ingest; syncing GitHub would not
    change that tab and reporting "nothing to do" would imply it was current.

    Mutation: drop the `NOT_FROM_SYNC` branch and this fails -- the plan comes
    back with every repository in it, offering to sync for a tab sync does not
    fill.
    """
    add(session, "org/one", synced=NOW - timedelta(days=90))

    plan = plan_for(session, tab="tab-deltas", owner="org", now=NOW)
    assert plan.inapplicable is not None
    assert "ingest" in plan.inapplicable
    assert plan.subjects == ()
    assert "ingest" in plan.summary()


def test_every_inapplicable_tab_names_what_does_fill_it():
    """A reason that only says "not this" leaves a reader with no next step."""
    for tab, reason in NOT_FROM_SYNC.items():
        assert reason and len(reason) > 10, tab


def test_a_repository_tab_is_planned_normally(session):
    """The repository-shaped tabs are all filled by the same sync, so none of
    them is special and none of them is inapplicable."""
    add(session, "org/one", synced=NOW - timedelta(days=90))
    plan = plan_for(session, tab="tab-languages", owner="org", now=NOW)
    assert plan.inapplicable is None
    assert len(plan.subjects) == 1


# --- what a reader is told ----------------------------------------------------


def test_an_empty_scope_is_not_reported_as_up_to_date(session):
    """Saying "up to date" about nothing is the more misleading of the two
    answers a reader could get.

    Mutation: make `is_current` true for an empty plan and this fails.
    """
    plan = plan_for(session, owner="nobody", now=NOW)
    assert plan.subjects == ()
    assert plan.is_current is False
    assert "nothing in scope" in plan.summary()


def test_the_summary_counts_never_and_stale_separately(session):
    add(session, "org/new")
    add(session, "org/old", synced=NOW - timedelta(days=90))
    add(session, "org/fine", synced=NOW - timedelta(hours=1))

    summary = plan_for(session, owner="org", now=NOW).summary()
    assert "1 never synced" in summary
    assert "1 stale" in summary
    assert "of 3 in scope" in summary


def test_a_current_view_says_so_and_names_its_oldest(session):
    """"Up to date" with no age is a claim a reader cannot check."""
    add(session, "org/a", synced=NOW - timedelta(hours=5))
    add(session, "org/b", synced=NOW - timedelta(hours=2))

    plan = plan_for(session, owner="org", now=NOW)
    assert plan.is_current
    assert "2 up to date" in plan.summary()
    assert "5h ago" in plan.summary()


# --- timestamps ---------------------------------------------------------------


def test_a_naive_timestamp_is_read_as_utc(session):
    """The database stores UTC. Reading a naive value as local time shifts
    every age by the offset, which on this machine is four hours -- enough to
    report a just-synced repository as stale-adjacent, or the reverse.

    Mutation: drop the tzinfo branch and this raises on the subtraction.
    """
    project = add(session, "org/one")
    project.last_synced_at = datetime(2026, 8, 20, 10, 0)  # naive
    session.add(project)
    session.commit()

    plan = plan_for(session, owner="org", now=NOW)
    assert plan.subjects[0].age_hours == pytest.approx(2.0)


def test_ages_are_worded_in_hours_then_days():
    assert Subject("a", 0.5).ago == "just now"
    assert Subject("a", 5.0).ago == "5h ago"
    assert Subject("a", 100.0).ago == "4d ago"


def test_a_plan_is_frozen():
    """It is a statement about a moment. Something that edited it after the
    fact would be describing a different moment under the same name."""
    plan = Plan(scope="org", subjects=())
    with pytest.raises(Exception):
        plan.scope = "elsewhere"
