"""Every command the docs tell somebody to run is a command this CLI has.

**THE DEPLOYMENT RUNG, FOR THIS PROJECT'S DOCUMENTATION.**
`governance/qm/records/DRAFT-a-capability-has-four-phases.md` names deployment
as the phase that fails without a symptom: a page can tell a reader to run
something for months while every test stays green, because nothing joins the
prose to the dispatcher. `qmcp`'s `tests/test_declared_commands.py` is the same
check for that package's docstrings; this is it for these pages.

**WHAT IT FOUND WHEN IT WAS WRITTEN.** `docs/workflows.md` carried five
`dossier deltas` commands -- `list`, `create`, `advance`, `link`, `show` -- in a
runnable block. None had ever been built. The phase they were "coming in" had
shipped with a different set of verbs entirely, and the page documented neither
the ones that exist nor the fact that these did not.

WHAT COUNTS AS A CLAIM, and each exclusion is here because including it
produced a false reading:

  * **fenced blocks only.** Inline code carries prose -- "the `dossier` files
    with a version" read as a command called `files`;
  * **not comment lines.** `# Export dossier files with version info` is a
    sentence that happens to sit in a bash block;
  * **the line must start with the command**, because that is what a reader
    copies.

And resolution goes through `click`'s own lookup rather than `cli.commands`,
because `tui` is registered lazily -- importing it would pull in trogon on
every invocation, which a stated requirement (very underpowered hardware)
does not allow. Reading the dict directly reported `dossier tui` as missing
from four pages that correctly name it.

THE MUTATION, per P16, quoted as it printed. Restoring the delta block to the
five commands that never existed:

    AssertionError: docs/workflows.md tells a reader to run
    `dossier deltas advance`, and `deltas` has no `advance`
"""

from __future__ import annotations

import re
from pathlib import Path

import click
import pytest

from dossier.cli import cli

ROOT = Path(__file__).resolve().parent.parent.parent
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md")),
         *sorted((ROOT / "walkthrough").glob("*.md"))]

FENCE = re.compile(r"```.*?```", re.DOTALL)
CLAIM = re.compile(
    r"^[ \t]*(?:\$ )?(?:uv run )?dossier ((?:[a-z][a-z-]*)(?:\s+[a-z][a-z-]*)?)",
    re.MULTILINE)
WORD = re.compile(r"^[a-z][a-z-]*$")

# Commands the docs name on purpose that this CLI does not provide.
# **Named rather than skipped**: a gate that quietly excluded them would be a
# green check standing where a reader believes every documented command works.
NOT_OURS = {
    # `docs/extending.md` shows what installing a community plugin would add:
    # "Plugin auto-registers commands". The point of the example is that this
    # command is *not* in core.
    "gitlab",
}


def runnable_lines(text: str) -> str:
    kept: list[str] = []
    for block in FENCE.findall(text):
        for line in block.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith("```"):
                continue
            kept.append(line)
    return "\n".join(kept)


def claims() -> list[tuple[Path, str]]:
    found = []
    for page in PAGES:
        if not page.is_file():
            continue
        body = runnable_lines(page.read_text(encoding="utf-8", errors="replace"))
        for match in CLAIM.finditer(body):
            parts = [p for p in match.group(1).split() if WORD.match(p)]
            if parts:
                found.append((page, " ".join(parts)))
    return found


def resolves(claim: str) -> str | None:
    """`None` if the claim resolves, otherwise what is missing."""
    ctx = click.Context(cli)
    parts = claim.split()
    group = cli.get_command(ctx, parts[0])
    if group is None:
        return f"`{parts[0]}` is not a command"
    if len(parts) == 1:
        return None
    if not isinstance(group, click.Group):
        # A plain command; whatever follows is its arguments, and whether it
        # accepts them is that command's business rather than this check's.
        return None
    if group.get_command(ctx, parts[1]) is None:
        return f"`{parts[0]}` has no `{parts[1]}`"
    return None


def test_the_scan_finds_something():
    """A scan that matched nothing would pass every test below it."""
    found = claims()

    assert len(found) > 40, f"only {len(found)} claims found; the scan is broken"
    assert any(claim.startswith("github") for _, claim in found)


def test_every_documented_command_resolves():
    """THE ONE THIS EXISTS FOR."""
    broken = []
    for page, claim in claims():
        if claim.split()[0] in NOT_OURS:
            continue
        problem = resolves(claim)
        if problem:
            broken.append(
                f"{page.relative_to(ROOT).as_posix()} tells a reader to run "
                f"`dossier {claim}`, and {problem}")

    assert not broken, "\n".join(broken)


def test_the_lazily_registered_explorer_is_reachable():
    """`tui` is registered only when something asks for it.

    Four pages name it, and a check reading `cli.commands` directly called all
    four wrong -- which is why `resolves` goes through click.

    **The absence is deliberately not asserted here.** `get_command` caches the
    explorer into `cli.commands` the first time anybody looks, so "it is not in
    the dict yet" is true only until some other test in this session resolves
    it. Asserting that would be asserting test order, and this suite runs in a
    random one.
    """
    assert resolves("tui") is None


@pytest.mark.parametrize("name", sorted(NOT_OURS))
def test_nothing_is_exempted_that_this_cli_actually_has(name: str):
    """An exemption that stopped being true is a hole nobody can see."""
    assert cli.get_command(click.Context(cli), name) is None, (
        f"`{name}` resolves now. Delete it from NOT_OURS -- an exemption for a "
        f"command that works reads as a gap that is still open.")


def test_prose_in_a_fence_is_not_read_as_a_command():
    """The exclusion that took three attempts to get right.

    Every line here read as a broken command at some point in writing this.
    """
    body = runnable_lines(
        "```bash\n"
        "# Export dossier files with version info\n"
        "uv run dossier export show owner/repo\n"
        "```\n"
        "Some prose about `dossier` files with versions.\n")

    assert "export show" in body
    assert "files with" not in body


# --- the other half of a page being true: where it sends you --------------------


LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)")


def internal_links() -> list[tuple[Path, str]]:
    """Every link in these pages that points at a file rather than the web."""
    found = []
    for page in PAGES:
        if not page.is_file():
            continue
        text = page.read_text(encoding="utf-8", errors="replace")
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            found.append((page, target))
    return found


def test_the_link_scan_finds_something():
    """A scan that matched nothing would pass the test below it."""
    assert len(internal_links()) > 40


def test_every_link_points_at_a_file_that_exists():
    """**A DEAD LINK ON THE FRONT DOOR IS THE FIRST THING A READER MEETS.**

    `docs/index.md` offered "Analysis & Consolidation" in its Quick Links
    table. `git log --all` has no record of that file ever being committed, so
    the row had pointed at nothing since the day it was written -- on the page
    that exists to send people somewhere.

    Mutation, quoted as it printed: restoring that row.

        AssertionError: docs/index.md links to ANALYSIS_AND_CONSOLIDATION.md,
        which is not a file
    """
    broken = []
    for page, target in internal_links():
        if not (page.parent / target).exists():
            broken.append(
                f"{page.relative_to(ROOT).as_posix()} links to {target}, "
                f"which is not a file")

    assert not broken, "\n".join(broken)


def test_the_executable_walkthrough_is_reachable_from_the_docs_front_door():
    """The two halves of this documentation have different guarantees.

    `walkthrough/` is executed by the ordinary test command -- `testpaths =
    ["tests", "walkthrough"]` -- so an example that stops being true fails the
    build. `docs/` is hand-written prose. The README linked the executable
    half and `docs/index.md` did not, so a reader who started at the docs
    never found the pages that cannot lie to them.
    """
    index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    assert "walkthrough/" in index, (
        "the docs front door does not offer the executable walkthrough")
