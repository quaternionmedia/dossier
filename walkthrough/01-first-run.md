# 01 — First run

Everything on this page runs. It is executed by the ordinary test command, so
an example that stops being true fails the build rather than sitting here
misleading somebody.

After `uv sync`, **one command** does the rest.

    uv run dossier dashboard

This page shows what that command does on your behalf, so that when it reports
something you know what it looked at.

## What "prepare" does

The dashboard prepares the database before it opens. That is the whole of
initialisation: create a database if there is none, apply migrations that have
not run, and correct a stamp that claims they did.

Start somewhere with nothing in it:

    >>> import pathlib, tempfile
    >>> work = pathlib.Path(tempfile.mkdtemp())
    >>> home = work / "home"
    >>> home.mkdir()
    >>> import os
    >>> os.environ["DOSSIER_HOME"] = str(home)

Nothing exists yet:

    >>> (work / "dossier.db").exists()
    False

Prepare it:

    >>> from dossier.health import prepare, worst, summary_line
    >>> actions, findings = prepare(cwd=work)
    >>> (work / "dossier.db").exists()
    True

The database is not merely present, it is one the migrations built — so alembic
knows what has run and the next migration will apply cleanly:

    >>> import sqlite3
    >>> connection = sqlite3.connect(str(work / "dossier.db"))
    >>> stamp = connection.execute("select version_num from alembic_version").fetchone()
    >>> stamp is not None
    True

This is the part worth understanding. Creating the tables directly, with
`SQLModel.metadata.create_all`, produces a database that works today and cannot
be migrated tomorrow: it carries no record of which migrations ran, and once it
holds data no such record can be inferred. Every schema failure reported against
this project came from that. The tables are built by migrations or not at all.

## What it tells you

    >>> worst(findings) != "blocked"
    True

`summary_line` is what the dashboard prints on the way in — where the data is,
how much of it there is, whether it is usable:

    >>> line = summary_line(findings, cwd=work)
    >>> "0 project(s)" in line
    True
    >>> "ready" in line
    True

An empty database is *ready*. It has nothing in it, which is a different
statement, and the next page is about filling it.

## When it cannot fix something

`prepare` repairs what can be repaired and refuses the rest. The case it
refuses: a database carrying data with no migration stamp. No stamp can be
inferred from a schema alembic has no record of, and a wrong one marks
migrations applied that never ran — so the columns they add never arrive and
the failure comes back later looking like a different bug.

    >>> from dossier.health import repair
    >>> from sqlmodel import Session, SQLModel, create_engine
    >>> from dossier.models.schemas import Project
    >>> orphan = work / "orphan.db"
    >>> engine = create_engine(f"sqlite:///{orphan}")
    >>> SQLModel.metadata.create_all(engine)
    >>> with Session(engine) as session:
    ...     session.add(Project(name="org/one", github_owner="org"))
    ...     session.commit()
    >>> connection = sqlite3.connect(str(orphan))
    >>> _ = connection.execute("alter table project drop column is_fork")
    >>> connection.commit()
    >>> connection.close()

    >>> [action.split(":")[0] for action in repair(orphan)]
    ['refused']

The dashboard will not open against a database in that state. Refusing is the
point: it would otherwise open and fail on the first query naming a missing
column, in the middle of a screen, with a message about SQLite rather than
about what to do.

## Checking an installation by hand

The same checks, on demand:

    >>> import subprocess, sys
    >>> result = subprocess.run(
    ...     [sys.executable, "-m", "dossier.cli", "db", "health"],
    ...     capture_output=True, text=True, cwd=str(work))
    >>> result.returncode
    0

`check=True` or a printed `returncode` on every example that runs a process:
doctest passes an example that raises nothing and declares no output, so a
command exiting non-zero would otherwise be reported as a success.

Add `--fix` to apply the repairs it names.

## Next

Nothing has been synced yet. `02-filling-it.md` covers that, including the rate
limit you will meet if you sync more than a handful of repositories without a
token.
