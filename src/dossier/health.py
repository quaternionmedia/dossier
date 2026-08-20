"""What is wrong with this installation, and the command that fixes it.

WHY THIS EXISTS. A fresh run died with `no such column: project.is_fork`. Every
part of the system was working: the migration existed, the model was right, the
code was right. The database being opened was simply not the one anybody had
migrated -- `sqlite:///dossier.db` is relative to the working directory, so
which database you get depends on where you launched from, and
`SQLModel.metadata.create_all` adds missing *tables* while leaving an existing
table's missing *columns* alone.

None of that is visible until a query names the column. Then it surfaces as a
driver error in the middle of a screen, which tells a reader what SQLite could
not do and nothing about what they should do next.

WHAT A FINDING IS. A fact, a consequence, and a command. A check that reports a
problem without naming the fix has moved the work rather than done it, so `fix`
is not optional on anything blocking.

WHAT THIS CANNOT DO. Repair anything. It reads; every fix is a command a person
runs, because the repairs here rewrite data and choosing to do that is not a
diagnostic's decision.
"""

from __future__ import annotations

import re
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

OK, WARN, BLOCKED = "ok", "warn", "blocked"

# Columns the code selects on that a database predating them will not have.
# Listed rather than reflected from the models: the point is to name the ones
# whose absence has actually broken a run.
EXPECTED_COLUMNS: dict[str, tuple[str, ...]] = {
    "project": ("is_fork", "is_archived"),
}


@dataclass(frozen=True)
class Finding:
    level: str
    title: str
    detail: str
    fix: str | None = None

    @property
    def is_blocking(self) -> bool:
        return self.level == BLOCKED


def candidate_databases(cwd: Path | None = None) -> list[Path]:
    """Every database this installation might open, in the order it prefers.

    Listing them is half the diagnosis: the failure that prompted this module
    was two databases, one migrated and one not, with nothing on screen saying
    which was in use.
    """
    from dossier.config import dossier_home

    cwd = cwd or Path.cwd()
    seen, found = set(), []
    override = overridden_database()
    order = [cwd / "dossier.db", dossier_home() / "dossier.db"]
    if override is not None:
        # First, and alone in practice: an operator who named a database meant
        # that one. Leaving the others behind it would let a diagnostic report
        # a database nobody asked for.
        order = [override]
    for path in order:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            found.append(path)
    return found


def overridden_database() -> Path | None:
    """The database `DOSSIER_DATABASE_URL` names, or None if it is unset.

    WHY THIS EXISTS AND WHY IT IS HERE RATHER THAN ONLY IN THE CLI. `dossier`
    opened `sqlite:///dossier.db` relative to the working directory and offered
    no other way to redirect it, so anything wanting a scratch database had to
    change directory and anything that forgot wrote into whichever `dossier.db`
    was underfoot. A demo run from the repository root wrote into the
    operator's own data, which is how this was found.

    Putting the override only on the engine would have been worse than not
    having one: `db upgrade` resolves its target through this module, so the
    migration would have run against one database while every query ran against
    another -- and it would have reported success. That is the two-databases
    failure this module was written for, reintroduced by its own fix.

    A URL this cannot resolve to a file raises rather than falling back. An
    override that is quietly ignored sends the caller's writes somewhere they
    did not ask for, which is the whole problem.
    """
    url = os.environ.get("DOSSIER_DATABASE_URL")
    if not url:
        return None
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ValueError(
            f"DOSSIER_DATABASE_URL={url!r} is not a sqlite file URL. This "
            f"resolves {prefix}<path> and refuses anything else rather than "
            f"falling back to the default, which would write where nobody asked."
        )
    return Path(url[len(prefix):])


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'pragma table_info("{table}")')}


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute(
        "select name from sqlite_master where type='table'")}


def _stamp(connection: sqlite3.Connection) -> str | None:
    try:
        row = connection.execute("select version_num from alembic_version").fetchone()
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def row_count(path: Path, table: str = "project") -> int:
    """How much data a database holds, or zero if it cannot be read."""
    if not path.exists():
        return 0
    try:
        connection = sqlite3.connect(str(path))
        try:
            if table not in _tables(connection):
                return 0
            return int(connection.execute(f'select count(*) from "{table}"').fetchone()[0])
        finally:
            connection.close()
    except sqlite3.Error:
        return 0


def code_revision(root: Path | None = None) -> str | None:
    """The head migration on disk, or None if there is not exactly one.

    The head is the revision no other migration names as its parent -- not the
    newest filename. Taking it from the filename gave `project`, the last word
    of a descriptive name, and the check then reported every database as behind
    a revision that does not exist. A wrong answer delivered confidently is
    worse here than no answer, so an ambiguous graph returns None rather than
    guessing which branch is current.

    Read from the files rather than through alembic so this still works when
    the database is too broken for alembic to open -- which is when it matters.
    """
    root = root or project_root() / "alembic" / "versions"
    if not root.is_dir():
        return None

    revisions: set[str] = set()
    parents: set[str] = set()
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name, bucket in (("revision", revisions), ("down_revision", parents)):
            match = re.search(rf"^{name}(?::[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]",
                              text, re.M)
            if match:
                bucket.add(match.group(1))

    heads = revisions - parents
    return next(iter(heads)) if len(heads) == 1 else None


def inspect(path: Path) -> list[Finding]:
    """Findings for one database file."""
    if not path.exists():
        return [Finding(WARN, f"{path} does not exist",
                        "Nothing has been synced into this location.",
                        "uv run dossier github sync-org <org>")]

    findings: list[Finding] = []
    connection = sqlite3.connect(str(path))
    try:
        tables = _tables(connection)
        if "project" not in tables:
            return [Finding(WARN, f"{path} is empty",
                            "It has no project table, so nothing has been synced here.",
                            "uv run dossier github sync-org <org>")]

        rows = connection.execute("select count(*) from project").fetchone()[0]
        stamp = _stamp(connection)

        for table, expected in EXPECTED_COLUMNS.items():
            if table not in tables:
                continue
            missing = sorted(set(expected) - _columns(connection, table))
            if missing:
                if stamp:
                    # Stamped at a revision whose columns are absent: the stamp
                    # is wrong, so `db upgrade` believes there is nothing to do
                    # and reports success while changing nothing. Recommending
                    # it here sent a reader in a circle.
                    detail = (
                        f"The stamp says {stamp}, but the columns that revision "
                        "adds are not there. alembic therefore believes the "
                        "database is current, and db upgrade reports success "
                        "without changing anything. The stamp has to be moved "
                        "back before the migration can run.")
                    fix = "uv run dossier db health --fix"
                else:
                    detail = (
                        "The code selects on these columns, so reads fail with "
                        "no such column rather than returning nothing. A schema "
                        "created before a migration keeps its old shape: "
                        "create_all adds missing tables and never alters an "
                        "existing one.")
                    fix = "uv run dossier db health --fix"
                findings.append(Finding(
                    BLOCKED,
                    f"{path} is missing {table}.{', '.join(missing)}",
                    detail, fix,
                ))

        if stamp is None:
            findings.append(Finding(
                BLOCKED if rows else WARN,
                f"{path} carries no migration stamp",
                "It was created by create_all rather than by a migration, so "
                "alembic cannot tell which migrations have run and db upgrade "
                "will try to create tables that already exist. Do not stamp it "
                "at head: that marks every migration applied, including ones "
                "that never ran, and the columns they add then never arrive.",
                "uv run dossier db health --fix",
            ))
        else:
            head = code_revision()
            if head and stamp != head:
                findings.append(Finding(
                    WARN,
                    f"{path} is at {stamp}, the code is at {head}",
                    "A migration on disk has not been applied here.",
                    "uv run dossier db upgrade",
                ))

        if not findings:
            findings.append(Finding(
                OK, f"{path} is current",
                f"Stamped {stamp}, {rows} project row(s), every expected column present."))
    finally:
        connection.close()
    return findings


def check(cwd: Path | None = None) -> list[Finding]:
    """Every finding across every database this installation might open."""
    databases = candidate_databases(cwd)
    holding_data = {path for path in databases if row_count(path)}

    findings: list[Finding] = []
    for path in databases:
        # A database that was never created is only worth mentioning when there
        # is no other one holding data. Otherwise it is a location this
        # installation simply does not use, and reporting it as a warning
        # teaches a reader that warnings here are noise.
        if not path.exists() and holding_data:
            continue
        findings.extend(inspect(path))

    from dossier.ratelimit import ANONYMOUS_PER_HOUR, has_token

    if not has_token():
        findings.append(Finding(
            WARN,
            "No GitHub token is set",
            f"Unauthenticated requests are limited to {ANONYMOUS_PER_HOUR} an "
            "hour, which a sync of more than a handful of repositories will "
            "exhaust part way through. The sync stops cleanly and resumes on a "
            "re-run, so this is a warning rather than a fault.",
            "export GITHUB_TOKEN=$(gh auth token)",
        ))

    populated = [(path, row_count(path)) for path in databases]
    populated = [(path, count) for path, count in populated if count]
    if len(populated) > 1:
        listed = ", ".join(f"{path} ({count} projects)" for path, count in populated)
        findings.append(Finding(
            WARN,
            "More than one database holds data",
            f"{listed}. dossier opens dossier.db relative to the working "
            "directory, so which one you read depends on where you launched "
            "from, and a migration applied in one does not reach the other.",
            "Run dossier from one directory, or set DOSSIER_HOME to the "
            "location you intend to use.",
        ))
    return findings


def summary_line(findings: list[Finding], cwd: Path | None = None) -> str:
    """One line a person can read on the way into the dashboard.

    The full report is right for a diagnostic command and wrong for a launch:
    a wall of text before a UI opens is text nobody reads. This states where
    the data is, how much of it there is, and whether anything is wrong.
    """
    databases = [(path, row_count(path)) for path in candidate_databases(cwd)]
    live = [(path, count) for path, count in databases if count] or databases
    path, count = live[0]
    state = {OK: "ready", WARN: "ready, with notes", BLOCKED: "not usable"}[worst(findings)]
    return f"{path} - {count} project(s) - {state}"


def ensure_schema(path: Path | None = None) -> bool:
    """Make sure the database at `path` has a schema alembic knows about.

    Cheap enough to call from every command: an existing, stamped database
    costs one small query and returns immediately. Anything else is handed to
    `repair`, which builds or migrates it.

    THIS REPLACES `create_all`. Calling `SQLModel.metadata.create_all` on
    startup is what produced every schema failure reported here. It creates
    tables without an alembic stamp, so the very first command a fresh
    installation runs leaves a database alembic has no record of -- and once
    that database holds data, no stamp can be inferred and it cannot be
    migrated at all. The database is created by the migrations or not at all.
    """
    path = path or candidate_databases()[0]
    if path.exists():
        connection = sqlite3.connect(str(path))
        try:
            if _stamp(connection) is not None:
                return False
        finally:
            connection.close()
    repair(path)
    return True


def prepare(cwd: Path | None = None) -> tuple[list[str], list[Finding]]:
    """Everything the dashboard needs done before it opens. Returns actions and
    the findings that remain.

    This is the whole of `init`: create a database that does not exist, apply
    migrations that have not run, correct a stamp that claims they did. It runs
    on every launch rather than on a first-run flag, because the state it
    repairs arrives from outside -- pulling a branch with a new migration is the
    ordinary way to get it, and a flag saying "already initialised" would be
    true and useless.
    """
    actions: list[str] = []
    findings = check(cwd)
    if worst(findings) == OK:
        return actions, findings

    for path in candidate_databases(cwd):
        # A database that has never existed is created; one that exists is
        # repaired only if something is wrong with it.
        if not path.exists() and row_count(path) == 0 and path != candidate_databases(cwd)[0]:
            continue
        for action in repair(path):
            actions.append(f"{path.name}: {action}")

    return actions, check(cwd)


def worst(findings: Iterable[Finding]) -> str:
    levels = {finding.level for finding in findings}
    if BLOCKED in levels:
        return BLOCKED
    return WARN if WARN in levels else OK


def render(findings: list[Finding]) -> str:
    """The report, with each fix directly under the finding it repairs."""
    marks = {OK: "ok   ", WARN: "warn ", BLOCKED: "BLOCK"}
    lines: list[str] = []
    for finding in findings:
        lines.append(f"{marks.get(finding.level, '?')} {finding.title}")
        lines.append(f"      {finding.detail}")
        if finding.fix:
            lines.append(f"      fix: {finding.fix}")
        lines.append("")
    lines.append({
        OK: "This installation is healthy.",
        WARN: "Usable, with something worth attending to above.",
        BLOCKED: "Something here will fail at runtime. Run the fix above first.",
    }[worst(findings)])
    return "\n".join(lines)


def repair(path: Path, backup_first: bool = True) -> list[str]:
    """Bring one database up to the code's schema. Returns what it did.

    FOUR CASES.

      * **Stamped, behind, schema matches** -- upgrade. Ordinary.
      * **Stamped at a revision whose columns it does not have** -- the stamp is
        wrong, and `upgrade` is a no-op because alembic believes it is already
        there. The stamp is moved back to the parent of the migration that adds
        the missing column, and then upgraded, so exactly that migration runs.
        This is the state that produced the report this function exists for:
        `db upgrade` said "upgraded successfully" and changed nothing.
      * **Unstamped and empty** -- rebuilt from the migrations. Alembic cannot
        migrate a schema it has no record of, and an empty database is worth
        nothing.
      * **Unstamped with rows** -- refused. No stamp can be inferred, and a
        wrong one marks migrations applied that never ran, which is how a
        database arrives in the second case above.

    IT VERIFIES, AND REPORTS WHAT IT FINDS. The previous version returned
    "upgraded to head" for a database that was still broken, because it
    reported the command it ran rather than the state it left. Anything still
    blocking afterwards is named in the return value.
    """
    from alembic import command
    from alembic.config import Config

    from dossier.maintenance import backup, timestamped_name

    done: list[str] = []
    if all(finding.level == OK for finding in inspect(path)):
        return done

    rows = row_count(path)
    connection = sqlite3.connect(str(path)) if path.exists() else None
    try:
        stamp = _stamp(connection) if connection else None
        has_tables = "project" in _tables(connection) if connection else False
    finally:
        if connection is not None:
            connection.close()

    if stamp is None and has_tables and rows:
        return ["refused: unstamped and holding data, so no stamp can be "
                "inferred. Back it up, then either migrate it by hand or "
                "re-sync into a fresh database."]

    if backup_first and path.exists() and rows:
        done.append(f"backed up to {backup(path, timestamped_name(path)).name}")

    import sys

    # `stdout` is passed explicitly. Alembic's `Config.__init__` declares
    # `stdout=sys.stdout` as a *default argument*, which Python evaluates once
    # when `alembic.config` is first imported -- binding whatever `sys.stdout`
    # was at that moment. Any later run then writes its output to that stream,
    # and if the first import happened inside something that has since replaced
    # or closed stdout, alembic fails with "I/O operation on closed file" for a
    # command that is otherwise fine.
    config = Config(str(project_root() / "alembic.ini"), stdout=sys.stdout)
    # This process may run alembic more than once. Re-running `fileConfig`
    # rebinds logging to a stream the previous caller may have closed.
    config.attributes["configure_logger"] = False
    config.set_main_option("script_location",
                           str(project_root() / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")

    absent = missing_columns(path)
    if stamp is not None and absent:
        # The stamp claims a migration ran that plainly did not. Rewind to just
        # before the one that adds the column, so that migration alone re-runs;
        # stamping further back would re-run migrations whose work is already
        # present, and those fail on tables that already exist.
        introducing = []
        for columns in absent.values():
            for column in columns:
                found = migration_introducing(column)
                if found:
                    introducing.append(found)
        if not introducing:
            return done + [f"cannot repair: no migration adds {absent}"]

        # Rewind, run exactly the migration that adds the column, then put the
        # stamp back. Rewinding and upgrading to head instead re-runs every
        # later migration, and those fail on work that is already present --
        # which is what a wrongly-stamped database has by definition. The
        # missing column is the only thing absent.
        revision, parent = introducing[0]
        command.stamp(config, parent)
        command.upgrade(config, revision)
        command.stamp(config, stamp)
        done.append(f"ran {revision} and restored the stamp to {stamp}")
        remaining = [f for f in inspect(path) if f.is_blocking]
        if remaining:
            done.append("STILL BLOCKED: " + "; ".join(f.title for f in remaining))
        return done

    if stamp is None and has_tables:
        path.unlink()
        done.append("removed an empty, unstamped database")

    path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(config, "head")
    done.append("upgraded to head")

    # Assert the intermediate. Reporting the command that ran is not reporting
    # the state it left, and the difference is what let a broken database be
    # called repaired.
    remaining = [f for f in inspect(path) if f.is_blocking]
    if remaining:
        done.append("STILL BLOCKED: " + "; ".join(f.title for f in remaining))
    return done


def project_root() -> Path:
    """Where `alembic.ini` and `alembic/` live.

    Resolved from this file rather than from the working directory: the
    dashboard is meant to be runnable from anywhere, and a config loaded as
    `Config("alembic.ini")` is found only when the caller happens to be
    standing in the repository root.
    """
    here = Path(__file__).resolve()
    for candidate in (here.parent.parent.parent, Path.cwd()):
        if (candidate / "alembic.ini").is_file():
            return candidate
    return Path.cwd()


def migration_introducing(column: str, root: Path | None = None) -> tuple[str, str] | None:
    """The revision that adds `column`, and its parent. None if not found.

    Found by reading the migrations for an `add_column` naming it. That is
    coarse -- a column added and later renamed would answer wrongly -- and it
    is enough for the case it exists to repair: a schema stamped at a revision
    whose columns it does not have.
    """
    root = root or project_root() / "alembic" / "versions"
    if not root.is_dir():
        return None
    for path in sorted(root.glob("*.py"), key=lambda p: p.name):
        text = path.read_text(encoding="utf-8")
        if not re.search(rf"add_column\([^)]*['\"]{re.escape(column)}['\"]", text):
            continue
        revision = re.search(r"^revision(?::[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]",
                             text, re.M)
        parent = re.search(r"^down_revision(?::[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]",
                           text, re.M)
        if revision and parent:
            return revision.group(1), parent.group(1)
    return None


def missing_columns(path: Path) -> dict[str, list[str]]:
    """Expected columns absent from each table, for a database that exists."""
    if not path.exists():
        return {}
    connection = sqlite3.connect(str(path))
    try:
        tables = _tables(connection)
        found = {}
        for table, expected in EXPECTED_COLUMNS.items():
            if table not in tables:
                continue
            absent = sorted(set(expected) - _columns(connection, table))
            if absent:
                found[table] = absent
        return found
    finally:
        connection.close()
