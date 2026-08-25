"""Removing a branch label, and every case where it must not.

Every case builds real repositories, pushes to a real remote and deletes from
it. The subject is what git considers reachable and what it considers gone, and
a stubbed graph is neither.

**THE FIXTURE HAS A REMOTE, WHICH IS NOT DECORATION.** `trim` measures against
`origin/main` and reads `%(upstream:track)`, so a repository with no remote
would exercise neither. The `gone` case in particular can only be built by
deleting a branch from a remote and pruning -- which is what
`upstream_is_gone` does, because the alternative is asserting that a detector
fires without ever having seen it fire.

THE MUTATIONS, per P16, quoted as they printed.

`PERMANENT_EXACT`/`PERMANENT_PREFIXES` dropped from the guard in `plan`, so a
namespace a downstream submodule pins is offered for removal:

    AssertionError: assert 'project/alfred' not in ['project/alfred']

The `name in gone` branch removed, so an unestablished branch falls through to
UNMERGED and the blind spot goes unreported:

    AssertionError: a branch with a deleted upstream was not named as the
    blind spot
    assert [] == ['squashed']

`execute` given `plan_.branches` instead of `plan_.trimmable`, which is the one
that would hand `main` to git:

    AssertionError: assert ['main', 'spent'] == ['spent']
    At index 0 diff: 'main' != 'spent'
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dossier import trim as mod


def git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    assert done.returncode == 0, f"git {' '.join(args)}\n{done.stdout}{done.stderr}"
    return done.stdout


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", name, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo).strip()


@pytest.fixture()
def clone(tmp_path: Path) -> Path:
    """A clone with a real `origin`, on `main`, with one commit pushed.

    Signing is turned off in the repository's own config rather than passed on
    a command line: a scratch repository with no key is a repository that does
    not sign, which is a property of the fixture rather than an instruction to
    skip a check.
    """
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    repo = tmp_path / "work"
    git("clone", "-q", str(remote), str(repo), cwd=tmp_path)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T"),
                       ("commit.gpgsign", "false")):
        git("config", key, value, cwd=repo)

    commit(repo, "first")
    git("push", "-q", "-u", "origin", "main", cwd=repo)
    return repo


def spent_branch(repo: Path, name: str) -> str:
    """A branch merged into main by fast-forward, so main contains its tip."""
    git("checkout", "-q", "-b", name, cwd=repo)
    tip = commit(repo, f"{name.replace('/', '-')}-work")
    git("checkout", "-q", "main", cwd=repo)
    git("merge", "-q", "--no-ff", "-m", f"merge {name}", name, cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    return tip


def live_branch(repo: Path, name: str) -> str:
    """A branch with a commit that is nowhere else."""
    git("checkout", "-q", "-b", name, cwd=repo)
    tip = commit(repo, f"{name.replace('/', '-')}-work")
    git("checkout", "-q", "main", cwd=repo)
    return tip


def upstream_is_gone(repo: Path, name: str) -> str:
    """A branch pushed, then deleted from the remote, then pruned.

    The shape a squash-merged pull request leaves behind: the remote branch is
    removed, the local one remains, and its commits are not in `main` because
    the merge rewrote them.
    """
    git("checkout", "-q", "-b", name, cwd=repo)
    tip = commit(repo, f"{name.replace('/', '-')}-work")
    git("push", "-q", "-u", "origin", name, cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    git("push", "-q", "origin", "--delete", name, cwd=repo)
    git("fetch", "-q", "--prune", cwd=repo)
    return tip


def by_name(plan) -> dict:
    return {b.name: b for b in plan.branches}


# --- what may be removed ------------------------------------------------------


def test_a_branch_already_in_main_is_trimmable(clone: Path):
    spent_branch(clone, "spent")
    plan = mod.plan("r", clone)

    assert [b.name for b in plan.trimmable] == ["spent"]
    assert by_name(plan)["spent"].why == "ancestor of origin/main"


def test_a_branch_with_work_of_its_own_is_kept_and_says_so(clone: Path):
    live_branch(clone, "live")
    plan = mod.plan("r", clone)

    kept = by_name(plan)["live"]
    assert not kept.trimmable
    assert kept.why == mod.UNMERGED
    assert kept.unique == 1, "the commit nowhere else was not counted"


def test_the_default_ref_it_measured_against_is_reported(clone: Path):
    """The answer depends on it entirely, so it is never left implicit."""
    assert mod.plan("r", clone).default == "origin/main"


# --- what must never be removed ------------------------------------------------


def test_main_is_never_trimmable_even_though_it_is_its_own_ancestor(clone: Path):
    plan = mod.plan("r", clone)

    assert "main" not in [b.name for b in plan.trimmable], (
        "main was offered for trimming")
    assert by_name(plan)["main"].why == mod.PERMANENT


@pytest.mark.parametrize("name", ["project/alfred", "workspace/math-experiments"])
def test_a_permanent_namespace_is_kept_when_it_is_merged(clone: Path, name: str):
    """**THE CASE THAT COSTS MOST.** A downstream submodule pins a `project/`
    tip. Being merged is exactly when this would otherwise look safe."""
    spent_branch(clone, name)
    plan = mod.plan("r", clone)

    assert name not in [b.name for b in plan.trimmable]
    assert by_name(plan)[name].why == mod.PERMANENT


def test_the_checked_out_branch_is_kept_with_that_reason(clone: Path):
    spent_branch(clone, "spent")
    git("checkout", "-q", "spent", cwd=clone)
    plan = mod.plan("r", clone)

    assert "spent" not in [b.name for b in plan.trimmable]
    assert by_name(plan)["spent"].why == mod.CHECKED_OUT


# --- the blind spot, which is reported rather than removed ---------------------


def test_a_branch_whose_upstream_is_gone_is_named_and_never_trimmed(clone: Path):
    """THE ONE THAT MATTERS.

    A squash-merged pull request leaves this: the remote branch deleted, the
    local one holding commits that are not in `main` because the merge rewrote
    them. It is indistinguishable from a branch somebody abandoned, so it is
    reported and never removed.
    """
    upstream_is_gone(clone, "squashed")
    plan = mod.plan("r", clone)

    assert [b.name for b in plan.unestablished] == ["squashed"], (
        "a branch with a deleted upstream was not named as the blind spot")
    assert "squashed" not in [b.name for b in plan.trimmable]
    assert by_name(plan)["squashed"].upstream_gone


def test_the_gone_detector_fires_at_all(clone: Path):
    """A detector that always returns nothing passes every test above it.

    The empty assertion this organisation keeps catching: on the real `dossier`
    clone no branch reported `gone`, and that is indistinguishable from a
    broken read until something is built that must report one.
    """
    assert mod._gone(clone) == set()
    upstream_is_gone(clone, "squashed")
    assert mod._gone(clone) == {"squashed"}


def test_a_squash_merged_branch_is_not_offered(clone: Path):
    """The sweep under-removes, which is the safe direction, and this pins it."""
    upstream_is_gone(clone, "squashed")

    assert mod.plan("r", clone).trimmable == ()


# --- removing, which only a caller that meant it reaches -----------------------


def test_execute_removes_the_trimmable_and_reports_the_way_back(clone: Path):
    tip = spent_branch(clone, "spent")
    plan = mod.plan("r", clone)

    removals = mod.execute(plan)

    assert [r.name for r in removals] == ["spent"]
    assert removals[0].removed
    assert removals[0].tip in tip, "the reported tip is not the branch's commit"
    assert removals[0].restore == f"git branch spent {removals[0].tip}"
    assert "spent" not in git("branch", "--format=%(refname:short)", cwd=clone)


def test_execute_touches_nothing_the_plan_kept(clone: Path):
    """`only` narrows the plan. It cannot widen it.

    Mutation: passing `plan_.branches` rather than `plan_.trimmable` fails
    here, which is the assertion standing between a narrowing option and a
    deletion of anything a caller can name.
    """
    live_branch(clone, "unmerged")
    plan = mod.plan("r", clone)

    removals = mod.execute(plan, only=("unmerged",))

    assert [r.name for r in removals] == [], "a kept branch was passed to git"
    assert "unmerged" in git("branch", "--format=%(refname:short)", cwd=clone)


def test_only_narrows_to_the_named_branch(clone: Path):
    spent_branch(clone, "one")
    spent_branch(clone, "two")
    plan = mod.plan("r", clone)

    removals = mod.execute(plan, only=("one",))

    assert [r.name for r in removals] == ["one"]
    listed = git("branch", "--format=%(refname:short)", cwd=clone)
    assert "two" in listed


def test_removal_asks_git_to_check_the_claim_rather_than_trusting_it(clone: Path):
    """`git branch -d` refuses an unmerged branch. A disagreement between this
    module and git therefore surfaces as a refusal instead of a deletion.

    Built by moving the branch after the plan was made, which is the shape of
    the race a long-running panel would hit.
    """
    spent_branch(clone, "spent")
    plan = mod.plan("r", clone)
    git("checkout", "-q", "spent", cwd=clone)
    commit(clone, "after-the-plan")
    git("checkout", "-q", "main", cwd=clone)

    removals = mod.execute(plan)

    assert removals[0].removed is False
    assert "not fully merged" in removals[0].detail
    assert "spent" in git("branch", "--format=%(refname:short)", cwd=clone)


# --- what it declines to read --------------------------------------------------


def test_no_clone_is_a_reason_rather_than_an_empty_plan():
    plan = mod.plan("nowhere", None)

    assert not plan.readable
    assert plan.reason == "no clone on this machine"
    assert plan.trimmable == ()


def test_a_directory_that_is_not_a_clone_says_so(tmp_path: Path):
    plan = mod.plan("r", tmp_path)

    assert not plan.readable
    assert "not a git clone" in plan.reason


def test_a_repository_with_no_remote_main_is_refused_rather_than_guessed(
        tmp_path: Path):
    """Measuring against a local `main` that may be behind would report a
    pushed-and-unmerged branch as trimmable."""
    repo = tmp_path / "solo"
    git("init", "-q", "-b", "main", str(repo), cwd=tmp_path)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T"),
                       ("commit.gpgsign", "false")):
        git("config", key, value, cwd=repo)
    commit(repo, "first")

    plan = mod.plan("r", repo)

    assert not plan.readable
    assert "origin/main" in plan.reason


def test_execute_on_an_unreadable_plan_does_nothing(tmp_path: Path):
    assert mod.execute(mod.plan("nowhere", None)) == []


# --- what a person reads -------------------------------------------------------


def test_a_dry_run_says_that_nothing_was_removed(clone: Path):
    spent_branch(clone, "spent")
    text = mod.render(mod.plan("r", clone))

    assert "Nothing was removed" in text
    assert "--delete" in text
    assert "No remote branch is touched" in text


def test_an_empty_result_does_not_read_as_a_clean_bill_of_health(clone: Path):
    """`Nothing is trimmable` and `nothing here is spent` are different claims."""
    text = mod.render(mod.plan("r", clone))

    assert "Nothing is trimmable" in text
    assert "not the same as nothing being spent" in text


def test_the_report_names_the_blind_spot_it_left(clone: Path):
    upstream_is_gone(clone, "squashed")
    text = mod.render(mod.plan("r", clone))

    assert "squashed" in text
    assert "Not trimmed" in text
    assert "squash or rebase merge" in text


def test_the_removal_report_carries_the_restore_command(clone: Path):
    spent_branch(clone, "spent")
    plan = mod.plan("r", clone)
    text = mod.render(plan, mod.execute(plan))

    assert "Removed 1 of 1" in text
    assert "restore with: git branch spent" in text


# --- the sweep's result is a delta --------------------------------------------


def test_one_trim_is_one_delta_and_not_one_per_branch(clone: Path):
    """`dossier.sweep` states the rule: a sweep is one unit of work with many
    parts, not many jobs that happen to look alike."""
    spent_branch(clone, "one")
    spent_branch(clone, "two")
    plan = mod.plan("r", clone)
    removals = mod.execute(plan)

    fields = mod.as_delta(plan, removals)

    assert fields["title"] == "Trim 2 merged branch(es) from r"
    assert fields["delta_type"] == "chore"


def test_the_delta_name_is_the_same_for_the_same_removals(clone: Path):
    """Content-addressed, so re-running a trim names the work it already did.

    Nothing here reads a clock, which is why the same trim on two machines is
    the same name.
    """
    one = [mod.Removal("a", "abc1234", True), mod.Removal("b", "def5678", True)]
    other = list(reversed(one))

    assert mod.delta_name(one) == mod.delta_name(other)
    assert mod.delta_name(one) != mod.delta_name(
        [mod.Removal("a", "abc1234", True)])


def test_a_refused_removal_does_not_enter_the_delta_name(clone: Path):
    """The delta names what went, and a refusal did not go."""
    went = [mod.Removal("a", "abc1234", True)]
    with_refusal = went + [mod.Removal("b", "def5678", False, "not fully merged")]

    assert mod.delta_name(went) == mod.delta_name(with_refusal)


def test_the_delta_carries_the_restore_commands(clone: Path):
    """**THE POINT OF RECORDING IT.** A terminal scrolls; the database does
    not. After the window closes the delta is the only way back."""
    spent_branch(clone, "spent")
    plan = mod.plan("r", clone)
    removals = mod.execute(plan)

    description = mod.as_delta(plan, removals)["description"]

    assert "git branch spent" in description
    assert removals[0].tip in description
    assert plan.default in description


def test_the_delta_records_what_the_sweep_left_alone(clone: Path):
    """The blind spot survives into the record, not just into the terminal."""
    spent_branch(clone, "spent")
    upstream_is_gone(clone, "squashed")
    plan = mod.plan("r", clone)

    description = mod.as_delta(plan, mod.execute(plan))["description"]

    assert "squashed" in description
    assert "squash or rebase" in description


def test_the_dry_run_names_the_delta_the_real_run_will_produce(clone: Path):
    """A preview that named a different delta would be worse than naming none.

    Mutation: `_prospective` returning `[]` makes the two names differ and
    fails here.
    """
    spent_branch(clone, "one")
    spent_branch(clone, "two")
    plan = mod.plan("r", clone)

    previewed = mod.delta_name(mod._prospective(plan))
    produced = mod.delta_name(mod.execute(plan))

    assert previewed == produced
    assert previewed in mod.render(plan)


def test_a_sweep_that_removed_nothing_previews_no_delta(clone: Path):
    """No work was done, so there is no unit of work to name."""
    text = mod.render(mod.plan("r", clone))

    assert "Would be recorded" not in text
