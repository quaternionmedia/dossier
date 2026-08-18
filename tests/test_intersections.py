"""What a project touches, and what the view refuses to imply."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier import intersections as ix
from dossier.models.governance import GovernanceRepository
from dossier.models.schemas import (
    Project,
    ProjectComponent,
    ProjectContributor,
    ProjectDependency,
)

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        mine = Project(name="org/mine", full_name="org/mine", github_owner="org",
                       github_repo="mine")
        peer = Project(name="org/peer", full_name="org/peer", github_owner="org")
        fork = Project(name="org/fork", full_name="org/fork", github_owner="org",
                       is_fork=True)
        s.add_all([mine, peer, fork])
        s.commit()
        for p in (mine, peer, fork):
            s.refresh(p)

        for pid in (mine.id, peer.id, fork.id):
            s.add_all([
                ProjectDependency(project_id=pid, name="pytest", source="pyproject.toml"),
                ProjectDependency(project_id=pid, name="sqlmodel", source="pyproject.toml"),
            ])
        s.add_all([
            ProjectContributor(project_id=mine.id, username="ada", contributions=1),
            ProjectContributor(project_id=peer.id, username="ada", contributions=1),
            ProjectContributor(project_id=fork.id, username="ada", contributions=1),
            ProjectComponent(parent_id=mine.id, child_id=peer.id,
                             relationship_type="related"),
            GovernanceRepository(name="mine", branch_ref="origin/project/mine",
                                 branch_commit="abcdef0123456789", behind_corpus=33,
                                 ahead_of_corpus=3, seed_drift="match",
                                 phase="v0.0.1", precondition="met"),
        ])
        s.commit()
        yield s, mine, peer


def section(sections, title):
    return next(s for s in sections if s.title == title)


def test_governance_reports_the_pin_and_the_distance(session):
    s, mine, _ = session
    gov = section(ix.build(s, mine, now=NOW), "Governance")
    values = dict(gov.rows)
    assert values["submodule branch"] == "origin/project/mine"
    assert values["behind corpus"] == "33"
    assert values["pinned commit"] == "abcdef012345", "a pin is shown short, not whole"


def test_a_project_outside_the_roster_says_so_without_a_verdict(session):
    s, _, peer = session
    gov = section(ix.build(s, peer, now=NOW), "Governance")
    assert gov.rows == ()
    assert "not a verdict" in gov.note


def test_ubiquitous_packages_are_not_an_intersection(session):
    """Sharing pytest says nothing; sharing sqlmodel is a choice."""
    s, mine, _ = session
    deps = section(ix.build(s, mine, now=NOW), "Shared dependencies")
    shared = {row[0]: row[2] for row in deps.rows}
    assert "sqlmodel" in shared["org/peer"]
    assert "pytest" not in shared["org/peer"]


def test_forks_are_excluded_from_both_observed_links(session):
    s, mine, _ = session
    built = ix.build(s, mine, now=NOW)
    for title in ("Shared dependencies", "Shared contributors"):
        assert all("fork" not in row[0] for row in section(built, title).rows), title


def test_shared_contributors_name_the_people(session):
    s, mine, _ = session
    people = section(ix.build(s, mine, now=NOW), "Shared contributors")
    assert people.rows[0][0] == "org/peer"
    assert "ada" in people.rows[0][2]


def test_a_declared_link_carries_its_direction_and_kind(session):
    s, mine, _ = session
    declared = section(ix.build(s, mine, now=NOW), "Declared components")
    assert declared.rows == (("parent of", "org/peer", "related"),)


def test_the_strongest_link_is_first(session):
    s, mine, _ = session
    assert [x.title for x in ix.build(s, mine, now=NOW)][0] == "Governance"


@pytest.mark.asyncio
async def test_the_panel_draws_for_the_selected_project(session):
    s, mine, _ = session
    from dossier.tui.app import DossierApp
    from dossier.tui.intersections_panel import IntersectionsPanel

    class Borrowed:
        def __enter__(self): return s
        def __exit__(self, *e): return False

    app = DossierApp(session_factory=lambda: Borrowed())
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        panel = app.query_one(IntersectionsPanel)
        panel.show_for(mine)
        await pilot.pause()
        assert panel.project_name == "org/mine"
