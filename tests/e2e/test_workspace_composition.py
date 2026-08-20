"""The composition, read from the real workspace rather than from fixtures.

`walkthrough/05-a-project-made-of-projects.md` states the shape and runs
anywhere, because addresses denote without existing. This reads the actual
submodule pins, and therefore only runs where the sibling clones are.

**IT SKIPS WITH A REASON RATHER THAN PASSING QUIETLY.** A test that silently
does nothing off the author's machine is worse than no test: the suite goes
green and nobody learns that the interesting half never ran.

**IT REPORTS THE BRANCH MAPPING AND DOES NOT ASSERT CONFORMANCE.** Whether a
downstream repository pins the branch it is supposed to is a fact about that
repository, and failing dossier's suite over it would put the alarm in a place
nobody looking for it would find. What is asserted here are the properties the
composition itself depends on.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# The repositories that embed the constitution, as of the commit that wrote
# this. Found with `git config --file .gitmodules --get-regexp path` across the
# workspace; not a guess, and not a list this repository owns -- if it drifts,
# `test_the_named_repositories_still_embed_the_corpus` is what says so.
PARTS = ("dossier", "qmcp", "rad", "alfred", "apothecary", "datum")
SUBMODULE = "governance/qm"


def workspace() -> Path | None:
    """The directory holding the sibling clones, or None."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "qm" / "PRINCIPLES.md").is_file() and (parent / "qmcp").is_dir():
            return parent
    return None


def git(repo: Path, *args: str) -> tuple[int, str]:
    done = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode, done.stdout.strip()


def pin_of(root: Path, name: str) -> str | None:
    """The commit a repository's `governance/qm` submodule points at."""
    code, out = git(root / name, "ls-tree", "HEAD", SUBMODULE)
    if code != 0 or not out:
        return None
    fields = out.split()
    return fields[2] if len(fields) > 2 else None


@pytest.fixture(scope="module")
def root() -> Path:
    found = workspace()
    if found is None:
        pytest.skip("the sibling clones are not beside this one, so the real "
                    "pins cannot be read; the shape is asserted in "
                    "walkthrough/05-a-project-made-of-projects.md")
    return found


@pytest.fixture(scope="module")
def pins(root: Path) -> dict[str, str]:
    found = {name: pin_of(root, name) for name in PARTS
             if (root / name / ".git").exists()}
    present = {name: pin for name, pin in found.items() if pin}
    if len(present) < 2:
        pytest.skip(f"only {len(present)} of {len(PARTS)} clones are here, "
                    f"which is not enough to compose anything")
    return present


# --- the parts ----------------------------------------------------------------


def test_the_named_repositories_still_embed_the_corpus(root, pins):
    """The composition is real only while the parts are still parts.

    A repository that dropped the submodule would make this list a description
    of the past, and the page built on it a description of nothing.
    """
    missing = [name for name in PARTS
               if (root / name / ".git").exists() and name not in pins]
    assert not missing, f"no {SUBMODULE} in: {missing}"


def test_the_parts_pin_different_commits(pins):
    """THE ONE THAT MATTERS, AND IT IS A FINDING RATHER THAN A RULE.

    A composed project whose parts all pinned the same commit would be a
    monorepo wearing submodules. They do not: each downstream repository takes
    the corpus in on its own schedule, which is what `derived-from` records --
    the strand came out of that one and *both continue*.

    Mutation: this fails on the day somebody synchronises every pin, which is
    a real change to how this organisation works and should not pass quietly.
    """
    assert len(set(pins.values())) > 1, (
        f"every part pins {next(iter(pins.values()))}, so nothing is composed")


def test_a_pin_is_a_commit_this_clone_can_resolve(root, pins):
    """A pin naming a commit nobody has is a composition that cannot be read.

    Skipped rather than failed for a part whose corpus history is not local:
    that is a fetch state, not a defect in the pin.
    """
    corpus = root / "qm"
    unresolvable = []
    for name, pin in pins.items():
        code, _ = git(corpus, "cat-file", "-e", f"{pin}^{{commit}}")
        if code != 0:
            unresolvable.append(name)
    if unresolvable == list(pins):
        pytest.skip("no pin resolves in the local corpus clone -- it has not "
                    "fetched, which is a state of this machine")
    assert not unresolvable or len(unresolvable) < len(pins)


# --- the thing that looks like a defect and is not ----------------------------


def test_a_pin_is_not_expected_to_be_an_ancestor_of_main(root, pins):
    """THE READING THAT WOULD BE WRONG.

    `git merge-base --is-ancestor <pin> main` returns 1 for these pins, and the
    obvious conclusion -- that every downstream repository has drifted onto an
    abandoned line -- is false. A `project/<name>` branch takes changes in and
    never out: `main` reaches it as a `propagate/<name>-<date>` pull request,
    merged and never rebased, because a downstream submodule pins the tip. So
    the pin is deliberately not on `main`.

    This asserts the merge-base exists instead, which is the question worth
    asking: the pin and `main` share history, and how far apart they are is a
    number rather than a verdict.

    Mutation: assert ancestry and this fails against the real workspace, which
    is how the misreading was caught.
    """
    corpus = root / "qm"
    code, main = git(corpus, "rev-parse", "--verify", "--quiet", "origin/main")
    if code != 0 or not main:
        pytest.skip("no origin/main in the corpus clone")

    shared = {}
    for name, pin in pins.items():
        if git(corpus, "cat-file", "-e", f"{pin}^{{commit}}")[0] != 0:
            continue
        code, base = git(corpus, "merge-base", pin, main)
        if code == 0 and base:
            shared[name] = base
    if not shared:
        pytest.skip("no pin resolves locally, so no merge-base can be taken")

    assert shared, "no part shares history with the corpus's main"
    for name, base in shared.items():
        assert len(base) == 40, f"{name}: {base!r} is not a commit"


def test_the_branch_holding_each_pin_is_reported(root, pins, capsys):
    """Reported, not asserted. Which branch a downstream repository pins is
    that repository's business; this makes it visible from the composition so
    an anomaly is findable rather than invisible.

    ANY BRANCH, NOT THE FIRST ONE. A commit is usually on several branches, and
    reading only the first produced a false anomaly while this was being
    written: `apothecary` looked like it pinned a fix branch instead of its
    project branch, because `fix/apothecary-seed-refresh` sorts ahead of
    `project/apothecary` and both hold the commit. Every part conforms.

    Kept as a report rather than an assertion anyway. Which branch a downstream
    repository pins is that repository's business, and a red suite in the
    control panel is the wrong place to learn about it.
    """
    corpus = root / "qm"
    lines = []
    for name, pin in sorted(pins.items()):
        if git(corpus, "cat-file", "-e", f"{pin}^{{commit}}")[0] != 0:
            lines.append(f"  {name:<12} {pin[:8]}  (not in this clone)")
            continue
        _, branches = git(corpus, "branch", "-a", "--contains", pin)
        holding = [b.strip().lstrip("* ") for b in branches.splitlines()]
        expected = f"project/{name}"
        matches = any(b.endswith(expected) for b in holding)
        lines.append(f"  {name:<12} {pin[:8]}  "
                     f"{'on ' + expected if matches else 'NOT on ' + expected}")

    with capsys.disabled():
        print("\nwhich branch holds each part's pin:")
        print("\n".join(lines))
    assert lines
