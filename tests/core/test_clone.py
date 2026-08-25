"""What this database knows about and this disk does not have.

**EIGHTY-TWO OF A HUNDRED AND FIFTEEN**, measured on 2026-08-25. Every reading
that needs a clone — branch hygiene, and anything asking what would be lost if
this disk died — answered `unknown` for all of them, which is honest and not
useful, and closing the gap meant typing `git clone` eighty-two times.

Nothing here decides to clone anything. A repository with no clone is an
ordinary state and usually the right one, so this reports what is absent and
clones exactly what it is told to.

**NO TEST HERE RUNS `git clone`.** `clone()` takes the runner, so what is under
test is which argv it builds and how it reads what comes back — not whether
GitHub is up.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dossier import clone as module


class FakeProject:
    def __init__(self, name, owner=None, repo=None, url=None, full_name=None):
        self.name = name
        self.full_name = full_name or name
        self.github_owner = owner
        self.github_repo = repo
        self.github_url = url


class Ran:
    """A runner that records rather than runs."""

    def __init__(self, returncode=0, stderr=""):
        self.argv = None
        self._code = returncode
        self._stderr = stderr

    def __call__(self, argv, **kwargs):
        self.argv = argv

        class Done:
            returncode = self._code
            stderr = self._stderr
            stdout = ""

        return Done()


def nothing_found(name, roots=None):
    return None


def everything_found(name, roots=None):
    return Path("/somewhere") / name


# --- what counts as absent ---------------------------------------------------


def test_a_delta_address_is_not_a_repository_to_clone(tmp_path):
    """THE ONE THIS EXISTS FOR.

    Four rows in the real database are delta addresses —
    `quaternionmedia/qm/delta/pr-57` — and the first version took the last
    segment of the name, so it offered to clone `pr-57` into a directory beside
    this checkout. They carry `github_owner` and `github_repo` naming the real
    repository, which is the field that answers the question.

    Mutation: derive the name from `full_name.split("/")[-1]` again and this
    fails.
    """
    delta = FakeProject("quaternionmedia/qm/delta/pr-57", owner="quaternionmedia",
                        repo="qm", url="https://github.com/quaternionmedia/qm")

    found = module.absent([delta], into=tmp_path, find=nothing_found)

    assert len(found) == 1
    assert found[0].name == "qm", found[0]
    assert found[0].repo == "quaternionmedia/qm"
    assert found[0].into == tmp_path / "qm"


def test_one_repository_is_absent_once(tmp_path):
    """A delta address and its repository are two rows and one repository.

    Mutation: drop the `seen` set and this fails.
    """
    repo = FakeProject("quaternionmedia/qm", owner="quaternionmedia", repo="qm",
                       url="https://github.com/quaternionmedia/qm")
    delta = FakeProject("quaternionmedia/qm/delta/pr-57", owner="quaternionmedia",
                        repo="qm", url="https://github.com/quaternionmedia/qm")

    found = module.absent([repo, delta], into=tmp_path, find=nothing_found)
    assert [one.repo for one in found] == ["quaternionmedia/qm"]


def test_a_row_that_names_no_repository_is_skipped(tmp_path):
    """Skipped rather than guessed at. There is nothing to look for."""
    odd = FakeProject("a/b/c/d")
    assert module.absent([odd], into=tmp_path, find=nothing_found) == ()


def test_a_repository_already_here_is_not_absent(tmp_path):
    repo = FakeProject("org/one", owner="org", repo="one", url="https://x/one")
    assert module.absent([repo], into=tmp_path, find=everything_found) == ()


def test_absent_uses_the_same_rule_every_other_reading_uses():
    """Two definitions of where a repository lives is how one of them starts
    reporting a repository missing while the other reads it happily."""
    import inspect

    source = inspect.getsource(module.absent)
    assert "find_clone" in source


# --- what it refuses ---------------------------------------------------------


def test_a_repository_with_no_url_is_refused_rather_than_attempted(tmp_path):
    one = module.Absent(repo="org/one", name="one", url="",
                        into=tmp_path / "one")
    outcome = module.clone(one, run=Ran())
    assert outcome.state == module.REFUSED
    assert "URL" in outcome.detail


def test_a_destination_that_exists_is_refused_before_git_runs(tmp_path):
    """git would fail on it anyway, and its wording is about a non-empty
    directory rather than about already having the thing.

    Mutation: drop the check and the runner is reached, so `ran.argv` is set
    and this fails.
    """
    (tmp_path / "one").mkdir()
    one = module.Absent(repo="org/one", name="one", url="https://x/one",
                        into=tmp_path / "one")
    ran = Ran()
    outcome = module.clone(one, run=ran)

    assert outcome.state == module.REFUSED
    assert "already there" in outcome.detail
    assert ran.argv is None, "git was run on a destination that exists"


# --- what it builds ----------------------------------------------------------


def test_the_argv_is_a_plain_clone(tmp_path):
    one = module.Absent(repo="org/one", name="one", url="https://x/one",
                        into=tmp_path / "one")
    ran = Ran()
    assert module.clone(one, run=ran).ok
    assert ran.argv == ["git", "clone", "https://x/one", str(tmp_path / "one")]


def test_shallow_is_asked_for_and_never_assumed(tmp_path):
    """Branch hygiene counts commits no remote has, and a shallow clone cannot
    answer that at all — so it is a different artifact, not a faster one.

    Mutation: pass `--depth 1` by default and this fails.
    """
    one = module.Absent(repo="org/one", name="one", url="https://x/one",
                        into=tmp_path / "one")

    plain = Ran()
    module.clone(one, run=plain)
    assert "--depth" not in plain.argv

    shallow = Ran()
    module.clone(one, run=shallow, depth=1)
    assert shallow.argv[2:4] == ["--depth", "1"]


def test_a_failure_carries_git_s_own_words(tmp_path):
    """A repository that does not exist, one with no credentials, and one on a
    full disk all fail, and only git can say which.

    Mutation: replace `detail` with a category and this fails.
    """
    one = module.Absent(repo="org/one", name="one", url="https://x/one",
                        into=tmp_path / "one")
    ran = Ran(returncode=128, stderr="remote: Repository not found.\n")
    outcome = module.clone(one, run=ran)

    assert outcome.state == module.FAILED
    assert "Repository not found" in outcome.detail


def test_a_summary_counts_every_state(tmp_path):
    """A summary naming only what succeeded reads as everything having been
    tried."""
    one = module.Absent(repo="org/one", name="one", url="", into=tmp_path)
    outcomes = [module.Outcome(one, module.CLONED),
                module.Outcome(one, module.REFUSED, "no URL"),
                module.Outcome(one, module.FAILED, "boom")]
    said = module.summarise(outcomes)
    for state in (module.CLONED, module.REFUSED, module.FAILED):
        assert state in said, said


def test_nothing_to_clone_says_so():
    assert module.summarise([]) == "nothing to clone"


# --- every way in ------------------------------------------------------------


def test_the_ring_reaches_it():
    """Asked for in rad, the API and click — one act, three doors.

    Mutation: remove the wedge and this fails.
    """
    from dossier.rad.index import keystroke
    from dossier.tui.app import DossierApp

    assert keystroke("reach.clone"), "no keystroke reaches it"
    assert "reach.clone" in DossierApp.RAD_HANDLED


def test_the_command_line_reaches_it():
    from dossier.cli import cli

    assert "clone" in cli.list_commands(None)


def test_the_api_reaches_it_for_one_and_not_for_all():
    """**THERE IS NO ROUTE THAT CLONES EVERYTHING.** An HTTP call pulling
    eighty-two repositories onto a machine is a denial of service with a polite
    name, and the caller cannot see the disk it is filling. The command line has
    `--all` because a person is standing in front of that disk.

    Mutation: add a POST that clones everything and this fails.
    """
    from dossier.api.main import app

    paths = {str(route.path) for route in app.routes
             if "clone" in str(route.path)}
    assert "/clones/absent" in paths
    assert "/clones/{owner}/{name}" in paths
    assert not any(path.rstrip("/").endswith("clones") and path != "/clones/absent"
                   for path in paths), paths


def test_the_command_lists_before_it_acts():
    """A clone is a network fetch and a write to somebody's disk, so listing is
    the default.

    Mutation: clone when neither REPO nor --all is given and this fails.
    """
    import inspect

    from dossier.cli import cli

    source = inspect.getsource(cli.get_command(None, "clone").callback)
    listing = source.index("Name one, or pass --all")
    acting = source.index("outcomes = []")
    assert listing < acting
    assert "click.confirm" in source
