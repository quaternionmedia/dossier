"""A fresh installation, driven the way a person drives it.

WHY THIS CATEGORY EXISTS. Every failure reported against this project reached
`main` with the suite green, because the suite built its own fixtures and
patched its own internals -- it tested a model of the system rather than the
system. The database that broke was the one the CLI chooses, in the directory
the user happened to stand in, created by the startup path no unit test ran.

So these tests run the real console script, as a subprocess, in a directory
that has nothing in it. No fixtures, no monkeypatching of internals: the only
thing injected is `DOSSIER_HOME`, so a run cannot touch the operator's own
state.

They are slower than the rest of the suite and there are deliberately few of
them. Their job is to catch the class of failure that only exists between the
parts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.structural import repo_root


def run(args: list[str], cwd: Path, home: Path, **kwargs) -> subprocess.CompletedProcess:
    """The real CLI, as a process, isolated from the operator's own state."""
    env = dict(os.environ)
    env["DOSSIER_HOME"] = str(home)
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    return subprocess.run(
        [sys.executable, "-m", "dossier.cli", *args],
        cwd=str(cwd), env=env, capture_output=True, text=True,
        timeout=300, **kwargs,
    )


@pytest.fixture()
def empty(tmp_path: Path) -> tuple[Path, Path]:
    work = tmp_path / "work"
    home = tmp_path / "home"
    work.mkdir()
    home.mkdir()
    return work, home


def test_a_first_command_leaves_a_database_the_migrations_built(empty):
    """`create_all` produced a database that worked that day and could never be
    migrated. Every schema failure reported here began there."""
    work, home = empty
    result = run(["db", "health"], work, home)
    assert result.returncode == 0, result.stderr

    database = work / "dossier.db"
    assert database.exists(), "the first command created no database"

    connection = sqlite3.connect(str(database))
    stamp = connection.execute("select version_num from alembic_version").fetchone()
    columns = {row[1] for row in connection.execute("pragma table_info(project)")}
    connection.close()

    assert stamp is not None, "the database carries no migration stamp"
    assert {"is_fork", "is_archived"} <= columns


def test_health_reports_a_fresh_installation_as_usable(empty):
    work, home = empty
    result = run(["db", "health"], work, home)
    assert result.returncode == 0
    assert "will fail at runtime" not in result.stdout


def test_health_names_the_missing_token_without_failing(empty):
    """A first run without a token is a condition to know about, not a fault."""
    work, home = empty
    result = run(["db", "health"], work, home)
    assert "No GitHub token" in result.stdout
    assert result.returncode == 0


def test_the_commands_work_from_a_directory_that_is_not_the_repository(empty):
    """`alembic.ini` was loaded relative to the working directory, so this
    worked only when the caller happened to stand in the repository root."""
    work, home = empty
    assert not (work / "alembic.ini").exists()
    assert run(["db", "current"], work, home).returncode == 0
    assert run(["db", "health"], work, home).returncode == 0


def test_a_second_command_in_one_process_still_writes_its_output():
    """Alembic binds `sys.stdout` as a default argument at import time, so the
    second command in a process wrote to the first one's stream."""
    from click.testing import CliRunner

    from dossier.cli import cli

    runner = CliRunner()
    runner.invoke(cli, ["--help"])
    result = runner.invoke(cli, ["db", "current"])
    assert result.exit_code == 0, result.exception


def test_projects_list_works_on_an_empty_installation(empty):
    work, home = empty
    result = run(["projects", "list"], work, home)
    assert result.returncode == 0, result.stderr


def test_the_module_entry_point_sees_every_command(empty):
    """Commands appended after the `__main__` guard are not registered when the
    module is run as `python -m`. It worked through the console script, which
    imports the whole module first, so the gap was invisible."""
    work, home = empty
    for command in (["db", "health"], ["gates", "list"], ["deltas", "--help"]):
        result = run(command, work, home)
        assert "No such command" not in result.output if hasattr(result, "output") \
            else "No such command" not in (result.stdout + result.stderr), command
        assert result.returncode == 0, (command, result.stderr)


def test_the_gates_route_names_every_seed_script_that_exists(empty):
    """A route that names a script the submodule does not carry sends a reader
    to a path that is not there."""
    work, home = empty
    result = run(["gates", "list"], work, home)
    assert result.returncode == 0

    root = repo_root()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith("runs:") or "project-seed" not in line:
            continue
        script = next(part for part in line.split() if part.endswith(".py"))
        assert (root / script).is_file(), f"{script} is named but not present"

