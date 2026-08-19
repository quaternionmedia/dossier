"""What the health check finds, and what it refuses to do about it.

Written against the failure that produced it: a fresh run died with
`no such column: project.is_fork`, and nothing on screen said which database
was open or what to run next.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier import health
from dossier.models.schemas import Project


def make_db(path: Path, *, stamp: str | None = None, rows: int = 0,
            drop_columns: tuple[str, ...] = ()) -> Path:
    """A database in a chosen state of disrepair."""
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for index in range(rows):
            session.add(Project(name=f"org/r{index}", full_name=f"org/r{index}",
                                github_owner="org"))
        session.commit()

    connection = sqlite3.connect(str(path))
    if drop_columns:
        for column in drop_columns:
            connection.execute(f"alter table project drop column {column}")
    if stamp:
        connection.execute("create table if not exists alembic_version "
                           "(version_num varchar(32) not null)")
        connection.execute("insert into alembic_version values (?)", (stamp,))
    connection.commit()
    connection.close()
    return path


# --- the head revision -------------------------------------------------------


def test_the_head_is_the_revision_nothing_descends_from(tmp_path: Path):
    """Taking it from the filename returned `project`, the last word of a
    descriptive name, and every database then read as behind a revision that
    does not exist."""
    (tmp_path / "0001_first.py").write_text(
        'revision = "aaa"\ndown_revision = None\n', encoding="utf-8")
    (tmp_path / "0002_second_thing_to_project.py").write_text(
        'revision = "bbb"\ndown_revision = "aaa"\n', encoding="utf-8")
    assert health.code_revision(tmp_path) == "bbb"


def test_an_ambiguous_graph_answers_nothing_rather_than_guessing(tmp_path: Path):
    """Two heads is a real state -- a branched migration history -- and a
    confident wrong answer would report every database as behind."""
    (tmp_path / "a.py").write_text('revision = "aaa"\ndown_revision = None\n',
                                   encoding="utf-8")
    (tmp_path / "b.py").write_text('revision = "bbb"\ndown_revision = None\n',
                                   encoding="utf-8")
    assert health.code_revision(tmp_path) is None


def test_a_missing_versions_directory_is_not_an_error(tmp_path: Path):
    assert health.code_revision(tmp_path / "nope") is None


def test_the_annotated_revision_form_is_read(tmp_path: Path):
    """Alembic writes `down_revision: Union[str, None] = '...'`, and a pattern
    that only matched the bare form would see no parent and call every
    revision a head."""
    (tmp_path / "a.py").write_text('revision = "aaa"\ndown_revision = None\n',
                                   encoding="utf-8")
    (tmp_path / "b.py").write_text(
        'revision: str = "bbb"\ndown_revision: Union[str, None] = \'aaa\'\n',
        encoding="utf-8")
    assert health.code_revision(tmp_path) == "bbb"


# --- what inspect finds ------------------------------------------------------


def test_a_missing_column_is_blocking_and_names_the_fix(tmp_path: Path):
    """The exact failure this module exists for."""
    path = make_db(tmp_path / "old.db", stamp="whatever", rows=3,
                   drop_columns=("is_fork",))
    findings = health.inspect(path)
    blocking = [f for f in findings if f.is_blocking]
    assert blocking, "a missing column must block, not warn"
    assert "is_fork" in blocking[0].title
    # The command has to be one that actually repairs this. `db upgrade` is a
    # no-op when the stamp already claims head, which is how the reported
    # failure survived being "fixed".
    assert blocking[0].fix == "uv run dossier db health --fix"


def test_every_blocking_finding_carries_a_command(tmp_path: Path):
    """A check that reports a problem without naming the fix has moved the
    work rather than done it."""
    path = make_db(tmp_path / "old.db", rows=2, drop_columns=("is_fork",))
    for finding in health.inspect(path):
        if finding.is_blocking:
            assert finding.fix, f"{finding.title} blocks and offers no command"


def test_an_unstamped_database_is_reported(tmp_path: Path):
    path = make_db(tmp_path / "unstamped.db", rows=1)
    titles = [f.title for f in health.inspect(path)]
    assert any("no migration stamp" in title for title in titles)


def test_an_unstamped_empty_database_only_warns(tmp_path: Path):
    """Nothing is at risk and nothing will fail: it has the current schema."""
    path = make_db(tmp_path / "fresh.db")
    findings = health.inspect(path)
    assert not any(f.is_blocking for f in findings)


def test_a_healthy_database_says_so_once(tmp_path: Path):
    path = make_db(tmp_path / "good.db", stamp=health.code_revision() or "x", rows=1)
    findings = health.inspect(path)
    assert len(findings) == 1 and findings[0].level == health.OK


def test_a_database_that_does_not_exist_is_not_an_error(tmp_path: Path):
    findings = health.inspect(tmp_path / "absent.db")
    assert not any(f.is_blocking for f in findings)
    assert findings[0].fix and "sync" in findings[0].fix


# --- more than one database --------------------------------------------------


def test_two_populated_databases_are_reported_as_ambiguity(tmp_path, monkeypatch):
    """The condition behind the original failure: one migrated, one not, and
    nothing on screen saying which was open."""
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "work"
    cwd.mkdir()
    monkeypatch.setenv("DOSSIER_HOME", str(home))
    make_db(cwd / "dossier.db", stamp="aaa", rows=2)
    make_db(home / "dossier.db", stamp="aaa", rows=5)

    findings = health.check(cwd=cwd)
    ambiguity = [f for f in findings if "More than one database" in f.title]
    assert ambiguity, "two populated databases must be called out"
    assert "working directory" in ambiguity[0].detail
    assert ambiguity[0].fix


def test_one_populated_database_is_not_an_ambiguity(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "work"
    cwd.mkdir()
    monkeypatch.setenv("DOSSIER_HOME", str(home))
    make_db(cwd / "dossier.db", stamp="aaa", rows=2)

    findings = health.check(cwd=cwd)
    assert not any("More than one database" in f.title for f in findings)


# --- repair ------------------------------------------------------------------


def test_repair_refuses_an_unstamped_database_holding_data(tmp_path, monkeypatch):
    """No stamp can be inferred, and a wrong one marks migrations applied that
    never ran -- so the columns they would add never arrive and the failure
    resurfaces later looking like a different bug."""
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path))
    path = make_db(tmp_path / "data.db", rows=4, drop_columns=("is_fork",))
    actions = health.repair(path)
    assert actions and actions[0].startswith("refused")
    assert path.exists(), "a refusal must not delete anything"
    assert health.row_count(path) == 4


def test_repair_leaves_a_healthy_database_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path))
    path = make_db(tmp_path / "good.db", stamp=health.code_revision() or "x", rows=1)
    assert health.repair(path) == []


def test_row_count_survives_a_database_it_cannot_read(tmp_path):
    """A corrupt file must report nothing, not raise: the health check is what
    a person runs *because* something is wrong."""
    broken = tmp_path / "broken.db"
    broken.write_bytes(b"this is not a database")
    assert health.row_count(broken) == 0


def test_render_puts_the_fix_under_the_finding(tmp_path):
    path = make_db(tmp_path / "old.db", stamp="aaa", rows=1, drop_columns=("is_fork",))
    text = health.render(health.inspect(path))
    lines = text.splitlines()
    title = next(i for i, line in enumerate(lines) if "is missing" in line)
    assert any("fix:" in line for line in lines[title:title + 4])
    assert "will fail at runtime" in text


# --- the dashboard prepares itself -------------------------------------------


def test_an_unused_location_is_not_reported_as_a_problem(tmp_path, monkeypatch):
    """Reporting a database this installation does not use teaches a reader
    that warnings here are noise."""
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path / "unused"))
    make_db(tmp_path / "dossier.db", stamp=health.code_revision(), rows=1)
    findings = health.check(cwd=tmp_path)
    assert not any("does not exist" in finding.title for finding in findings)


def test_the_dashboard_refuses_rather_than_opening_a_broken_database(tmp_path, monkeypatch):
    """The refusal is the feature: the app would open and then fail on the
    first query naming a missing column."""
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path))
    make_db(tmp_path / "dossier.db", rows=3, drop_columns=("is_fork",))
    findings = health.check(cwd=tmp_path)
    assert health.worst(findings) == health.BLOCKED


def test_the_overview_defaults_to_the_organisation_this_database_is_about(tmp_path):
    """Local by default. Unscoped totals mix every owner ever synced, which
    describes the database rather than anybody's work."""
    from dossier.overview import dominant_owner

    engine = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for index in range(3):
            session.add(Project(name=f"org/r{index}", full_name=f"org/r{index}",
                                github_owner="org"))
        session.add(Project(name="other/one", full_name="other/one",
                            github_owner="other"))
        session.commit()
        assert dominant_owner(session) == "org"


def test_a_fork_does_not_decide_which_organisation_is_local(tmp_path):
    """A vendored copy of somebody else's work is not what this database is
    about, however many of them there are."""
    from dossier.overview import dominant_owner

    engine = create_engine(f"sqlite:///{tmp_path / 'f.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Project(name="org/one", full_name="org/one", github_owner="org"))
        for index in range(5):
            session.add(Project(name=f"up/f{index}", full_name=f"up/f{index}",
                                github_owner="upstream", is_fork=True))
        session.commit()
        assert dominant_owner(session) == "org"


def test_an_empty_database_has_no_local_organisation(tmp_path):
    from dossier.overview import dominant_owner

    engine = create_engine(f"sqlite:///{tmp_path / 'e.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        assert dominant_owner(session) is None


# --- a stamp that claims a migration ran when it did not ----------------------


def drifted_db(path: Path, rows: int = 1) -> Path:
    """Stamped at head, missing the columns head adds. A real reported state."""
    make_db(path, rows=rows, drop_columns=("is_fork", "is_archived"))
    connection = sqlite3.connect(str(path))
    connection.execute("create table if not exists alembic_version "
                       "(version_num varchar(32) not null)")
    connection.execute("insert into alembic_version values (?)",
                       (health.code_revision(),))
    connection.commit()
    connection.close()
    return path


def test_a_wrong_stamp_is_named_as_the_cause(tmp_path: Path):
    """`db upgrade` reported success and changed nothing, because alembic
    believed the database was already current."""
    path = drifted_db(tmp_path / "drifted.db")
    blocking = [f for f in health.inspect(path) if f.is_blocking]
    assert blocking
    assert "stamp" in blocking[0].detail
    assert "without changing anything" in blocking[0].detail


def test_the_advice_for_a_wrong_stamp_is_not_the_command_that_does_nothing(tmp_path: Path):
    """Recommending `db upgrade` here sent a reader in a circle."""
    path = drifted_db(tmp_path / "drifted.db")
    blocking = [f for f in health.inspect(path) if f.is_blocking]
    assert blocking[0].fix == "uv run dossier db health --fix"


def test_nothing_recommends_stamping_at_head():
    """That marks every migration applied, including ones that never ran, and
    the columns they add then never arrive. It is how a database reaches the
    state above."""
    source = Path("src/dossier/health.py").read_text(encoding="utf-8")
    assert "stamp head" not in source


def test_repair_moves_the_stamp_back_and_the_migration_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path))
    path = drifted_db(tmp_path / "drifted.db", rows=2)
    actions = health.repair(path, backup_first=False)
    # The stamp is rewound, exactly the migration that adds the column is run,
    # and the stamp is restored. Rewinding and upgrading to head instead
    # re-runs later migrations against work that is already there.
    assert any("restored the stamp" in action for action in actions), actions
    assert not [f for f in health.inspect(path) if f.is_blocking]


def test_repair_keeps_the_rows_it_repairs_around(tmp_path, monkeypatch):
    """A repair that loses data is not a repair."""
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path))
    path = drifted_db(tmp_path / "drifted.db", rows=4)
    health.repair(path, backup_first=False)
    assert health.row_count(path) == 4


def test_repair_reports_the_state_it_left_not_the_command_it_ran(tmp_path, monkeypatch):
    """The earlier version returned "upgraded to head" for a database that was
    still broken. Anything still blocking is named in the result."""
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path))
    path = drifted_db(tmp_path / "drifted.db", rows=1)

    # Make the repair impossible: no migration on disk introduces the column,
    # so it cannot rewind, and it must say so rather than claim success.
    monkeypatch.setattr(health, "migration_introducing", lambda column, root=None: None)
    actions = health.repair(path, backup_first=False)
    assert any("cannot repair" in action for action in actions)
    assert not any(action == "upgraded to head" for action in actions)


def test_the_migration_introducing_a_column_is_found_with_its_parent(tmp_path: Path):
    (tmp_path / "0001_base.py").write_text(
        'revision = "aaa"\ndown_revision = None\n', encoding="utf-8")
    (tmp_path / "0002_add.py").write_text(
        'revision = "bbb"\ndown_revision = "aaa"\n'
        'def upgrade():\n    op.add_column("project", sa.Column("is_fork"))\n',
        encoding="utf-8")
    assert health.migration_introducing("is_fork", tmp_path) == ("bbb", "aaa")


def test_a_column_no_migration_adds_is_not_invented(tmp_path: Path):
    (tmp_path / "0001_base.py").write_text(
        'revision = "aaa"\ndown_revision = None\n', encoding="utf-8")
    assert health.migration_introducing("nonexistent", tmp_path) is None


# --- the dashboard is the only command needed --------------------------------


def test_prepare_repairs_a_drifted_database(tmp_path, monkeypatch):
    """`uv sync` then `dossier dashboard`, and nothing else."""
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    drifted_db(tmp_path / "dossier.db", rows=2)

    actions, findings = health.prepare(cwd=tmp_path)
    assert actions, "prepare did nothing to a broken database"
    assert health.worst(findings) != health.BLOCKED


def test_prepare_is_quiet_when_there_is_nothing_to_do(tmp_path, monkeypatch):
    """A launch that prints repairs it did not make trains a reader to ignore
    the line."""
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    make_db(tmp_path / "dossier.db", stamp=health.code_revision(), rows=1)

    actions, findings = health.prepare(cwd=tmp_path)
    assert actions == []
    # Not "everything is OK": a missing GitHub token is a legitimate warning
    # about a first run and says nothing about the database. What "quiet"
    # means is that prepare changed nothing.
    assert not any(finding.is_blocking for finding in findings)


def test_prepare_runs_every_time_rather_than_behind_a_flag():
    """The state it repairs arrives from outside: pulling a branch with a new
    migration is the ordinary way to get it, and a flag saying `already
    initialised` would be true and useless."""
    source = Path("src/dossier/health.py").read_text(encoding="utf-8")
    body = source.split("def prepare(")[1].split("\ndef ")[0]
    assert "first-run flag" in body or "first_run" not in body


def test_the_status_line_says_where_the_data_is_and_how_much(tmp_path, monkeypatch):
    monkeypatch.setenv("DOSSIER_HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    make_db(tmp_path / "dossier.db", stamp=health.code_revision(), rows=7)

    line = health.summary_line(health.check(cwd=tmp_path), cwd=tmp_path)
    assert "7 project(s)" in line
    assert "ready" in line


def test_the_dashboard_prepares_reports_and_refuses():
    """All three, in that order, in the command a fresh clone runs."""
    source = Path("src/dossier/cli.py").read_text(encoding="utf-8")
    body = source.split("def dashboard(")[1].split("\ndef ")[0]
    assert "prepare()" in body, "dashboard does not run init"
    assert "summary_line" in body, "dashboard launches without saying what it opened"
    assert "SystemExit" in body, "dashboard would open a database it cannot read"
    assert body.index("prepare()") < body.index("DossierApp()")


def test_a_fresh_clone_gets_a_database_from_one_command(tmp_path, monkeypatch):
    """The end state the dashboard promises: `uv sync`, then `dossier
    dashboard`, and nothing else. No database exists anywhere here."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("DOSSIER_HOME", str(home))

    work = tmp_path / "work"
    work.mkdir()
    actions, findings = health.prepare(cwd=work)

    assert (work / "dossier.db").exists(), "prepare did not create a database"
    assert health.worst(findings) != health.BLOCKED
    assert any("head" in action for action in actions)


def test_prepare_works_from_a_directory_that_is_not_the_repository(tmp_path, monkeypatch):
    """`Config("alembic.ini")` is found only when the caller happens to be
    standing in the repository root, and the dashboard is meant to run from
    anywhere."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("DOSSIER_HOME", str(home))
    monkeypatch.chdir(tmp_path)

    actions, findings = health.prepare(cwd=tmp_path)
    assert health.worst(findings) != health.BLOCKED
    assert (tmp_path / "dossier.db").exists()


def test_the_project_root_is_found_from_the_package(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert (health.project_root() / "alembic.ini").is_file()
