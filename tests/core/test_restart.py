"""Archiving this dossier, and starting an empty one.

**THERE WAS NO WAY BACK TO A FIRST RUN.** `dossier dev reset` drops every table
with no backup, and its entire safety net is the words "Use with caution in
production!" in a help text. Somebody who has synced the wrong owner, or been
following a tutorial, or filled the database with a hundred forks, is exactly
the person least likely to know that command exists and most likely to need it.

**TWO ARCHIVES, BECAUSE THEY FAIL DIFFERENTLY.** The database copy is faithful
and stops being restorable when the schema moves. The exports are portable and
lossy. Neither is a backup on its own, which is why nothing here offers a
choice between them at the moment a person is least able to make it.

**AND NOTHING IS DROPPED THAT WAS NOT COPIED.** The test that matters most is
the refusal: an archive-and-reinit whose archive half quietly failed is a
reinit, and the person asked for the other thing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from dossier import restart as module
from dossier.models.schemas import (
    Project,
    ProjectBranch,
    ProjectDelta,
    ProjectPullRequest,
)


@pytest.fixture()
def on_disk(tmp_path):
    """A real SQLite file, because the backup copies one."""
    database = tmp_path / "dossier.db"
    engine = create_engine(f"sqlite:///{database}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, engine, database


@pytest.fixture()
def in_memory():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, engine


def fill(session, projects=2):
    for n in range(projects):
        project = Project(name=f"qm/repo{n}", full_name=f"qm/repo{n}")
        session.add(project)
        session.flush()
        session.add(ProjectBranch(project_id=project.id, name="main"))
        session.add(ProjectPullRequest(project_id=project.id, pr_number=n + 1,
                                       title=f"PR {n + 1}", state="open"))
    session.commit()


# --- the count is the plan ----------------------------------------------------


def test_it_counts_every_table_it_would_empty(in_memory):
    """THE ONE THIS EXISTS FOR, on this half.

    `holding` walks the same list `reinit` drops, so what a person reads before
    confirming is what goes.

    Mutation: drop a model from `COUNTED` and its rows vanish from the plan and
    not from the database.
    """
    session, _ = in_memory
    fill(session, projects=3)

    was = module.holding(session)

    assert was.projects == 3
    assert was.counts["ProjectBranch"] == 3
    assert was.counts["ProjectPullRequest"] == 3
    assert was.total == 9
    assert "3 project(s)" in was.summary() and "9 row(s)" in was.summary()


def test_an_empty_dossier_says_so_rather_than_reporting_zeros(in_memory):
    session, _ = in_memory
    was = module.holding(session)
    assert was.is_empty
    assert "already empty" in was.summary()


def test_the_counted_list_covers_the_tables_a_download_writes():
    """A table `download.absorb` fills and this does not count is one whose
    rows disappear from every plan.

    Mutation: add a table to `absorb` and not to `COUNTED` and this fails.
    """
    from dossier import download

    written = {
        line.split("(")[0].strip()
        for line in ("ProjectLanguage(", "ProjectDependency(",
                     "ProjectContributor(", "ProjectIssue(", "ProjectBranch(",
                     "ProjectPullRequest(", "ProjectRelease(")
    }
    counted = {model.__name__ for model in module.COUNTED}
    assert written <= counted, sorted(written - counted)
    assert "DocumentSection" in counted and "Project" in counted


# --- the archive --------------------------------------------------------------


def test_it_takes_both_copies(on_disk):
    """THE OTHER ONE THIS EXISTS FOR.

    Faithful and portable. Neither is a backup on its own.

    Mutation: skip either half and this fails.
    """
    session, _, database = on_disk
    fill(session, projects=2)

    put_away = module.archive(session, database)

    assert put_away.backup is not None and put_away.backup.exists()
    assert put_away.backup.stat().st_size > 0
    assert len(put_away.exports) == 2, put_away.exports
    assert all(path.exists() and path.suffix == ".dossier"
               for path in put_away.exports)


def test_the_backup_is_a_real_database_not_an_empty_file(on_disk):
    """`maintenance.backup` goes through SQLite's online backup API. A copy
    that is the right size and holds no rows would pass a size check and lose
    everything.

    Mutation: touch an empty file instead and this fails.
    """
    session, _, database = on_disk
    fill(session, projects=2)

    put_away = module.archive(session, database)

    restored = create_engine(f"sqlite:///{put_away.backup}")
    with Session(restored) as reading:
        assert len(reading.exec(select(Project)).all()) == 2


def test_two_archives_on_one_day_do_not_overwrite_each_other(on_disk):
    """A fixed `exports/` loses the older one and only says so when somebody
    needs it.

    Mutation: default `into` to a constant and this fails.
    """
    session, _, database = on_disk
    fill(session, projects=1)

    from datetime import timedelta

    from dossier.models import utcnow

    first = module.archive(session, database, now=utcnow())
    second = module.archive(session, database,
                            now=utcnow() + timedelta(seconds=5))

    assert first.export_dir != second.export_dir
    assert first.backup != second.backup


def test_one_export_failing_does_not_abandon_the_archive(on_disk, monkeypatch):
    """The faithful copy is already taken and holds what the export lost. It
    is carried, not raised — and the caller decides.

    Mutation: let the exception out and this fails.
    """
    session, _, database = on_disk
    fill(session, projects=2)

    calls = {"n": 0}

    def sometimes(session, project, target):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("disk full")
        target.write_text("ok", encoding="utf-8")

    monkeypatch.setattr(module, "_write_export", sometimes)
    put_away = module.archive(session, database)

    assert len(put_away.failures) == 1
    assert "disk full" in put_away.failures[0][1]
    assert len(put_away.exports) == 1
    assert put_away.is_safe, "a lost export is not a lost backup"


def test_a_dossier_with_no_file_still_archives_its_exports(in_memory, tmp_path):
    """An in-memory database is a real dossier with nothing to copy.

    Mutation: require a database path and this raises.
    """
    session, _ = in_memory
    fill(session, projects=1)

    put_away = module.archive(session, database=None, into=tmp_path / "out")

    assert put_away.backup is None
    assert len(put_away.exports) == 1


# --- the refusal --------------------------------------------------------------


def test_it_refuses_to_empty_a_database_it_could_not_copy(on_disk, monkeypatch):
    """**THE ONE THAT MATTERS MOST.**

    An archive-and-reinit whose archive half silently failed is a reinit, and
    the person asked for the other thing. It raises, and the rows are still
    there afterwards.

    Mutation: proceed when `is_safe` is False and this fails on the row count.
    """
    session, engine, database = on_disk
    fill(session, projects=2)

    monkeypatch.setattr(
        module, "archive",
        lambda *a, **k: module.Archived(backup=None, exports=()))

    with pytest.raises(RuntimeError, match="not copied"):
        module.start_over(session, engine, database)

    assert len(session.exec(select(Project)).all()) == 2, (
        "it emptied a database it had not copied")


def test_start_over_archives_then_empties(on_disk):
    """The whole act, in the order the name promises.

    Mutation: empty before archiving and the backup holds nothing.
    """
    session, engine, database = on_disk
    fill(session, projects=2)

    was, put_away = module.start_over(session, engine, database)

    assert was.projects == 2, "the count was taken after the emptying"
    assert put_away.backup.exists()

    restored = create_engine(f"sqlite:///{put_away.backup}")
    with Session(restored) as reading:
        assert len(reading.exec(select(Project)).all()) == 2

    with Session(engine) as after:
        assert after.exec(select(Project)).all() == []
        assert after.exec(select(ProjectBranch)).all() == []


def test_the_tables_come_back_empty_rather_than_absent(on_disk):
    """`drop_all` then `create_all`. A dropped table that was not recreated is
    a dossier that raises on its first read rather than showing nothing.

    Mutation: drop without recreating and this fails.
    """
    session, engine, database = on_disk
    fill(session, projects=1)

    module.start_over(session, engine, database)

    with Session(engine) as after:
        assert after.exec(select(Project)).all() == []
        assert after.exec(select(ProjectDelta)).all() == []


def test_it_says_what_it_did_not_empty():
    """Somebody who has just emptied everything is entitled to know what they
    did not empty — the conversation archive is the harness's, and this does
    not reach it.

    Mutation: empty the list and this fails.
    """
    assert len(module.NOT_OURS_TO_EMPTY) >= 3
    for what, whose in module.NOT_OURS_TO_EMPTY.items():
        assert len(whose) > 25, f"{what}: the reason is a label"
    assert any("conversation" in what for what in module.NOT_OURS_TO_EMPTY)
