"""Which stores this installation is reading, and which it merely might.

**THE QUESTION THIS ANSWERS IS "WHICH DATABASE AM I LOOKING AT".** `dossier`
opens `sqlite:///dossier.db` relative to the working directory unless
`DOSSIER_DATABASE_URL` says otherwise, so which one you get depends on where you
launched from. `dossier/health.py` exists because of a run that died on a
missing column when every part of the system was right and the database being
opened was simply not the one anybody had migrated.

The settings screen used to report `dossier_home()/dossier.db` and its size --
a path the application does not necessarily open. It showed a real number about
the wrong file, which is worse than showing nothing: a reader checks it, sees a
plausible size, and stops looking.

**IN USE IS MARKED, AND THE OTHERS ARE STILL LISTED.** Listing them is half the
diagnosis. Two databases with nothing on screen saying which is live is the
state this whole module is written against, and hiding the ones that are not
live would recreate it.

THE ARCHIVE IS A SOURCE THIS SIDE DOES NOT OWN. It belongs to the harness, is
reached over HTTP, and appears here with whatever it said -- including that it
said nothing. A source that cannot be reached is a row with a reason, never an
absent row.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def human_size(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.1f} KB"
    return f"{count / (1024 * 1024):.1f} MB"


@dataclass(frozen=True)
class Source:
    """One store, and whether this installation is actually using it."""

    label: str
    where: str
    detail: str = ""
    in_use: bool = False
    present: bool = True

    @property
    def marker(self) -> str:
        """What a reader scans down the column for."""
        if self.in_use:
            return "in use"
        if not self.present:
            return "absent"
        return ""


def database_url() -> str:
    """The URL this process resolved, override included."""
    from dossier.cli import DATABASE_URL

    return DATABASE_URL


def open_database() -> Path | None:
    """The sqlite file this process is actually opening, if it is a file."""
    url = database_url()
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    return Path(url[len(prefix):]).expanduser()


def databases() -> list[Source]:
    """Every database this installation might open, the live one marked.

    Order is `health.candidate_databases`' preference order, with the one this
    process resolved marked rather than moved -- moving it would hide the
    ordering, which is the thing a person is checking when two disagree.
    """
    from dossier.health import candidate_databases

    live = open_database()
    live_resolved = live.resolve() if live else None

    found: list[Source] = []
    seen: set[Path] = set()
    for path in [p for p in ([live] if live else []) + list(candidate_databases())
                 if p is not None]:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        exists = path.is_file()
        detail = human_size(path.stat().st_size) if exists else "not created yet"
        found.append(Source(
            label="dossier database",
            where=str(path),
            detail=detail,
            in_use=(live_resolved is not None and resolved == live_resolved),
            present=exists,
        ))
    return found


def archive(base: str | None = None) -> Source:
    """The harness's thread archive, as it answered.

    Not a file this side opens. It is somebody else's store reached over the
    seam, and its row carries whatever came back -- including a refusal.
    """
    from dossier.threads import base_url, fetch

    where = base or base_url()
    state = fetch(base=where)
    if not state.reachable:
        return Source("thread archive", where, "harness not answering",
                      in_use=False, present=False)
    if not state.indexed:
        return Source("thread archive", where, "running, nothing indexed",
                      in_use=False, present=True)
    counted = state.totals.get("threads", len(state.threads))
    return Source("thread archive", where,
                  f"{counted} thread(s), indexed {state.generated_at}",
                  in_use=True, present=True)


def config_file() -> Source:
    from dossier.config import DossierConfig

    path = Path(DossierConfig.get_config_path())
    return Source("config", str(path),
                  "read" if path.is_file() else "using defaults",
                  in_use=path.is_file(), present=path.is_file())


def all_sources(include_archive: bool = True) -> list[Source]:
    """Everything this installation reads or might read, in one list.

    `include_archive` exists because reaching the harness is a network call with
    a timeout, and a caller drawing a settings screen may not want to wait for
    it. The default is to ask: a source silently omitted is the failure this
    module is about.
    """
    found = databases()
    found.append(config_file())
    if include_archive:
        found.append(archive())
    return found
