"""Nothing committed here names the machine it was made on.

**A SCREENSHOT IS A PUBLISHED ARTIFACT AND NOBODY RE-READS IT.** A committed
screenshot of the settings tab carried `C:\\Users\\<account>\\.dossier\\dossier.db`
— an operator's username, in a public repository, in a file that is generated
once and then looked at rather than read. The account is written `<account>`
here for the same reason it was taken out of the screenshot.

One of the seven screenshots this repository commits. A second file on disk
carried it too and was never tracked, which is why `artifacts()` asks git rather
than the filesystem: what is published is what is committed.

It was nobody's mistake. The settings tab lists every candidate database by its
real path, correctly, and a capture on any machine picks up whoever is logged
in. That is why the redaction lives at the capture point in `conftest.py` and
why this test exists beside it: fixing the files would have lasted until the
next regeneration.

`docs/settings.md` had it right the whole time — it writes `C:\\Users\\you`. The
screenshots were the inconsistency, which is the ordinary shape of this: the
prose is written by somebody thinking about a reader, and the artifact is
produced by a machine thinking about nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# The account name in a home path, in any of the three shapes a path takes.
# `you` is what the redaction writes and what the docs already use.
NAMES_A_MACHINE = re.compile(
    r"(?i)(?:[A-Z]:[\\/]{1,2}Users[\\/]{1,2}|/home/|/Users/)"
    r"(?!you\b)(?P<who>[^\\/\s<>\"'{}]+)")

# Directories whose contents are published as they are, rather than read and
# edited. Prose gets reviewed; these do not.
PUBLISHED = ("docs/screenshots",)


def artifacts() -> list[Path]:
    """Every published artifact — which is every *tracked* one, not every file.

    **THIS READ THE FILESYSTEM FIRST, AND THE FILESYSTEM IS NOT THE
    REPOSITORY.** 54 screenshots sit in this directory on a machine that has run
    the suite with `--screenshots`; 7 are committed. Globbing found 54, and CI —
    which checks out only what is tracked — found 7 and failed the floor below.

    The distinction is the whole subject. An untracked screenshot is not
    published and cannot leak; a tracked one is published and can. Reading the
    filesystem checked 47 files nobody will ever see and would have reported a
    leak in one of them as though it mattered.

    It also made the finding wrong in both directions. The account name was
    reported as being in "2 of 54 screenshots". It was in one of seven: the
    second file carrying it was never committed.
    """
    import subprocess

    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", *PUBLISHED],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return sorted(
        ROOT / line for line in listed.stdout.splitlines()
        if line.strip().endswith(".svg"))


def test_there_are_artifacts_to_check():
    """A glob that matched nothing would make the check below vacuous, and a
    vacuous check reports green.

    The floor is low on purpose: it is a floor against *nothing*, and setting it
    near the current count makes it a second thing to maintain. The first
    version asserted `> 10` against a filesystem count of 54 and broke the
    moment CI counted the 7 that are committed.

    Mutation: point `PUBLISHED` at an empty directory and this fails.
    """
    assert len(artifacts()) > 3, f"only {len(artifacts())} tracked artifact(s)"


def test_no_published_artifact_names_an_account():
    """THE ONE THIS EXISTS FOR.

    Mutation: put a real home path back into any screenshot and this fails,
    naming the file and the account.
    """
    offenders: list[str] = []
    for artifact in artifacts():
        body = artifact.read_text(encoding="utf-8", errors="replace")
        for match in NAMES_A_MACHINE.finditer(body):
            who = match.group("who")
            offenders.append(f"{artifact.relative_to(ROOT).as_posix()}: {who}")

    assert not offenders, (
        "these published artifacts name the machine they were made on:\n  "
        + "\n  ".join(sorted(set(offenders)))
        + "\n\nRegenerate them: `conftest.redact_home` runs on every capture "
          "and writes `you` in place of the account. If one slipped past, that "
          "function is what to fix — not the file.")


def test_the_placeholder_itself_is_allowed():
    """The control. Without it this is satisfiable by rejecting every path,
    which would make regeneration impossible rather than safe.
    """
    assert not NAMES_A_MACHINE.search(r"C:\Users\you\.dossier\dossier.db")
    assert not NAMES_A_MACHINE.search("/home/you/.dossier")


@pytest.mark.parametrize("path", [
    # leaks: allow this file is the guard; every path here is a fixture
    r"C:\Users\peter\.dossier\dossier.db",
    # leaks: allow this file is the guard; every path here is a fixture
    "C:/Users/someone/.dossier",
    # leaks: allow this file is the guard; every path here is a fixture
    "/home/operator/.dossier",
    # leaks: allow this file is the guard; every path here is a fixture
    "/Users/operator/Library",
])
def test_a_real_account_is_caught_in_every_path_shape(path: str):
    """Windows, POSIX and macOS shapes, with either slash. A check that only
    knew one of them would pass on a colleague's machine.
    """
    assert NAMES_A_MACHINE.search(path), path


def test_the_capture_redacts_before_anything_is_committed():
    """The guard above catches what reached the repository; this pins the thing
    that stops it reaching there at all.

    Mutation: remove the `redact_home` call from `ScreenshotHelper.capture` and
    this fails.
    """
    import inspect
    import sys

    sys.path.insert(0, str(ROOT / "tests"))
    import conftest

    # leaks: allow the input to the redaction has to look like a real account
    assert conftest.redact_home(r"C:\Users\peter\.dossier") == r"C:\Users\you\.dossier"
    source = inspect.getsource(conftest.ScreenshotHelper)
    assert source.count("redact_home") >= 2, (
        "every capture path must redact. ScreenshotHelper has a sync and an "
        "async one, and a screenshot taken through the other is unredacted.")
