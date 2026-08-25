"""Local branches whose work is already in the default branch, and nothing else.

    dossier trim <repo>             what a trim would remove. Removes nothing
    dossier trim <repo> --delete    remove them

**LISTING IS THE DEFAULT AND DELETING IS ASKED FOR**, the same shape as
`dossier.clone` and for the mirrored reason: a clone writes to somebody's disk
and this removes from it. A dry run is not a mode here, it is what the command
does unless told otherwise.

**"MERGED" MEANS ONE THING AND IT IS STATED.** A branch is trimmable when its
tip is an ancestor of the default branch's *remote* ref -- `git branch --merged
origin/main`. Every commit on it is therefore already in `origin/main`, so
removing the label removes no commit. That is the only definition used, and it
is checkable by hand on any branch this reports.

**THE BLIND SPOT, AND WHICH WAY IT FAILS.** A branch that reached `main` by
squash or rebase has no ancestry link to it: its commits were rewritten, so it
is *not* `--merged` and this leaves it alone. The sweep therefore under-removes,
which is the safe direction, and it means **"nothing to trim" is not "no branch
here is spent."** Those branches are not silently dropped from the report --
they are listed under `not established`, because a sweep that quietly omitted
its own blind spot would read as a clean bill of health.

`branches.py` records the same fact from the other side: it counts commits, not
changes, so a branch whose work reached `main` by another route is reported at
risk. Three branches in `codecartographer` read that way on 2026-08-23 and all
three were in fact spent. This module inherits that limit rather than solving
it, and neither module will delete on a guess.

**IT NEVER TOUCHES A REMOTE.** Local refs only. Deleting a remote branch takes
it from everybody who fetches, which is a different act with a different blast
radius, and it is not this one. A trimmed branch that still exists on `origin`
is a branch anybody can fetch back.

**AND IT PRINTS THE WAY BACK.** Every removal is reported with the commit the
branch pointed at, because `git branch -D` is only recoverable if somebody
wrote the hash down before it scrolled away.

WHAT THIS CANNOT DO. Decide whether an unmerged branch is wanted. Read a
repository it has no clone of. Or know that a branch was merged somewhere other
than the default branch of this clone -- a branch merged into a release line
this clone does not track reads as unmerged here, and that is honest rather
than complete.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from dossier.branches import (AUTOMATION_PREFIXES, PERMANENT_EXACT,
                              PERMANENT_PREFIXES, unique_commits)

# Why a branch was kept. Stated per branch rather than inferred from a class,
# because "why is this one still here" is the question somebody reading a trim
# actually has.
CHECKED_OUT = "checked out here"
PERMANENT = "never deleted; a downstream submodule may pin it"
UNIQUE = "carries commit(s) no remote has"
UNMERGED = "not an ancestor of the default branch"

# The branch is not an ancestor and its remote counterpart is gone. Most often a
# squash or rebase merge whose pull request deleted the branch -- and sometimes
# a branch somebody removed from the remote without merging it. **The two are
# indistinguishable from here**, so this is a report and never a removal.
UNESTABLISHED = "upstream gone, but not an ancestor: check before removing"


@dataclass(frozen=True)
class Branch:
    """One local branch, and what a trim would do about it."""

    name: str
    tip: str
    """The commit it points at. Carried so a removal can be undone."""

    trimmable: bool
    why: str
    """Why it is kept, or how being trimmable was established."""

    unique: int = 0
    """Commits this clone holds that no remote does. Zero for a merged branch,
    by definition -- kept as a field because a reader checking the claim wants
    the number rather than the assurance."""

    upstream_gone: bool = False
    automation: bool = False

    @property
    def unestablished(self) -> bool:
        return not self.trimmable and self.why == UNESTABLISHED


@dataclass(frozen=True)
class Plan:
    """What a trim of one clone would remove, before anything is removed."""

    repo: str
    path: str = ""
    default: str = ""
    """The ref `merged` was measured against. Named because the answer depends
    on it entirely."""

    branches: tuple[Branch, ...] = ()
    reason: str = ""
    """Why no plan could be made. Empty when one was."""

    @property
    def readable(self) -> bool:
        return not self.reason

    @property
    def trimmable(self) -> tuple[Branch, ...]:
        return tuple(b for b in self.branches if b.trimmable)

    @property
    def kept(self) -> tuple[Branch, ...]:
        return tuple(b for b in self.branches if not b.trimmable)

    @property
    def unestablished(self) -> tuple[Branch, ...]:
        """The blind spot, named. Never removed."""
        return tuple(b for b in self.branches if b.unestablished)


@dataclass(frozen=True)
class Removal:
    """One branch this actually removed, or refused to."""

    name: str
    tip: str
    removed: bool
    detail: str = ""

    @property
    def restore(self) -> str:
        return f"git branch {self.name} {self.tip}"


def _git(repo: Path, *args: str) -> tuple[int, str, str]:
    """Run one git command. The status is returned rather than swallowed.

    `branches.py`'s `_git` returns `""` on failure, which is right for a survey
    that would rather report nothing than raise. It is wrong here: a delete that
    failed and reported an empty string would be a removal nobody performed and
    nobody heard about.
    """
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def _read(repo: Path, *args: str) -> str:
    return _git(repo, *args)[1]


def default_ref(repo: Path) -> str:
    """The remote ref to measure against, or `""` if there is none.

    A remote ref rather than a local one on purpose: local `main` can be behind,
    and a branch measured against a stale `main` reads as unmerged. The same
    choice `branches.survey` makes.
    """
    for candidate in ("origin/main", "origin/master"):
        if _read(repo, "rev-parse", "--verify", "--quiet", candidate):
            return candidate
    return ""


def _current(repo: Path) -> str:
    """The checked-out branch, or `""` in a detached head."""
    return _read(repo, "symbolic-ref", "--quiet", "--short", "HEAD")


def _gone(repo: Path) -> set[str]:
    """Branches whose upstream no longer exists on the remote.

    Read from `%(upstream:track)`, which reports `[gone]` for exactly this. It
    is evidence about the blind spot and never a reason to delete: a remote
    branch is deleted when a pull request merges, and also when somebody
    abandons one.
    """
    listed = _read(repo, "for-each-ref", "--format=%(refname:short)\t%(upstream:track)",
                   "refs/heads")
    found = set()
    for line in listed.splitlines():
        name, _, track = line.partition("\t")
        if "gone" in track:
            found.add(name.strip())
    return found


def plan(repo_name: str, path: Path | str | None) -> Plan:
    """What a trim of this clone would remove. Removes nothing.

    Every branch is reported, kept ones included and with their reason, because
    a list of what will be deleted is only checkable beside the list of what
    will not.
    """
    if path is None:
        return Plan(repo_name, reason="no clone on this machine")
    repo = Path(path)
    if not (repo / ".git").exists():
        return Plan(repo_name, path=str(repo),
                    reason="not a git clone at that path")

    default = default_ref(repo)
    if not default:
        return Plan(repo_name, path=str(repo),
                    reason="no origin/main or origin/master to measure against")

    merged = {line.strip() for line
              in _read(repo, "branch", "--merged", default,
                       "--format=%(refname:short)").splitlines() if line.strip()}
    every = [r.strip() for r
             in _read(repo, "for-each-ref", "--format=%(refname)",
                      "refs/heads", "refs/remotes").splitlines()
             if r.strip() and not r.endswith("/HEAD")]
    gone = _gone(repo)
    here = _current(repo)

    found = []
    for line in _read(repo, "for-each-ref",
                      "--format=%(refname:short)\t%(objectname:short)",
                      "refs/heads").splitlines():
        name, _, tip = line.partition("\t")
        name, tip = name.strip(), tip.strip()
        if not name:
            continue
        automation = name.startswith(AUTOMATION_PREFIXES)

        # Order matters, and it is the order of how much is at stake. A branch
        # that is checked out cannot be removed whatever else is true of it; a
        # permanent one must not be even when it is merged.
        if name in PERMANENT_EXACT or name.startswith(PERMANENT_PREFIXES):
            why, trimmable = PERMANENT, False
        elif name == here:
            why, trimmable = CHECKED_OUT, False
        elif name in merged:
            why, trimmable = f"ancestor of {default}", True
        elif name in gone:
            why, trimmable = UNESTABLISHED, False
        else:
            why, trimmable = UNMERGED, False

        found.append(Branch(
            name=name, tip=tip, trimmable=trimmable, why=why,
            # Counted only where it can change the reading. A merged branch has
            # none by definition and asking git per branch is the cost
            # `branches.merged_refs` exists to avoid.
            unique=0 if trimmable else unique_commits(
                repo, f"refs/heads/{name}", every),
            upstream_gone=name in gone, automation=automation))

    return Plan(repo_name, path=str(repo), default=default,
                branches=tuple(sorted(found, key=lambda b: b.name)))


def execute(plan_: Plan, only: tuple[str, ...] = ()) -> list[Removal]:
    """Remove the trimmable branches. **Called only by a caller that meant it.**

    `only` narrows to named branches; empty means every trimmable one. Nothing
    outside `plan_.trimmable` is ever passed to git, so a caller cannot widen
    this by naming a branch the plan kept -- the plan is the authority and this
    is the hands.

    A branch git refuses to delete is reported as refused with git's own words,
    not translated into a guess about why.
    """
    if not plan_.readable:
        return []
    repo = Path(plan_.path)
    wanted = [b for b in plan_.trimmable if not only or b.name in only]

    done = []
    for branch in wanted:
        # `-d`, not `-D`. Lowercase refuses anything not merged, so git checks
        # the claim this module made rather than being told to trust it. A
        # disagreement between the two is a bug here and shows up as a refusal
        # rather than as a deletion.
        status, _, error = _git(repo, "branch", "-d", branch.name)
        done.append(Removal(name=branch.name, tip=branch.tip,
                            removed=status == 0,
                            detail="" if status == 0 else error))
    return done


def _prospective(plan_: Plan) -> list[Removal]:
    """What `execute` would report if every trimmable branch went.

    Used to name the delta in a dry run. Built from the plan rather than
    guessed at, so the preview and the run agree by construction.
    """
    return [Removal(name=b.name, tip=b.tip, removed=True)
            for b in plan_.trimmable]


def delta_name(removals: list[Removal]) -> str:
    """A stable name for the delta one trim produces.

    **CONTENT-ADDRESSED, SO THE SAME TRIM IS THE SAME DELTA.** Named from what
    was removed rather than from a clock or a counter: re-running a trim that
    removed the same branches names the same work, and a different trim names
    different work. Nothing here needs the time to be reproducible.
    """
    import hashlib

    subject = "\n".join(sorted(f"{r.name}@{r.tip}" for r in removals if r.removed))
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    return f"trim-{digest[:12]}"


def as_delta(plan_: Plan, removals: list[Removal]) -> dict[str, str]:
    """One trim as the fields of a delta. **Writes nothing.**

    `dossier.sweep` states the rule this follows: a sweep is one delta rather
    than a pile of similar jobs, so a trim of eighteen branches is one unit of
    work with eighteen parts and closing it means all of them.

    **THE DESCRIPTION CARRIES THE WAY BACK.** `git branch -D` is recoverable
    only from a hash somebody kept, and a terminal scrolls. Putting the restore
    commands in the delta is the difference between a removal that can be
    undone next week and one that can be undone until the window closes.

    The caller owns the database. This returns fields, so the module that knows
    git does not also need to know a session.
    """
    gone_now = [r for r in removals if r.removed]
    lines = [f"Trimmed from {plan_.path}, measured against {plan_.default}.",
             "",
             "A branch below was an ancestor of that ref, so every commit on "
             "it was already there and removing the label removed no commit.",
             "",
             "Restore any of them with the command beside it:", ""]
    lines += [f"  {r.restore}" for r in gone_now]
    if plan_.unestablished:
        lines += ["",
                  "Left alone, because being merged could not be established "
                  "from this clone -- most often a squash or rebase merge, "
                  "sometimes an abandoned branch:", ""]
        lines += [f"  {b.name}  ({b.tip})" for b in plan_.unestablished]

    return {
        "name": delta_name(removals),
        "title": f"Trim {len(gone_now)} merged branch(es) from {plan_.repo}",
        "description": "\n".join(lines),
        "delta_type": "chore",
    }


def render(plan_: Plan, removals: list[Removal] | None = None) -> str:
    """The plan, for a person deciding whether to run it."""
    if not plan_.readable:
        return f"  {plan_.repo}: {plan_.reason}"

    lines = [f"  {plan_.repo}  ({plan_.path})",
             f"  merged measured against {plan_.default}", ""]

    if plan_.trimmable:
        lines.append(f"  {len(plan_.trimmable)} branch(es) can be trimmed:")
        for branch in plan_.trimmable:
            mark = "  [bot]" if branch.automation else ""
            lines.append(f"    {branch.tip}  {branch.name}{mark}")
        lines.append("")
    else:
        lines.append("  Nothing is trimmable. That is not the same as nothing "
                     "being spent -- see below.")
        lines.append("")

    if plan_.unestablished:
        lines.append(f"  {len(plan_.unestablished)} branch(es) have no remote "
                     f"and are not ancestors. **Not trimmed.**")
        lines.append("    Most often a squash or rebase merge; sometimes a "
                     "branch abandoned. Indistinguishable from here.")
        for branch in plan_.unestablished:
            lines.append(f"    {branch.tip}  {branch.name}"
                         f"   ({branch.unique} commit(s) no remote has)")
        lines.append("")

    other = [b for b in plan_.kept if not b.unestablished]
    if other:
        lines.append(f"  {len(other)} kept:")
        for branch in other:
            lines.append(f"    {branch.tip}  {branch.name:<44} {branch.why}")
        lines.append("")

    if removals is None:
        if plan_.trimmable:
            # **THE NAME IS THE SAME ONE THE REAL RUN WILL USE**, because it is
            # computed from what would be removed and that set is this list. A
            # preview that named a different delta than the run produces would
            # be worse than naming none.
            lines.append(f"  Would be recorded as one delta: "
                         f"{delta_name(_prospective(plan_))}")
        lines.append("  Nothing was removed. Pass --delete to remove the "
                     "trimmable branches.")
        lines.append("  No remote branch is touched by this command, with or "
                     "without --delete.")
        return "\n".join(lines)

    gone_now = [r for r in removals if r.removed]
    refused = [r for r in removals if not r.removed]
    lines.append(f"  Removed {len(gone_now)} of {len(removals)}.")
    for removal in gone_now:
        lines.append(f"    {removal.name}  ->  restore with: {removal.restore}")
    for removal in refused:
        lines.append(f"    REFUSED {removal.name}: {removal.detail}")
    return "\n".join(lines)
