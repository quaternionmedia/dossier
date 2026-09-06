"""Putting this dossier away, and starting an empty one.

**THE FIRST-RUN PROBLEM IS THAT THERE IS NO FIRST RUN.** Somebody who has synced
the wrong owner, or been following a tutorial, or filled the database with a
hundred forks, has one route back to an empty dossier: `dossier dev reset`,
which drops every table with no backup and warns "Use with caution in
production!". That is the entire safety net, and it is a sentence in a help
text.

So this pairs the two halves that were always meant to go together. **Archive
first, then empty.** Nothing here drops a table it has not already copied.

TWO ARCHIVES, BECAUSE THEY FAIL DIFFERENTLY AND A PERSON NEEDS BOTH.

  * **The database copy is faithful and fragile.** `maintenance.backup` goes
    through SQLite's own online backup API, so every row, every id and every
    join comes back exactly. It stops being restorable the moment the schema
    moves under it, which is the ordinary case for anybody who upgrades.
  * **The exports are portable and lossy.** One `.dossier` per project through
    `dossier_file.generate_dossier`, which is the format that survives a
    migration -- and which drops everything the format has no field for.

Neither is a backup on its own. Taking both is the only combination where "I
can get this back" is true in the two ways it needs to be, and it is why the
panel takes both rather than offering a choice nobody has the information to
make at the moment they are asked.

**IT COUNTS BEFORE IT DELETES, AND THE COUNT IS THE PLAN.** `holding()` walks
the same tables `reinit()` drops, so what a person is shown is what goes. That
is `maintenance.purge_other_owners`'s rule, applied to the whole database.

WHAT THIS CANNOT DO.

  * Restore. Copying a backup back over `dossier.db` is a file operation and a
    person doing it deliberately is the point; a panel with a one-key undo for
    a destructive act is a panel that invites the act.
  * Archive what is not in the database. The harness's conversation archive is
    the harness's -- `threads.py` says so -- and emptying this dossier does not
    touch it. The reinit report says as much, because a person who has just
    emptied everything is entitled to know what they did *not* empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from sqlmodel import select

from dossier.models.schemas import (
    DeltaLink,
    DocumentSection,
    Project,
    ProjectBranch,
    ProjectComponent,
    ProjectContributor,
    ProjectDelta,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
)

# Every table `reinit` empties, in the order a reader would count them. Spelled
# out rather than taken from `SQLModel.metadata`, for the same reason
# `maintenance.CHILD_TABLES` is: a table nobody listed is a table whose rows
# vanish from a plan and not from the database.
COUNTED: tuple[Any, ...] = (
    Project,
    DocumentSection,
    ProjectComponent,
    ProjectDelta,
    DeltaLink,
    ProjectBranch,
    ProjectContributor,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
)

# What emptying this database does not reach, and who owns it instead. Reported
# after a reinit, because somebody who has just emptied everything is entitled
# to know what they did not empty.
NOT_OURS_TO_EMPTY: dict[str, str] = {
    "the conversation archive":
        "the harness holds it and serves it over the seam; this database only "
        "reads it",
    "the governance corpus":
        "a submodule checkout on this disk, read and never written",
    "clones on this disk":
        "`dossier clone` put them there and only a person takes them away",
}


@dataclass(frozen=True)
class Holding:
    """What this dossier has right now, table by table."""

    counts: dict[str, int]
    database: Path | None = None
    size: int = 0

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def projects(self) -> int:
        return self.counts.get(Project.__name__, 0)

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    def summary(self) -> str:
        """One sentence, and it always names a number.

        A reinit that reports nothing is indistinguishable from one that did
        not run -- the rule `_sync_current_view` states about the same panel.
        """
        if self.is_empty:
            return "This dossier is already empty."
        where = f" in {self.database.name}" if self.database else ""
        size = f" ({self.size:,} bytes)" if self.size else ""
        return (f"{self.projects} project(s) and {self.total:,} row(s) across "
                f"{len(self.counts)} table(s){where}{size}")


@dataclass(frozen=True)
class Archived:
    """Where the two copies went, and what each one is good for."""

    backup: Path | None = None
    """The faithful copy. None when there was no database file to copy."""

    exports: tuple[Path, ...] = ()
    """The portable copies, one per project."""

    export_dir: Path | None = None
    failures: tuple[tuple[str, str], ...] = ()
    """`(project, why)` for each export that could not be written.

    **CARRIED, NOT RAISED.** One project whose export fails is not a reason to
    refuse the archive -- the database copy is already taken and is the
    faithful one. It *is* a reason to refuse the reinit, which is the caller's
    decision and is why this is reported rather than swallowed.
    """

    @property
    def is_safe(self) -> bool:
        """Whether it is honest to empty the database after this.

        **THE FAITHFUL COPY IS THE ONE THAT DECIDES.** A missing export loses a
        portable rendering of something the backup still holds exactly; a
        missing backup loses the rows. So a failed export is reported and does
        not block, and an absent backup blocks -- unless there was no database
        file to copy, which is a dossier with nothing to lose.
        """
        return self.backup is not None

    def summary(self) -> str:
        parts = []
        if self.backup:
            parts.append(f"{self.backup.name} ({self.backup.stat().st_size:,} bytes)")
        if self.exports:
            where = self.export_dir.name if self.export_dir else "exports"
            parts.append(f"{len(self.exports)} export(s) in {where}/")
        if not parts:
            return "Nothing was archived."
        said = "Archived " + " and ".join(parts)
        if self.failures:
            said += f". {len(self.failures)} export(s) could not be written"
        return said


def holding(session: Any, database: Path | None = None) -> Holding:
    """Count every table `reinit` would empty. The plan, and it is the deletion.

    Counted with the same list the emptying walks, so a table that grew a row
    between the two readings is the only way they can disagree -- and nothing
    else is looking at this database while a person reads a confirmation.
    """
    counts: dict[str, int] = {}
    for model in COUNTED:
        try:
            counts[model.__name__] = len(session.exec(select(model)).all())
        except Exception:                          # noqa: BLE001
            # A table the current migration has not created yet is zero rows,
            # not a failed count. Reporting it as an error would make a fresh
            # checkout look broken.
            counts[model.__name__] = 0

    size = 0
    if database is not None and database.exists():
        size = database.stat().st_size
    return Holding(counts=counts, database=database, size=size)


def archive(session: Any, database: Path | None = None,
            into: Path | None = None,
            now: datetime | None = None,
            on_each: Callable[[str], None] | None = None) -> Archived:
    """Take both copies. The faithful one first, because it is the one that
    makes emptying honest.

    `into` defaults to a timestamped directory beside the database, so two
    archives taken on one day do not overwrite each other -- which is the
    failure a fixed `exports/` has and only discovers when somebody needs the
    older one.
    """
    from dossier.maintenance import backup as copy_database, timestamped_name

    stamp = (now or _utcnow()).strftime("%Y%m%dT%H%M%SZ")

    taken: Path | None = None
    if database is not None and database.exists():
        taken = timestamped_name(database, now)
        copy_database(database, taken)
        if on_each is not None:
            on_each(f"copied the database to {taken.name}")

    if into is None:
        beside = database.parent if database is not None else Path(".")
        into = beside / f"dossier-archive-{stamp}"
    into.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    failed: list[tuple[str, str]] = []
    for project in session.exec(select(Project).order_by(Project.name)).all():
        safe = project.name.replace("/", "_")
        target = into / f"{safe}.dossier"
        try:
            _write_export(session, project, target)
        except Exception as exc:                   # noqa: BLE001
            # In the words the failure used. See `Archived.failures`.
            failed.append((project.name, f"{type(exc).__name__}: {exc}"))
            continue
        written.append(target)
        if on_each is not None:
            on_each(f"exported {project.name}")

    return Archived(backup=taken, exports=tuple(written), export_dir=into,
                    failures=tuple(failed))


def _write_export(session: Any, project: Any, target: Path) -> None:
    """One project, as YAML, through the same generator `dossier export` uses."""
    import yaml

    from dossier.dossier_file import generate_dossier

    target.write_text(
        yaml.dump(generate_dossier(session, project), default_flow_style=False,
                  allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def reinit(engine: Any) -> None:
    """Drop every table and recreate them empty.

    **THE SAME TWO CALLS `dossier dev reset` MAKES**, deliberately: two ways to
    empty a database is how the two come to disagree about which tables exist.
    What is different is everything around it, which is this module.
    """
    from sqlmodel import SQLModel

    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def start_over(session: Any, engine: Any, database: Path | None = None,
               into: Path | None = None,
               on_each: Callable[[str], None] | None = None
               ) -> tuple[Holding, Archived]:
    """Archive, then empty. Returns what was there and where it went.

    **IT REFUSES TO EMPTY WHAT IT COULD NOT COPY.** `Archived.is_safe` is
    False when the database existed and the backup did not happen, and this
    raises rather than proceeding -- an archive-and-reinit whose archive half
    silently failed is a reinit, and the person asked for the other thing.
    """
    was = holding(session, database)
    put_away = archive(session, database, into=into, on_each=on_each)

    if database is not None and database.exists() and not put_away.is_safe:
        raise RuntimeError(
            f"{database} was not copied, so nothing has been emptied. "
            f"The archive has to succeed before the reinit is honest.")

    reinit(engine)
    return was, put_away


def _utcnow() -> datetime:
    from dossier.models import utcnow

    return utcnow()
