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
    for path in (cwd / "dossier.db", dossier_home() / "dossier.db"):
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            found.append(path)
    return found


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
    root = root or Path("alembic/versions")
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
                findings.append(Finding(
                    BLOCKED,
                    f"{path} is missing {table}.{', '.join(missing)}",
                    "The code selects on these columns, so reads fail with "
                    "no such column rather than returning nothing. A schema "
                    "created before a migration keeps its old shape: create_all "
                    "adds missing tables and never alters an existing one.",
                    "uv run dossier db upgrade" if stamp
                    else "uv run dossier db stamp head, then uv run dossier db upgrade",
                ))

        if stamp is None:
            findings.append(Finding(
                BLOCKED if rows else WARN,
                f"{path} carries no migration stamp",
                "It was created by create_all rather than by a migration, so "
                "alembic cannot tell which migrations have run and db upgrade "
                "will try to create tables that already exist.",
                "uv run dossier db stamp head",
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
    findings: list[Finding] = []
    for path in databases:
        findings.extend(inspect(path))

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

    THREE CASES, AND ONE OF THEM IS REFUSED.

      * **Stamped and behind** -- upgrade to head. Ordinary.
      * **Unstamped and empty** -- rebuild. Alembic cannot migrate a schema it
        has no record of: running from base tries to create tables that already
        exist and fails on the first one. An empty database is worth nothing, so
        the file is replaced by one built from the migrations.
      * **Unstamped with rows** -- refused. There is no way to tell which
        migrations that schema has already had, so any stamp is a guess, and a
        wrong guess marks migrations applied that never ran. The columns they
        would have added then never arrive, and the failure resurfaces later
        looking like a different bug. This returns without touching it and the
        finding says so.

    A backup is taken before anything is written. The one thing worse than a
    stale database is a half-migrated one with no copy of what it used to be.
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
        stamped = _stamp(connection) is not None if connection else False
        has_tables = "project" in _tables(connection) if connection else False
    finally:
        if connection is not None:
            connection.close()

    if not stamped and has_tables and rows:
        done.append(
            "refused: unstamped and holding data, so no stamp can be inferred. "
            "Back it up, then either migrate it by hand or re-sync into a fresh "
            "database.")
        return done

    if backup_first and path.exists() and rows:
        done.append(f"backed up to {backup(path, timestamped_name(path)).name}")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")

    if not stamped and has_tables:
        # Empty and unstamped: replace it rather than migrate it. Nothing is
        # lost, and it is the only route that ends at a schema alembic knows.
        path.unlink()
        done.append("removed an empty, unstamped database")

    path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(config, "head")
    done.append("built to head" if not stamped else "upgraded to head")
    return done
