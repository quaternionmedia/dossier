"""Where the delta board and the repositories it describes disagree.

**A BOARD IS A CLAIM, AND NOTHING WAS CHECKING IT.** `maintenance.deltas_from_prs`
builds one delta per *open* pull request. Read the loop and the consequence
falls out: when a pull request merges it stops being open, so the pass that
would update its delta never sees it again. A delta enters at `review` and can
only leave if a person moves it by hand. Nobody has.

The state that produces, measured on this machine at the commit this module was
written against: **every delta in the database is `brainstorm`, `planning`,
`implementation` or `review`, and not one is `complete` or `abandoned`** — while
the `dossier` clone alone shows forty-four merged pull requests. The board says a
great deal of work is awaiting review. Almost none of it is.

THE SECOND HALF, WHICH IS WORSE THAN THE FIRST. The same loop cannot create a
delta for work that merged before a sync ran, because that work was never open
while anybody was looking. So the board is *also* missing what actually
happened: `dossier` has forty-four merged pull requests and **zero deltas**.
Noisy and incomplete at once, and no signal for either property.

WHY THIS CANNOT SIMPLY COMPARE TWO TABLES. `project_delta.phase` and
`project_pull_request.state` are both stored, both written by the same sync, and
both go stale together. Comparing them finds nothing and reports clean — an
empty query read as a good answer, which is the mistake this estate makes most
often.

So the comparison is anchored to something neither table wrote: **the git clone
on disk**. `Merge pull request #N` in the default branch's history is the host's
own record of what landed, it needs no network, and no sync produced it. If the
clone knows about pull requests the database has never heard of, the board is
behind by that much and **every other finding here is a floor rather than a
count**. `render` refuses to say "clean" while that lag is non-zero.

WHAT IT DOES NOT DO. Decide. It writes nothing; `reconcile` is a separate,
explicit act, and it moves a delta only where the evidence is mechanical.
Whether a delta is *abandoned* is a judgement about intent, and nothing here
guesses it.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from dossier.models.schemas import (
    DeltaPhase,
    Project,
    ProjectDelta,
    ProjectPullRequest,
)

# The phases that assert work is still moving. A delta in one of these whose
# pull request has merged is making a claim the repository contradicts.
IN_FLIGHT = (
    DeltaPhase.BRAINSTORM,
    DeltaPhase.PLANNING,
    DeltaPhase.IMPLEMENTATION,
    DeltaPhase.REVIEW,
)

# GitHub's own merge-commit subject. Read from the clone rather than from any
# table here: it is the one account of what landed that this application did
# not write, and every wrong answer this module could give comes from trusting
# something it did write.
MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) ")

# Accounts whose pull requests are not this organisation's units of work.
# `maintenance` already excludes forks for this reason and stops there, so a
# dependabot bump on a first-party repository becomes a delta and sits on the
# board looking exactly like somebody's feature.
AUTOMATION = ("dependabot", "app/dependabot", "github-actions")

BEHIND = "behind"
STUCK = "stuck"
ABSENT = "absent"
AUTOMATED = "automated"
UNBACKED = "unbacked"
THREAD = "thread"

WHAT_IT_MEANS = {
    BEHIND: "the clone knows pull requests this database has never seen",
    STUCK: "the delta says in flight; its pull request has already landed",
    ABSENT: "it merged, and the board never learned it happened",
    AUTOMATED: "a bot's pull request, sitting on the board as a unit of work",
    UNBACKED: "the delta names a pull request no row here describes",
    THREAD: "listed as an open thread; the clone records it merging",
}


@dataclass(frozen=True)
class Finding:
    """One disagreement, with both sides of it."""

    kind: str
    project: str
    subject: str
    detail: str


@dataclass
class Lag:
    """How far one project's board is behind the repository on disk."""

    project: str
    clone: Path | None = None
    highest_landed: int | None = None   # from the clone's history
    highest_known: int | None = None    # from this database
    deltas: int = 0

    @property
    def measurable(self) -> bool:
        """Whether a clone was found and read. Absence is not zero."""
        return self.highest_landed is not None

    @property
    def behind(self) -> int:
        """Pull requests the clone has landed that this database lacks.

        Zero when the clone could not be read, and `measurable` is what tells
        the two apart -- a project with no clone on this machine is unknown,
        never up to date.
        """
        if not self.measurable:
            return 0
        return max(0, self.highest_landed - (self.highest_known or 0))


def landed_pull_requests(clone: Path) -> set[int]:
    """Every pull request number the clone's default branch records merging.

    Reads refs, never the working tree. A shallow clone or a repository whose
    merges were squashed produces fewer numbers than really landed, so this is
    a floor -- which is the safe direction, because it can under-report lag and
    never invent it.
    """
    done = subprocess.run(
        ("git", "-C", str(clone), "log", "--format=%s", "origin/HEAD"),
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        done = subprocess.run(
            ("git", "-C", str(clone), "log", "--format=%s", "origin/main"),
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        return set()
    found = set()
    for line in done.stdout.splitlines():
        seen = MERGE_SUBJECT.match(line)
        if seen:
            found.add(int(seen.group(1)))
    return found


def survey(session: Session, clones: dict[str, Path] | None = None,
           only: str | None = None) -> tuple[list[Finding], list[Lag]]:
    """Every disagreement, and how far behind each board is.

    `clones` maps a project's short name to a checkout. A project absent from
    it is reported as unmeasurable rather than as current.

    `only` narrows to one project by its short name, and narrows **both**
    halves. Filtering the clones alone -- which is what the first version did
    -- produced a report headed by one project and followed by findings from
    thirty others, so the flag contradicted the output directly under it.
    """
    clones = clones or {}
    projects = {p.id: p for p in session.exec(select(Project)).all()}
    prs: dict[tuple[int, int], ProjectPullRequest] = {
        (pr.project_id, pr.pr_number): pr
        for pr in session.exec(select(ProjectPullRequest)).all()
    }
    deltas = list(session.exec(select(ProjectDelta)).all())

    findings: list[Finding] = []
    lags: list[Lag] = []

    by_project: dict[int, list[ProjectDelta]] = {}
    for delta in deltas:
        by_project.setdefault(delta.project_id, []).append(delta)

    for pid, project in sorted(projects.items(), key=lambda kv: kv[1].name):
        short = project.name.rsplit("/", 1)[-1]
        if only and short != only:
            continue
        mine = by_project.get(pid, [])
        lag = Lag(project=project.name, deltas=len(mine))
        known = [n for (p, n) in prs if p == pid]
        lag.highest_known = max(known, default=0)

        clone = clones.get(short) or clones.get(project.name)
        landed: set[int] = set()
        if clone is not None:
            lag.clone = clone
            landed = landed_pull_requests(clone)
            if landed:
                lag.highest_landed = max(landed)
        lags.append(lag)

        if lag.behind:
            findings.append(Finding(
                BEHIND, project.name, f"#{lag.highest_known}..#{lag.highest_landed}",
                f"the clone records #{lag.highest_landed} landing; the highest "
                f"pull request in this database is #{lag.highest_known}"))

        held = {d.pr_number for d in mine if d.pr_number}
        for number in sorted(landed - held):
            findings.append(Finding(
                ABSENT, project.name, f"pr-{number}",
                "merged in the clone's history, and no delta names it"))

        for delta in sorted(mine, key=lambda d: (d.pr_number or 0, d.name)):
            if delta.pr_number is None:
                continue
            row = prs.get((pid, delta.pr_number))
            if row is None:
                findings.append(Finding(
                    UNBACKED, project.name, delta.name,
                    f"names pull request #{delta.pr_number}, which no row here "
                    f"describes"))
                continue
            author = (row.author or "").lower()
            if any(bot in author for bot in AUTOMATION):
                findings.append(Finding(
                    AUTOMATED, project.name, delta.name,
                    f"#{row.pr_number} is {row.author}'s"))
            landed_here = bool(row.is_merged) or delta.pr_number in landed
            if landed_here and delta.phase in IN_FLIGHT:
                findings.append(Finding(
                    STUCK, project.name, delta.name,
                    f"phase {delta.phase.value}, and #{row.pr_number} merged"))

    findings.extend(stale_threads(session, clones, only))
    return findings, lags


def stale_threads(session: Session, clones: dict[str, Path],
                  only: str | None = None) -> list[Finding]:
    """Threads listed as in flight whose pull request the clone shows merging.

    **AGE IS NOT STALENESS, AND THE COUNTEREXAMPLE IS IN THE DATA.** The oldest
    thread on this machine names a pull request last touched on 2023-12-30 --
    and that pull request is genuinely still open. The two threads that were
    actually wrong were closed weeks ago and looked no different in the list.
    So nothing here judges a thread by its date; it reports only what the
    clone's history settles.

    **WHAT THIS CANNOT SEE, AND IT IS HALF THE PROBLEM.** A pull request closed
    *without* merging leaves no trace in the default branch, so the clone
    cannot report it. Both of the genuinely stale threads found by hand were
    that case. Offline, this finds only the merged half, and `render` says so
    rather than letting a short list read as a short problem.
    """
    from dossier.models.governance import GovernanceThread

    landed_by_project: dict[str, set[int]] = {}
    for short, clone in clones.items():
        landed_by_project[short] = landed_pull_requests(clone)

    found = []
    for row in session.exec(select(GovernanceThread)).all():
        short = (row.repository_name or "").rsplit("/", 1)[-1]
        if only and short != only:
            continue
        landed = landed_by_project.get(short)
        if not landed or row.pr is None:
            continue
        if row.pr in landed:
            found.append(Finding(
                THREAD, row.repository_name, row.name or f"#{row.pr}",
                f"stage {row.stage}, and #{row.pr} merged"))
    return found


def render(findings: list[Finding], lags: list[Lag]) -> str:
    """What a person reads before touching the board.

    **THE LAG IS PRINTED FIRST AND IT GOVERNS THE VERDICT.** Every other line
    is a comparison between two things this application wrote, and two stale
    tables agree with each other perfectly. A board that is behind its own
    clone cannot be called clean however few disagreements it shows, and this
    says so instead of printing a reassuring zero.
    """
    out: list[str] = []
    measurable = [lag for lag in lags if lag.measurable]
    behind = [lag for lag in measurable if lag.behind]
    blind = [lag for lag in lags if not lag.measurable and lag.deltas]

    out.append("  How far the board is behind the repositories on disk")
    if not measurable:
        out.append("      No clone could be read, so nothing here is anchored "
                   "to anything this application did not write.")
    for lag in sorted(behind, key=lambda lag: -lag.behind):
        out.append(f"      {lag.project}: {lag.behind} pull request(s) behind "
                   f"(#{lag.highest_known} known, #{lag.highest_landed} landed)"
                   f"; {lag.deltas} delta(s)")
    if measurable and not behind:
        out.append("      Every readable clone agrees with this database on "
                   "the highest pull request that landed.")
    if blind:
        out.append(f"      {len(blind)} project(s) hold deltas and have no "
                   f"clone here, so they are UNKNOWN, not current.")
    if behind or blind:
        # **PRINTED WHETHER OR NOT ANYTHING WAS FOUND**, which the first
        # version got wrong: it said this only when the finding list was empty,
        # so a stale board that happened to show a few rows read as an
        # authoritative report of a few problems. The rows below a stale
        # comparison are a floor, and that is true with or without them.
        out.append("      SO EVERY COUNT BELOW IS A FLOOR, NOT A TOTAL, and "
                   "no result here is a clean one.")
    out.append("")

    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(finding.kind, []).append(finding)

    for kind in (STUCK, THREAD, UNBACKED, ABSENT, AUTOMATED):
        rows = grouped.get(kind, [])
        if not rows:
            continue
        out.append(f"  {kind.upper()} -- {WHAT_IT_MEANS[kind]}")
        if kind in (ABSENT, AUTOMATED):
            # **BY PROJECT, NOT ONE LINE EACH.** Over a repository's whole
            # history these run to hundreds, and a flat list of them is a wall
            # that buries the four projects somebody is actually working in.
            # The per-project count is the number a person can act on.
            per: dict[str, list[Finding]] = {}
            for row in rows:
                per.setdefault(row.project, []).append(row)
            for project, group in sorted(per.items(),
                                         key=lambda kv: -len(kv[1])):
                newest = ", ".join(
                    f.subject for f in sorted(
                        group, key=lambda f: _number(f.subject), reverse=True
                    )[:4])
                out.append(f"      {project}: {len(group)}  (newest: "
                           f"{newest})")
        else:
            shown = rows[:12]
            for row in shown:
                out.append(f"      {row.project}  {row.subject}  -- "
                           f"{row.detail}")
            if len(rows) > len(shown):
                # **SAID OUT LOUD.** A truncated list that does not announce
                # its truncation is a smaller problem than the one that exists.
                out.append(f"      ... and {len(rows) - len(shown)} more not "
                           f"listed.")
        out.append("")

    if not findings:
        if behind or blind:
            out.append("  No disagreement found, AND THAT IS NOT A CLEAN "
                       "RESULT: the comparison above is behind or blind, so "
                       "this is what a stale board looks like from inside.")
        else:
            out.append("  No disagreement found, and the clones agree on what "
                       "landed.")
        out.append("")

    # **THE HALF THIS CANNOT SEE, SAID WHETHER OR NOT ANY THREAD WAS FOUND.**
    # A pull request closed without merging leaves nothing in the default
    # branch, so no offline check can find a thread that names one. Both of the
    # genuinely stale threads found by hand on this machine were exactly that,
    # and a short THREAD list would otherwise read as a small problem.
    out.append("  Threads: only the merged half is visible offline. A pull "
               "request closed WITHOUT merging leaves no trace in a clone, so "
               "a thread naming one cannot be found from here.")
    out.append("  Nothing here has been changed. `dossier deltas reconcile` "
               "moves only what the evidence settles mechanically.")
    return "\n".join(out) + "\n"


def _number(subject: str) -> int:
    """The pull request number inside a `pr-N` subject, for ordering.

    A subject that is not `pr-N` -- a hand-named delta -- sorts last rather
    than raising: this is a display order, and a crash here would take out a
    report about somebody else's rows.
    """
    found = re.search(r"(\d+)$", subject)
    return int(found.group(1)) if found else -1


@dataclass
class Move:
    """One delta this would advance, and the evidence for it."""

    delta: ProjectDelta
    to: DeltaPhase
    because: str


def reconcilable(findings: list[Finding], session: Session) -> list[Move]:
    """The findings a machine may act on, which is one of the five.

    **Only `stuck`.** A pull request that merged is a fact, and `complete` is
    the phase that fact implies, so moving it is arithmetic rather than
    judgement.

    Everything else is refused on purpose:

      * `absent` would mean *creating* a delta for work nobody chose to track,
        and a board that invents its own rows is a board nobody trusts.
      * `automated` asks whether a bot's pull request should be a unit of work
        at all. That is a policy this application does not get to set.
      * `unbacked` and `behind` are both "go and sync", not "go and edit".
    """
    wanted = {(f.project, f.subject) for f in findings if f.kind == STUCK}
    if not wanted:
        return []
    projects = {p.id: p.name for p in session.exec(select(Project)).all()}
    moves = []
    for delta in session.exec(select(ProjectDelta)).all():
        if (projects.get(delta.project_id), delta.name) in wanted:
            moves.append(Move(delta, DeltaPhase.COMPLETE,
                              f"#{delta.pr_number} merged"))
    return moves
