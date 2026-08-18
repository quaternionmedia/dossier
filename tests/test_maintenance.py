"""Backup and purge: the two operations that can lose data.

The purge tests assert on rows that remain as well as rows that go. A test that
only checks the deletion passes just as well when everything was deleted.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from dossier.maintenance import (
    PurgePlan,
    backup,
    purge_other_owners,
    timestamped_name,
)
from dossier.models.schemas import Project, ProjectIssue, ProjectLanguage


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        keep = Project(name="qm/keep", full_name="quaternionmedia/keep",
                       github_owner="quaternionmedia")
        drop = Project(name="tx/drop", full_name="Textualize/drop",
                       github_owner="Textualize")
        implied = Project(name="implied", full_name="Textualize/implied")
        unattributed = Project(name="loose")
        s.add_all([keep, drop, implied, unattributed])
        s.commit()
        for p in (keep, drop, implied, unattributed):
            s.refresh(p)
        s.add_all([
            ProjectLanguage(project_id=keep.id, language="Python", bytes_count=1),
            ProjectLanguage(project_id=drop.id, language="Python", bytes_count=1),
            ProjectIssue(project_id=drop.id, issue_number=1, title="x", state="open"),
        ])
        s.commit()
        yield s


def test_a_dry_run_changes_nothing(session):
    plan = purge_other_owners(session, "quaternionmedia")
    assert plan.applied is False
    assert session.exec(select(Project)).all().__len__() == 4


def test_the_plan_names_what_would_go(session):
    plan = purge_other_owners(session, "quaternionmedia")
    assert plan.projects == ["implied", "loose", "tx/drop"]
    assert plan.rows_by_table["project_language"] == 1
    assert plan.rows_by_table["project_issue"] == 1


def test_owner_is_read_from_full_name_when_the_column_is_empty(session):
    """A row synced without `github_owner` still has an owner in `full_name`."""
    plan = purge_other_owners(session, "quaternionmedia")
    assert "implied" in plan.projects


def test_an_unattributable_project_is_not_kept(session):
    """It cannot be shown to belong to the org, and keeping it would put it
    back into the denominator the purge exists to clean."""
    plan = purge_other_owners(session, "quaternionmedia")
    assert "loose" in plan.projects


def test_applying_removes_the_others_and_keeps_the_owner(session):
    purge_other_owners(session, "quaternionmedia", apply=True)
    remaining = session.exec(select(Project)).all()
    assert [p.name for p in remaining] == ["qm/keep"]


def test_applying_removes_the_child_rows_too(session):
    """Orphans are invisible in every view and present in every count."""
    purge_other_owners(session, "quaternionmedia", apply=True)
    langs = session.exec(select(ProjectLanguage)).all()
    assert len(langs) == 1, "the kept project's language row must survive"
    assert session.exec(select(ProjectIssue)).all() == []


def test_the_plan_matches_what_the_apply_does(session):
    """A dry run walks the same rows as a real one, so it can be trusted."""
    planned = purge_other_owners(session, "quaternionmedia")
    applied = purge_other_owners(session, "quaternionmedia", apply=True)
    assert applied.projects == planned.projects
    assert applied.rows_by_table == planned.rows_by_table


def test_purging_when_nothing_matches_is_a_no_op(session):
    purge_other_owners(session, "quaternionmedia", apply=True)
    again = purge_other_owners(session, "quaternionmedia", apply=True)
    assert again.projects == []
    assert again.total_rows == 0


# --- backup ------------------------------------------------------------------


def test_backup_copies_the_rows(tmp_path: Path):
    source = tmp_path / "src.db"
    engine = create_engine(f"sqlite:///{source}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Project(name="only", github_owner="quaternionmedia"))
        s.commit()

    target = backup(source, tmp_path / "out" / "copy.db")
    assert target.exists()
    copied = sqlite3.connect(str(target)).execute(
        "select name from project").fetchall()
    assert copied == [("only",)]


def test_backup_of_an_open_database_is_readable(tmp_path: Path):
    """The reason for the online API rather than a file copy: a copy taken
    while a connection is open must not be torn."""
    source = tmp_path / "live.db"
    engine = create_engine(f"sqlite:///{source}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as live:
        live.add(Project(name="held", github_owner="quaternionmedia"))
        live.commit()
        target = backup(source, tmp_path / "hot.db")
        rows = sqlite3.connect(str(target)).execute("select name from project").fetchall()
    assert rows == [("held",)]


def test_the_backup_name_is_stamped_and_sits_beside_the_source():
    stamped = timestamped_name(Path("/data/dossier.db"),
                               now=datetime(2026, 8, 18, 9, 30, 15, tzinfo=timezone.utc))
    assert stamped.name == "dossier.20260818T093015Z.backup.db"
    assert stamped.parent == Path("/data")


# --- deltas ------------------------------------------------------------------


@pytest.fixture()
def delta_session():
    from dossier.models.schemas import DeltaPhase, ProjectDelta, ProjectPullRequest

    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        p = Project(name="quaternionmedia/qmcp", github_owner="quaternionmedia")
        s.add(p)
        s.commit()
        s.refresh(p)
        s.add_all([
            ProjectDelta(project_id=p.id, name="leftover", title="leftover"),
            ProjectDelta(project_id=p.id, name="real", title="Real work",
                         description="Something a person wrote."),
            ProjectDelta(project_id=p.id, name="branchy", title="On a branch",
                         branch_name="feat/x"),
            ProjectPullRequest(project_id=p.id, pr_number=7, title="Add a thing",
                               state="open", author="ada", head_branch="feat/thing"),
            ProjectPullRequest(project_id=p.id, pr_number=8, title="Draft thing",
                               state="open", is_draft=True, head_branch="feat/draft"),
            ProjectPullRequest(project_id=p.id, pr_number=9, title="Closed",
                               state="closed"),
        ])
        s.commit()
        yield s


def test_a_stub_is_a_delta_with_no_evidence_of_work(delta_session):
    from dossier.maintenance import prune_stub_deltas

    assert prune_stub_deltas(delta_session) == ["leftover"]


def test_a_delta_with_only_a_branch_is_not_a_stub(delta_session):
    """A name heuristic would have taken this one."""
    from dossier.maintenance import prune_stub_deltas

    assert "branchy" not in prune_stub_deltas(delta_session)


def test_pruning_without_apply_deletes_nothing(delta_session):
    from dossier.maintenance import prune_stub_deltas
    from dossier.models.schemas import ProjectDelta

    prune_stub_deltas(delta_session)
    assert len(delta_session.exec(select(ProjectDelta)).all()) == 3


def test_pruning_removes_only_the_stub(delta_session):
    from dossier.maintenance import prune_stub_deltas
    from dossier.models.schemas import ProjectDelta

    prune_stub_deltas(delta_session, apply=True)
    names = sorted(d.name for d in delta_session.exec(select(ProjectDelta)).all())
    assert names == ["branchy", "real"]


def test_open_pull_requests_become_deltas(delta_session):
    from dossier.maintenance import deltas_from_pull_requests
    from dossier.models.schemas import ProjectDelta

    deltas_from_pull_requests(delta_session, apply=True)
    derived = {d.name: d for d in delta_session.exec(select(ProjectDelta)).all()
               if d.pr_number}
    assert sorted(derived) == ["pr-7", "pr-8"], "a closed PR is not work in flight"
    assert derived["pr-7"].branch_name == "feat/thing"


def test_a_draft_pull_request_is_implementation_not_review(delta_session):
    """Draft means incomplete and nothing else."""
    from dossier.maintenance import deltas_from_pull_requests
    from dossier.models.schemas import DeltaPhase, ProjectDelta

    deltas_from_pull_requests(delta_session, apply=True)
    rows = {d.name: d for d in delta_session.exec(select(ProjectDelta)).all() if d.pr_number}
    assert rows["pr-8"].phase == DeltaPhase.IMPLEMENTATION
    assert rows["pr-7"].phase == DeltaPhase.REVIEW


def test_rerunning_updates_rather_than_duplicating(delta_session):
    from dossier.maintenance import deltas_from_pull_requests
    from dossier.models.schemas import ProjectDelta

    deltas_from_pull_requests(delta_session, apply=True)
    deltas_from_pull_requests(delta_session, apply=True)
    derived = [d for d in delta_session.exec(select(ProjectDelta)).all() if d.pr_number]
    assert len(derived) == 2


def test_deriving_leaves_hand_written_deltas_alone(delta_session):
    """A delta this pass did not create is not a delta that should go."""
    from dossier.maintenance import deltas_from_pull_requests
    from dossier.models.schemas import ProjectDelta

    deltas_from_pull_requests(delta_session, apply=True)
    names = {d.name for d in delta_session.exec(select(ProjectDelta)).all()}
    assert {"real", "branchy"} <= names
