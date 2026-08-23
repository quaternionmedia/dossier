"""Which branches carry work that exists nowhere else.

Every case builds real repositories and commits into them. The subject is what
git can and cannot reach from a ref, and a stubbed graph cannot be unreachable
from anything.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from dossier import branches as mod


def git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    assert done.returncode == 0, f"git {' '.join(args)}\n{done.stdout}{done.stderr}"
    return done.stdout


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", name, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo).strip()


@pytest.fixture()
def clone(tmp_path: Path) -> Path:
    """A repository with an `origin/main` to measure against."""
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)

    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.email", "t@example.com", cwd=repo)
    git("config", "user.name", "T", cwd=repo)
    commit(repo, "first.txt")
    git("remote", "add", "origin", remote.as_uri(), cwd=repo)
    git("push", "-q", "-u", "origin", "main", cwd=repo)
    return repo


def counts(repo: Path) -> dict[str, int]:
    return mod.survey("r", repo).counts


# --- the distinction the Branches facet cannot make ---------------------------


def test_a_branch_whose_commits_are_on_main_is_merged(clone: Path):
    """A label over history somebody already has. Deleting it loses nothing."""
    git("checkout", "-q", "-b", "done", cwd=clone)
    git("checkout", "-q", "main", cwd=clone)
    # `main` is permanent by namespace, so it is not counted as merged.
    assert counts(clone) == {mod.MERGED: 1, mod.PERMANENT: 1}


def test_a_branch_with_commits_on_no_other_ref_is_at_risk(clone: Path):
    """THE ONE THIS EXISTS FOR.

    `branches_org` says a branch is "work in flight or work never cleaned up,
    and the two are indistinguishable from this side". From a clone they are
    distinguishable, and this is the side that can tell.

    Mutation: classify everything unmerged as `contained` and this fails.
    """
    git("checkout", "-q", "-b", "only-here", cwd=clone)
    commit(clone, "unique.txt")
    git("checkout", "-q", "main", cwd=clone)

    survey = mod.survey("r", clone)
    assert survey.counts.get(mod.AT_RISK) == 1
    assert survey.at_risk == [("only-here", 1)]


def test_two_names_for_one_unpushed_commit_are_both_at_risk(clone: Path):
    """**THE FALSE NEGATIVE THAT CHANGED THE DEFINITION.**

    Comparing against every ref, these two cancelled each other: each saw the
    other holding "its" commit, both reported zero, and unpushed work read as
    safe. Another name on the same machine is not a second copy — losing the
    disk loses both.

    Mutation: compare against all refs instead of remotes and this fails.
    """
    git("checkout", "-q", "-b", "work", cwd=clone)
    commit(clone, "unique.txt")
    git("branch", "also-work", cwd=clone)
    git("checkout", "-q", "main", cwd=clone)

    survey = mod.survey("r", clone)
    assert survey.counts.get(mod.AT_RISK) == 2
    assert sorted(name for name, _ in survey.at_risk) == ["also-work", "work"]


def test_a_pushed_but_unmerged_branch_is_not_at_risk(clone: Path):
    """An open pull request. It is not merged and it is not in one place, and
    those are different facts.

    Mutation: treat every unmerged branch as at risk and this fails.
    """
    git("checkout", "-q", "-b", "in-review", cwd=clone)
    commit(clone, "proposed.txt")
    git("push", "-q", "origin", "in-review", cwd=clone)
    git("checkout", "-q", "main", cwd=clone)

    survey = mod.survey("r", clone)
    assert survey.at_risk == []
    assert survey.counts.get(mod.CONTAINED) == 1


def test_the_count_is_the_commits_only_that_branch_has(clone: Path):
    git("checkout", "-q", "-b", "three", cwd=clone)
    for name in ("a.txt", "b.txt", "c.txt"):
        commit(clone, name)
    git("checkout", "-q", "main", cwd=clone)
    assert mod.survey("r", clone).at_risk == [("three", 3)]


# --- the bug that made this report nothing ------------------------------------


def test_a_branch_does_not_cancel_its_own_commits(clone: Path):
    """**THE FIRST VERSION REPORTED THAT NOTHING ANYWHERE WAS AT RISK.**

    It asked `rev-list <ref> --not --exclude=refs/heads/<name> --branches`, and
    `--exclude` matches relative to the glob that follows it — so the pattern
    never matched, every branch excluded nothing, and every branch cancelled
    itself to zero. A uniformly clean answer, and the one somebody about to
    delete branches wants to hear.

    Mutation: put the branch itself back into the `--not` set and this fails.
    """
    git("checkout", "-q", "-b", "only-here", cwd=clone)
    commit(clone, "unique.txt")
    git("checkout", "-q", "main", cwd=clone)

    every = mod._refs(clone)
    assert mod.unique_commits(clone, "refs/heads/only-here", every) == 1


# --- namespaces and automation ------------------------------------------------


@pytest.mark.parametrize("name", ["project/codecartographer", "workspace/x"])
def test_a_permanent_namespace_is_never_at_risk(clone: Path, name: str):
    """`docs/ref/namespaces.md` says these are never deleted — a downstream
    submodule pins a `project/` tip. Listing one as at risk invites exactly the
    deletion that breaks the pin."""
    git("checkout", "-q", "-b", name, cwd=clone)
    commit(clone, "unique.txt")
    git("checkout", "-q", "main", cwd=clone)
    assert counts(clone).get(mod.PERMANENT) == 2   # main, and this one


def test_an_automation_branch_is_counted_apart(clone: Path):
    """Nobody loses a bot's branch, and fourteen dependency bumps would bury
    the one branch a person made."""
    git("checkout", "-q", "-b", "dependabot/uv/pillow-12.3.0", cwd=clone)
    commit(clone, "bump.txt")
    git("checkout", "-q", "main", cwd=clone)

    survey = mod.survey("r", clone)
    assert survey.counts.get(mod.AUTOMATION) == 1
    assert survey.at_risk == []


# --- what it says when it cannot answer ---------------------------------------


def test_no_clone_is_unknown_and_not_zero(tmp_path: Path):
    """**A REPOSITORY WITH NO CLONE HERE IS NOT ONE WITH CLEAN BRANCHES.**
    Reporting zeros would say it had been checked.

    Mutation: return an empty Survey with `found=True` and this fails.
    """
    survey = mod.survey("elsewhere", None)
    assert survey.found is False
    assert survey.counts == {}
    assert "no clone" in survey.reason


def test_a_directory_that_is_not_a_clone_says_so(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    survey = mod.survey("r", plain)
    assert survey.found is False
    assert "not a git clone" in survey.reason


def test_a_clone_with_no_upstream_default_says_so(tmp_path: Path):
    """Without `origin/main` there is nothing to call merged, and guessing
    would classify every branch as at risk."""
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    git("init", "-q", "-b", "main", cwd=lonely)
    git("config", "user.email", "t@example.com", cwd=lonely)
    git("config", "user.name", "T", cwd=lonely)
    commit(lonely, "only.txt")

    survey = mod.survey("r", lonely)
    assert survey.counts == {}
    assert "origin/main" in survey.reason


# --- finding the clone --------------------------------------------------------


def test_a_clone_is_found_beside_this_one(tmp_path: Path):
    """The same rule `qm demo` uses. dossier stores no local path for a
    project, so a facet that wants one has to look."""
    sibling = tmp_path / "sibling"
    (sibling / ".git").mkdir(parents=True)
    assert mod.find_clone("sibling", roots=[tmp_path]) == sibling


def test_a_directory_without_a_git_is_not_a_clone(tmp_path: Path):
    (tmp_path / "notrepo").mkdir()
    assert mod.find_clone("notrepo", roots=[tmp_path]) is None


def test_a_name_nothing_matches_is_none(tmp_path: Path):
    assert mod.find_clone("absent", roots=[tmp_path]) is None


# --- the facet ----------------------------------------------------------------


def test_the_facet_has_its_own_tab():
    """**`BY_TAB` IS KEYED BY TAB, SO TWO FACETS SHARING ONE REPLACES THE
    FIRST.** Registered on `tab-branches` at first, this silently took over the
    Branches tab: twelve facets became eleven entries.

    Mutation: point the hygiene facet at another facet's tab and this fails.
    """
    from dossier import facets

    assert len(facets.BY_TAB) == len(facets.FACETS)
    assert facets.BY_TAB["tab-branches"].key == "branches"
    assert facets.BY_TAB["tab-hygiene"].key == "hygiene"


def test_a_repository_with_no_clone_renders_dashes_not_zeros():
    """Unknown is a value, in the table as well as in the survey."""
    from dossier import facets

    row = facets._hygiene_row(mod.Survey("gone", reason="no clone on this machine"))
    assert row[1] == "--"
    assert "no clone" in row[-1]


def test_the_note_says_how_many_clones_it_could_read():
    """A denominator. "2 at risk" across four clones and across one are
    different claims."""
    from dossier import facets

    note = facets._hygiene_note([
        mod.Survey("a", found=True, counts={mod.AT_RISK: 1},
                   at_risk=[("x", 1)]),
        mod.Survey("b", reason="no clone on this machine"),
    ])
    assert "1 branch(es) at risk across 1 clone(s) read" in note
    assert "had no clone here to read" in note


# --- the overview is on the startup path ---------------------------------------
#
# **A CORE REQUIREMENT IS RUNNING ON VERY UNDERPOWERED HARDWARE**, and the two
# costs that grow worst there are process spawn and a network round trip. The
# overview had both: `hygiene` ran git in every clone on the machine and
# `threads` dialled the harness, together six seconds of an eight-second build.
#
# The rule is not "make them faster". It is that the reading which opens first
# does not cross a process boundary at all.


def test_a_facet_that_crosses_a_boundary_says_so():
    """The two that do are declared, so the rule is checkable rather than
    remembered."""
    from dossier import facets

    crossing = {f.key for f in facets.FACETS if f.beyond_the_database}
    assert crossing == {"threads", "hygiene"}, crossing
    for facet in facets.FACETS:
        if facet.beyond_the_database:
            assert len(facet.beyond_the_database) > 12, (
                f"{facet.key}: say what it does, not that it is slow")


def _watch(monkeypatch) -> list[str]:
    """Record any attempt to spawn git or dial the harness.

    Patched at the two calls that actually cross, not at the facets: `Facet` is
    frozen, and patching the registry would test the arrangement rather than
    the behaviour. What matters is whether a process gets spawned.
    """
    from dossier import branches, threads

    reached: list[str] = []
    monkeypatch.setattr(
        threads, "fetch",
        lambda *a, **k: reached.append("threads") or threads.Archive())
    monkeypatch.setattr(
        branches, "find_clone",
        lambda *a, **k: reached.append("hygiene") or None)
    return reached


def test_the_startup_path_neither_spawns_nor_dials(test_session, monkeypatch):
    """THE ONE THIS EXISTS FOR.

    Asserting on the attempt rather than on a duration: a timing test on a
    developer's machine would pass with the spawning restored, and the machine
    this has to run on is not a developer's.

    Mutation: read every facet unconditionally in `build` and this fails.
    """
    from dossier.overview import build

    reached = _watch(monkeypatch)
    build(test_session, limit=2)
    assert reached == [], f"the startup path reached for {sorted(set(reached))}"


def test_asking_for_them_reads_them(test_session, monkeypatch):
    """The control. Without it this is satisfiable by never reading them at
    all, which would delete the facet rather than move it off the hot path.

    The session needs one project in it: `hygiene` surveys the repositories it
    is given, so against an empty database it correctly reaches for nothing and
    the control passes without proving anything.
    """
    from dossier.models import Project
    from dossier.overview import build

    test_session.add(Project(name="acme/thing", full_name="acme/thing",
                             github_owner="acme"))
    test_session.commit()

    reached = _watch(monkeypatch)
    build(test_session, limit=2, beyond_the_database=True)
    assert sorted(set(reached)) == ["hygiene", "threads"], reached


def test_a_skipped_reading_is_not_reported_as_an_empty_one(test_session):
    """A heading with no rows and no sentence reads as a facet that failed.

    Mutation: return a bare empty Section for a skipped facet and this fails.
    """
    from dossier.overview import build

    section = build(test_session, limit=2).section("Branch hygiene")
    assert section is not None
    assert "Not read here" in section.note
    assert "skipped reading, not an empty one" in section.note
