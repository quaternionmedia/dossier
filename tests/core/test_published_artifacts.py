"""Nothing committed here names the machine it was made on.

**A SCREENSHOT IS A PUBLISHED ARTIFACT AND NOBODY RE-READS IT.** Two committed
screenshots of the settings tab carried `C:\\Users\\peter\\.dossier\\dossier.db`
— an operator's username, in a public repository, in a file that is generated
once and then looked at rather than read.

It was nobody's mistake. The settings tab lists every candidate database by its
real path, correctly, and a capture on any machine picks up whoever is logged
in. That is why the redaction lives at the capture point in `conftest.py` and
why this test exists beside it: fixing the two files would have lasted until the
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
    found: list[Path] = []
    for where in PUBLISHED:
        found.extend(sorted((ROOT / where).rglob("*.svg")))
    return found


def test_there_are_artifacts_to_check():
    """A glob that matched nothing would make the check below vacuous, and a
    vacuous check reports green.

    Mutation: point `PUBLISHED` at an empty directory and this fails.
    """
    assert len(artifacts()) > 10, f"only {len(artifacts())} artifact(s) found"


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
    r"C:\Users\peter\.dossier\dossier.db",
    "C:/Users/someone/.dossier",
    "/home/operator/.dossier",
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

    assert conftest.redact_home(r"C:\Users\peter\.dossier") == r"C:\Users\you\.dossier"
    source = inspect.getsource(conftest.ScreenshotHelper)
    assert source.count("redact_home") >= 2, (
        "every capture path must redact. ScreenshotHelper has a sync and an "
        "async one, and a screenshot taken through the other is unredacted.")
