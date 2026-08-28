# 07 — A board that could not check itself

Everything on this page runs. It is executed by the ordinary test command, so
an example that stops being true fails the build rather than sitting here
misleading somebody.

**The problem.** `dossier deltas` shows units of work moving through phases.
Those deltas are built from *open* pull requests — so when one merges it stops
being open, the pass that would update it never sees it again, and the delta
sits at `review` until a person moves it. On the machine this was written on,
no delta in the database was `complete` or `abandoned`, and the repository this
application is named for had **forty-four merged pull requests and no deltas at
all**. The board was noisy and incomplete at once, and nothing measured either.

    >>> from dossier import drift
    >>> from dossier.models.schemas import (
    ...     DeltaPhase, Project, ProjectDelta, ProjectPullRequest)

## Two stale tables agree with each other perfectly

The obvious check compares a delta's phase against the pull request row beside
it. Both are written by the same sync and go stale together, so the comparison
finds nothing and reports clean — an empty query read as a good answer.

So the anchor is a git clone, which no sync here wrote. A real repository, with
two pull requests merged into it:

    >>> import pathlib, subprocess, tempfile
    >>> repo = pathlib.Path(tempfile.mkdtemp()) / "clone"
    >>> repo.mkdir()
    >>> def git(*args):
    ...     subprocess.run(["git", "-C", str(repo), *args], check=True,
    ...                    capture_output=True)
    >>> git("init", "-q", "-b", "main")
    >>> git("config", "user.email", "walkthrough@example.invalid")
    >>> git("config", "user.name", "Walkthrough")
    >>> _ = (repo / "f").write_text("x", encoding="utf-8")
    >>> git("add", "-A")
    >>> git("commit", "-q", "-m", "init")
    >>> for number in (1, 2, 4):
    ...     git("commit", "-q", "--allow-empty", "-m",
    ...         f"Merge pull request #{number} from quaternionmedia/b{number}")
    >>> git("update-ref", "refs/remotes/origin/main", "HEAD")

    >>> sorted(drift.landed_pull_requests(repo))
    [1, 2, 4]

`Merge pull request #N` in the default branch is the host's own record of what
landed. It needs no network and no credentials.

## A board behind its clone cannot report a clean result

A project whose tables say nothing is wrong, because they say almost nothing:

    >>> from sqlmodel import Session, SQLModel, create_engine
    >>> engine = create_engine("sqlite://")
    >>> SQLModel.metadata.create_all(engine)
    >>> session = Session(engine)
    >>> project = Project(name="quaternionmedia/thing")
    >>> session.add(project); session.commit(); session.refresh(project)

    >>> findings, lags = drift.survey(session, {"thing": repo})
    >>> lags[0].behind
    4

The clone's highest merged pull request is #4 and this database has never heard
of any of them. The report says so before it says anything else, and says what
that does to every line under it:

    >>> report = drift.render(findings, lags)
    >>> "FLOOR, NOT A TOTAL" in report
    True
    >>> "no result here is a clean one" in report
    True

## An unreadable clone is unknown, never current

    >>> _, blind = drift.survey(session, {})
    >>> blind[0].measurable
    False
    >>> blind[0].behind
    0

`behind` is zero because nothing was measured, and `measurable` is what stops
that being read as agreement. A project with no clone on this machine is not a
project that is up to date.

## What a machine may fix, and what it may not

Five kinds of disagreement are reported and exactly one may be acted on.
Here is a delta whose pull request has merged, and a delta that is a bot's:

    >>> session.add(ProjectPullRequest(
    ...     project_id=project.id, pr_number=1, title="one", state="merged",
    ...     author="peter", is_merged=True, head_branch="b1"))
    >>> stuck = ProjectDelta(project_id=project.id, name="pr-1", title="one",
    ...                      phase=DeltaPhase.REVIEW, pr_number=1)
    >>> session.add(stuck)
    >>> session.add(ProjectPullRequest(
    ...     project_id=project.id, pr_number=3, title="bump", state="open",
    ...     author="dependabot[bot]", is_merged=False, head_branch="b3"))
    >>> session.add(ProjectDelta(project_id=project.id, name="pr-3",
    ...                          title="bump", phase=DeltaPhase.REVIEW,
    ...                          pr_number=3))
    >>> session.commit()

    >>> findings, _ = drift.survey(session, {"thing": repo})
    >>> sorted({finding.kind for finding in findings})
    ['absent', 'automated', 'behind', 'stuck']

    >>> [(move.delta.name, move.to.value)
    ...  for move in drift.reconcilable(findings, session)]
    [('pr-1', 'complete')]

A merged pull request is a fact and `complete` is the phase it implies, so that
move is arithmetic. The rest are refused on purpose: `absent` would have the
board invent rows for work nobody chose to track, `automated` asks whether a
bot's pull request is a unit of work at all — a policy this application does not
get to set — and `behind` and `unbacked` both mean *go and sync*, not *go and
edit*.

Reading the findings changes nothing:

    >>> stuck.phase is DeltaPhase.REVIEW
    True
    >>> session.close()

## What this page does not claim

That reconciling makes the board true. It moves what the evidence settles and
leaves the rest, and while the board is behind its clones even that is tidying
inside a stale picture — which is why `dossier deltas reconcile` prints the lag
whether or not it moved anything.
