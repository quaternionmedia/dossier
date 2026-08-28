"""What a board must not be able to say about itself.

**THE DEFECT THIS IS WRITTEN AGAINST.** `maintenance.deltas_from_prs` builds one
delta per *open* pull request. When a pull request merges it stops being open,
so the pass that would update its delta never sees it again: a delta enters at
`review` and can only leave if a person moves it. Measured on the machine this
was written on, not one delta in the database was `complete` or `abandoned`,
while the `dossier` clone alone showed forty-four merged pull requests and
`dossier` had **no deltas at all**. Noisy and incomplete at once.

**AND THE TRAP UNDERNEATH IT.** `project_delta.phase` and
`project_pull_request.state` are both written by the same sync and go stale
together, so comparing them finds nothing and reports clean. That is an empty
query read as a good answer, which is the mistake this estate makes most often
and the reason `test_a_stale_board_is_not_reported_as_clean` exists.

So the comparison is anchored to the git clone -- `Merge pull request #N` in the
default branch, written by the host and by no sync here.

THE MUTATIONS, per P16, quoted as they printed.

  the lag ignored, so a board behind its clone reads clean

    AssertionError: a board 3 pull requests behind its clone reported a clean
    result

  `reconcilable` acting on every finding rather than only STUCK

    AssertionError: reconcile offered to act on ['absent', 'automated',
    'unbacked']
    assert ['pr-1', 'pr-2', 'pr-98'] == ['pr-1']

  the phase check dropped, so a merged pull request is not stuck

    AssertionError: a merged pull request left its delta in review
    assert [] != []

  `Lag.measurable` forced True, so a project with no clone reads as current

    4 failed, 9 passed

  the thread check keyed on having a pull request rather than on it merging

    AssertionError: assert [Finding(kind...#113 merged')] == []

AND ONE INERT MUTATION, recorded because it looked like a passing guard.
Rewriting `behind`'s early return as `return 0 if False else 0` changed
nothing and the suite stayed green -- it is a no-op, not evidence. The property
these tests actually rest on is `measurable`, and forcing it True is what shows
them working. A mutation that does not change behaviour proves nothing about
the test, and this session produced three of them before noticing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier import drift
from dossier.models.schemas import (
    DeltaPhase,
    Project,
    ProjectDelta,
    ProjectPullRequest,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def a_project(session, name="quaternionmedia/thing") -> Project:
    row = Project(name=name)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def a_pr(session, project, number, *, merged=False, state="open",
         author="peter") -> ProjectPullRequest:
    row = ProjectPullRequest(
        project_id=project.id, pr_number=number, title=f"pr {number}",
        state=state, author=author, is_merged=merged, head_branch=f"b{number}")
    session.add(row)
    session.commit()
    return row


def a_delta(session, project, number, phase=DeltaPhase.REVIEW) -> ProjectDelta:
    row = ProjectDelta(project_id=project.id, name=f"pr-{number}",
                       title=f"pr {number}", phase=phase, pr_number=number)
    session.add(row)
    session.commit()
    return row


def a_clone(tmp_path: Path, merged: list[int]) -> Path:
    """A repository whose history records those pull requests merging.

    A real repository with real merge commits, not a stub: the whole anchor is
    that this is the one account of what landed that the application did not
    write, and a fake one would be the application writing it again.
    """
    repo = tmp_path / "clone"
    repo.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True,
                                    capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "T")
    (repo / "f").write_text("x", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", "init")
    for number in merged:
        run("commit", "-q", "--allow-empty", "-m",
            f"Merge pull request #{number} from quaternionmedia/b{number}")
    run("update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


# --- the anchor -------------------------------------------------------------


def test_the_landed_numbers_come_from_the_clone_not_the_database(tmp_path):
    assert drift.landed_pull_requests(a_clone(tmp_path, [2, 7, 9])) == {2, 7, 9}


def test_an_unreadable_clone_yields_nothing_rather_than_raising(tmp_path):
    """A directory that is not a repository is not a repository with no
    merges, and the difference is `Lag.measurable`."""
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    assert drift.landed_pull_requests(empty) == set()


# --- the verdict, which is the point ---------------------------------------


def test_a_stale_board_is_not_reported_as_clean(session, tmp_path):
    """**THE ONE THAT MATTERS.**

    Both stored tables agree, so nothing disagrees and the naive answer is
    "clean". The clone knows about three pull requests neither table has heard
    of, so the board is behind and the absence of findings means nothing.
    """
    project = a_project(session)
    clone = a_clone(tmp_path, [1, 2, 3])

    findings, lags = drift.survey(session, {"thing": clone})
    text = drift.render(findings, lags)

    assert lags[0].behind == 3
    assert "FLOOR, NOT A TOTAL" in text, (
        "a board 3 pull requests behind its clone reported a clean result")
    assert "no result here is a clean one" in text


def test_a_project_with_no_clone_is_unknown_rather_than_current(session):
    project = a_project(session)
    a_delta(session, project, 1)

    findings, lags = drift.survey(session, {})

    assert lags[0].measurable is False
    assert lags[0].behind == 0, "unmeasurable must not be reported as behind"
    assert "UNKNOWN, not current" in drift.render(findings, lags)


def test_an_agreeing_board_with_a_readable_clone_says_so(session, tmp_path):
    """The other side of the verdict: a real clean result must be sayable, or
    the check is just an alarm that never stops."""
    project = a_project(session)
    a_pr(session, project, 1, merged=True, state="merged")
    a_delta(session, project, 1, phase=DeltaPhase.COMPLETE)

    findings, lags = drift.survey(session, {"thing": a_clone(tmp_path, [1])})
    text = drift.render(findings, lags)

    assert lags[0].behind == 0
    assert "FLOOR, NOT A TOTAL" not in text
    assert "clones agree on what landed" in text


# --- the four findings ------------------------------------------------------


def test_a_delta_in_flight_whose_pull_request_merged_is_stuck(session,
                                                              tmp_path):
    project = a_project(session)
    a_pr(session, project, 1, merged=True, state="merged")
    a_delta(session, project, 1, phase=DeltaPhase.REVIEW)

    findings, _ = drift.survey(session, {"thing": a_clone(tmp_path, [1])})

    stuck = [f for f in findings if f.kind == drift.STUCK]
    assert stuck != [], "a merged pull request left its delta in review"
    assert "review" in stuck[0].detail


def test_a_delta_already_complete_is_not_stuck(session, tmp_path):
    project = a_project(session)
    a_pr(session, project, 1, merged=True, state="merged")
    a_delta(session, project, 1, phase=DeltaPhase.COMPLETE)

    findings, _ = drift.survey(session, {"thing": a_clone(tmp_path, [1])})

    assert [f for f in findings if f.kind == drift.STUCK] == []


def test_work_that_merged_with_no_delta_is_absent(session, tmp_path):
    project = a_project(session)

    findings, _ = drift.survey(session, {"thing": a_clone(tmp_path, [4])})

    absent = [f for f in findings if f.kind == drift.ABSENT]
    assert [f.subject for f in absent] == ["pr-4"]


def test_a_bots_pull_request_on_the_board_is_named(session, tmp_path):
    """`maintenance` excludes forks for this reason and stops there, so a
    dependabot bump on a first-party repository becomes a unit of work."""
    project = a_project(session)
    a_pr(session, project, 1, author="dependabot[bot]")
    a_delta(session, project, 1)

    findings, _ = drift.survey(session, {"thing": a_clone(tmp_path, [])})

    assert [f.kind for f in findings if f.kind == drift.AUTOMATED] == [
        drift.AUTOMATED]


def test_a_delta_naming_a_pull_request_no_row_describes_is_unbacked(session,
                                                                    tmp_path):
    project = a_project(session)
    a_delta(session, project, 99)

    findings, _ = drift.survey(session, {"thing": a_clone(tmp_path, [])})

    unbacked = [f for f in findings if f.kind == drift.UNBACKED]
    assert unbacked and "#99" in unbacked[0].detail


# --- what may be acted on ---------------------------------------------------


def test_reconcile_offers_only_the_mechanically_settled(session, tmp_path):
    """Four of the five findings are refused, and each for its own reason.

    `absent` would have the board invent rows for work nobody chose to track;
    `automated` is a policy about what counts as work; `unbacked` and `behind`
    both mean "go and sync", not "go and edit".
    """
    project = a_project(session)
    a_pr(session, project, 1, merged=True, state="merged")
    a_delta(session, project, 1, phase=DeltaPhase.REVIEW)     # stuck
    a_pr(session, project, 2, author="dependabot[bot]")
    a_delta(session, project, 2)                              # automated
    a_delta(session, project, 98)                             # unbacked
    clone = a_clone(tmp_path, [1, 3])                         # 3 is absent

    findings, _ = drift.survey(session, {"thing": clone})
    kinds = {f.kind for f in findings}
    assert {drift.STUCK, drift.ABSENT, drift.AUTOMATED, drift.UNBACKED} <= kinds

    moves = drift.reconcilable(findings, session)

    assert [m.delta.name for m in moves] == ["pr-1"], (
        f"reconcile offered to act on "
        f"{sorted(kinds - {drift.STUCK, drift.BEHIND})}")
    assert moves[0].to == DeltaPhase.COMPLETE


def test_reconcile_writes_nothing_by_itself(session, tmp_path):
    """It returns moves. Applying them is the caller's separate act, so a
    reader of this function cannot accidentally change the board."""
    project = a_project(session)
    a_pr(session, project, 1, merged=True, state="merged")
    delta = a_delta(session, project, 1, phase=DeltaPhase.REVIEW)

    findings, _ = drift.survey(session, {"thing": a_clone(tmp_path, [1])})
    drift.reconcilable(findings, session)

    assert delta.phase == DeltaPhase.REVIEW


# --- threads ----------------------------------------------------------------


def a_thread(session, repository, number, *, stage="ready", name=None):
    from dossier.models.governance import GovernanceThread

    row = GovernanceThread(repository_name=repository, name=name or f"b{number}",
                           stage=stage, pr=number)
    session.add(row)
    session.commit()
    return row


def test_a_thread_whose_pull_request_merged_is_reported(session, tmp_path):
    a_thread(session, "thing", 12)

    findings = drift.stale_threads(session, {"thing": a_clone(tmp_path, [12])})

    assert [f.kind for f in findings] == [drift.THREAD]
    assert "#12 merged" in findings[0].detail


def test_a_thread_is_never_judged_by_its_age(session, tmp_path):
    """**THE COUNTEREXAMPLE IS REAL AND IT IS IN THE DATA.**

    The oldest thread on the machine this was written on names a pull request
    last touched on 2023-12-30, and that pull request is genuinely still open.
    The two threads that were actually wrong had closed weeks earlier. A rule
    keyed on age would have flagged the correct one and missed both.
    """
    a_thread(session, "thing", 113)

    assert drift.stale_threads(session, {"thing": a_clone(tmp_path, [1])}) == []


def test_a_thread_with_no_clone_is_not_reported(session, tmp_path):
    """Unknown, not clean -- and the lag block above is where that is said."""
    a_thread(session, "elsewhere", 12)

    assert drift.stale_threads(session, {"thing": a_clone(tmp_path, [12])}) == []


def test_the_report_states_the_half_it_cannot_see(session, tmp_path):
    """A pull request closed without merging leaves nothing in a clone.

    Both threads found genuinely stale by hand were that case, so a short
    THREAD list must not read as a small problem.
    """
    findings, lags = drift.survey(session, {})

    assert "closed WITHOUT merging" in drift.render(findings, lags)


# --- the narrowing ----------------------------------------------------------


def test_narrowing_to_one_project_narrows_the_findings_too(session, tmp_path):
    """The first version filtered the clones only, so `--project qmcp` printed
    one project's lag above thirty other projects' findings."""
    mine = a_project(session, "quaternionmedia/mine")
    other = a_project(session, "quaternionmedia/other")
    a_delta(session, mine, 91)
    a_delta(session, other, 92)

    findings, lags = drift.survey(session, {}, only="mine")

    assert {f.project for f in findings} == {"quaternionmedia/mine"}
    assert [lag.project for lag in lags] == ["quaternionmedia/mine"]
