"""Repositories this database knows about and this disk does not have.

**EIGHTY-SIX OF A HUNDRED AND FIFTEEN, MEASURED ON 2026-08-25.** Every facet that
reads a clone -- branch hygiene, and anything asking what would be lost if this
disk died -- reports `unknown` for all of them. That is the honest answer and it
is not a useful one, and the gap between "indexed" and "on this machine" was
something a person could only close by hand, one `git clone` at a time.

**WHAT IS ABSENT IS NOT WHAT IS MISSING.** A repository with no clone here is a
repository nobody needed on this machine, which is an ordinary state and usually
the right one. So nothing here decides to clone anything: it reports what is
absent and clones exactly what it is told to, and the caller is where the
deciding happens.

WHAT IT COSTS, WHICH IS WHY IT ASKS. A clone is a network fetch and a write to
somebody's disk, and eighty-six of them is neither quick nor small. Both the
command and the panel list first and act second.

WHAT THIS CANNOT DO. Know whether you have the right to clone something.
Authentication is git's, and a private repository this database learned about
through an authenticated sync will still refuse at the network if the machine
running the clone has no credentials -- so the refusal is reported as git worded
it rather than translated into a guess about why.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# **ONE ANSWER TO 'WHICH REPOSITORY IS THIS ROW ABOUT'.** This
# module had its own, and the overview's attention list had a
# different one -- so a delta address was skipped here and
# recommended for syncing there, from the same four rows.
from dossier.naming import repository_of

# What a clone that has not been attempted reports. Never `False`: not yet
# tried and tried-and-failed are different states, and one of them is nobody's
# fault.
NOT_TRIED = "not tried"
CLONED = "cloned"
REFUSED = "refused"
FAILED = "failed"


@dataclass(frozen=True)
class Absent:
    """One repository the database holds and this machine does not."""

    repo: str
    """`owner/name`, as the database has it."""

    name: str
    """The bare directory name a clone would land in."""

    url: str
    """Where it would be cloned from, or empty when nothing recorded one."""

    into: Path
    """The path it would occupy."""

    @property
    def can_be_cloned(self) -> bool:
        return bool(self.url)


@dataclass(frozen=True)
class Outcome:
    """What happened to one clone, in the words the tool used.

    Carries `detail` verbatim rather than a category. A repository that does
    not exist, one the machine has no credentials for, and one whose disk is
    full all fail, and only git can say which -- translating that into a guess
    is how a person ends up debugging the wrong thing.
    """

    absent: Absent
    state: str = NOT_TRIED
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.state == CLONED


def absent(projects: Iterable[Any], roots: Sequence[Path] | None = None,
           into: Path | None = None,
           find: Callable[..., Path | None] | None = None
           ) -> tuple[Absent, ...]:
    """Every project with no clone under `roots`.

    `find` is `branches.find_clone` by default -- the same rule every other
    reading of a clone uses, so "absent here" means the same thing in the
    hygiene facet and in this command. Two definitions of where a repository
    lives is how one of them starts reporting a repository as missing while
    the other reads it happily.
    """
    if find is None:
        from dossier.branches import find_clone as find

    if into is None:
        from dossier.branches import _here

        into = _here().parent

    found = []
    seen: set[str] = set()
    for project in projects:
        repo, name = repository_of(project)
        if not name:
            # Nothing here says which repository this row belongs to, so
            # there is nothing to look for and nothing to clone. Skipped
            # rather than guessed at.
            continue
        if repo in seen:
            # Several rows can name one repository -- a delta address and the
            # repository itself -- and one repository is absent once.
            continue
        seen.add(repo)
        if find(name, list(roots) if roots else None):
            continue
        found.append(Absent(repo=repo, name=name,
                            url=getattr(project, "github_url", "") or "",
                            into=Path(into) / name))
    return tuple(found)


def clone(one: Absent, run: Callable[..., Any] = subprocess.run,
          depth: int | None = None) -> Outcome:
    """Clone one repository, or say why not.

    **REFUSES BEFORE IT RUNS RATHER THAN AFTER.** A destination that already
    exists is the case that matters: git would fail on it anyway, and the
    difference between "there is already something here" and whatever git says
    about a non-empty directory is the difference between a person knowing they
    already have it and a person reading a stack of network errors.
    """
    if not one.can_be_cloned:
        return Outcome(one, REFUSED, "nothing recorded a URL for it")
    if one.into.exists():
        return Outcome(one, REFUSED, f"{one.into} is already there")
    if shutil.which("git") is None:
        return Outcome(one, REFUSED, "no git on this machine")

    argv = ["git", "clone"]
    if depth:
        # A shallow clone is a different artifact, so it is asked for and never
        # assumed: branch hygiene counts commits no remote has, and a shallow
        # clone cannot answer that question at all.
        argv += ["--depth", str(depth)]
    argv += [one.url, str(one.into)]

    try:
        done = run(argv, capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    except Exception as error:                    # noqa: BLE001
        return Outcome(one, FAILED, f"{type(error).__name__}: {error}")

    if getattr(done, "returncode", 1) == 0:
        return Outcome(one, CLONED, str(one.into))
    said = (getattr(done, "stderr", "") or getattr(done, "stdout", "") or "")
    return Outcome(one, FAILED, said.strip().splitlines()[-1] if said.strip()
                   else f"git exited {done.returncode}")


def summarise(outcomes: Sequence[Outcome]) -> str:
    """One line. Counts every state, including the ones that did nothing.

    A summary naming only what succeeded reads as everything having been tried.
    """
    if not outcomes:
        return "nothing to clone"
    tally: dict[str, int] = {}
    for outcome in outcomes:
        tally[outcome.state] = tally.get(outcome.state, 0) + 1
    return ", ".join(f"{count} {state}" for state, count in sorted(tally.items()))
