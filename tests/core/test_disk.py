"""The disk group's red paths, and the properties that make it safe to wrap.

dossier does not measure a disk or decide what may be deleted -- the corpus
does both. That claim is the whole point of the module, so most of what follows
asserts an *absence*: no measurement code, no second definition of a threshold,
no way to make deletion the default.

The rest are states that must not be reported as fine: a checkout without the
tooling, a document that was never written, a target nobody could measure. Per
the project's own standard, every signal has a fixture in which it reports bad;
each of these was confirmed to go red against the code it names before being
kept.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from tests import structural
from tests.structural import calls_of, imports_of
from dossier import disk
from dossier.cli import cli

CORPUS_TOOLS = (*disk.TOOLS.values(), disk.POLICY)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def fake_corpus(root: Path, script_body: str = "import sys\nsys.exit(0)\n") -> Path:
    """A checkout carrying stand-in disk tooling.

    Stand-ins rather than the real scripts: what is under test here is how
    dossier drives them and reports what comes back, and a fixture that walked
    a real filesystem would measure the machine running the suite.
    """
    (root / "ci").mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    for name in disk.TOOLS.values():
        (root / name).write_text(script_body, encoding="utf-8")
    (root / disk.POLICY).write_text("schema: 1\nreclaimers: []\n", encoding="utf-8")
    return root


# --- dossier adds no second definition of anything -------------------------


# The structural helpers live in tests/structural.py -- one definition rather
# than one per test module, since three copies had already appeared.


def test_dossier_measures_no_disk_fact_of_its_own() -> None:
    """The claim this module exists to make, asserted structurally.

    Parsed rather than grepped: the docstring explaining that this module walks
    no directory necessarily contains the words for walking one, so a text scan
    fails on the documentation and would pass on a module that deleted the
    prose and added the call.
    """
    assert not calls_of(disk) & {"walk", "disk_usage", "iterdir", "rmtree", "glob"}
    assert "shutil" not in imports_of(disk)


def test_no_threshold_or_tier_ordering_is_restated_here() -> None:
    """A rule stated in two places is a rule that gets edited in one.

    Two structural facts, not a word scan -- the recipes below are prose about
    thresholds and tiers, and a grep for those words matches the explanation
    rather than a second implementation of it:

    * No float literal anywhere. Every threshold in this system is a fraction
      in ci/disk-policy.yaml; one appearing here would be a second definition
      that nobody would think to keep in step.
    * No `.index(` call. That is how the corpus reclaimer turns a tier name
      into a ratchet, and reimplementing the ordering here is precisely how a
      wrapper ends up permitting a tier the corpus would not.
    """
    tree = ast.parse(Path(disk.__file__).read_text(encoding="utf-8"))
    floats = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]
    assert not floats, f"threshold-shaped literals in disk.py: {floats}"
    assert "index" not in calls_of(disk)


def test_the_read_and_render_path_still_runs_no_commands() -> None:
    """The corpus's rule is that a renderer may not run a command.

    dossier keeps it by putting every shell-out in corpus.py and disk.py, both
    imported only by the CLI. This is the same assertion test_governance.py
    makes, extended to cover the module the disk group added.
    """
    from dossier import governance as gov

    assert not structural.runs_commands(gov), (
        "asserted structurally: this module's docstring names subprocess while "
        "explaining the rule, so a text scan fails on the explanation"
    )


# --- a checkout that cannot run the tooling says so ------------------------


def test_a_missing_directory_is_a_reason_not_an_exception(tmp_path: Path) -> None:
    reason = disk.can_measure(tmp_path / "nowhere")
    assert reason and "does not exist" in reason


def test_a_checkout_without_the_tooling_names_what_is_absent(tmp_path: Path) -> None:
    """The vendored governance/qm case: empty by construction, not broken.

    Naming the files is the difference between a reader fixing their command
    and a reader filing a bug against the corpus.
    """
    (tmp_path / "ci").mkdir()
    reason = disk.can_measure(tmp_path)
    assert reason
    assert "ci/disk_status.py" in reason
    assert "branch without the disk tooling" in reason


def corpus_checkout() -> Path:
    """The corpus this repository can actually reach.

    Preferring a sibling checkout and skipping without one made these tests
    depend on how somebody arranged their directories. In a fresh clone they
    skipped -- and a skipped test blocks a version tag, because a test that
    skips contributes nothing to the automated-validation claim. The clone
    always carries the corpus as a submodule at `governance/qm`, so there is a
    copy to read whatever else is on the machine.
    """
    from tests.structural import repo_root

    sibling = repo_root().parent / "qm"
    if (sibling / disk.TOOLS["reclaim"]).exists():
        return sibling
    return repo_root() / "governance" / "qm"


def test_a_complete_checkout_is_permitted(tmp_path: Path) -> None:
    assert disk.can_measure(fake_corpus(tmp_path)) is None


def test_the_real_corpus_beside_this_one_carries_the_tooling() -> None:
    """The path a developer here actually hits, rather than only a fixture.

    Skipped rather than failed when the sibling checkout is on a branch without
    the tooling: that is a true state of somebody's machine, not a defect in
    this suite.
    """
    root = corpus_checkout()
    assert disk.can_measure(root) is None, disk.can_measure(root)
    assert all((root / name).exists() for name in CORPUS_TOOLS)


# --- the document is machine-scoped, in both repositories ------------------


def test_the_document_lives_outside_every_repository() -> None:
    # The claim is the one in the name. Pinning the literal `~/.dossier` made
    # this fail the moment the state directory became overridable for tests --
    # asserting the implementation rather than the property it exists for.
    from dossier.config import dossier_home

    assert disk.document_path().parent == dossier_home()
    assert disk.inside_a_repository(disk.document_path()) is None


def test_a_path_inside_a_repository_is_recognised(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "docs" / "disk-status.json"
    assert disk.inside_a_repository(nested) == tmp_path.resolve()


def test_writing_the_document_into_a_repository_is_refused(tmp_path: Path) -> None:
    """The corpus guards its own repository; dossier is a second one.

    A guard that stopped at the boundary between them would let the document
    land in whichever repository was not doing the checking.
    """
    corpus = fake_corpus(tmp_path / "corpus")
    (tmp_path / "project" / ".git").mkdir(parents=True)
    doomed = tmp_path / "project" / "disk-status.json"

    outcome = disk.measure(corpus, document=doomed)

    assert not outcome.ran
    assert outcome.reason and "inside the repository" in outcome.reason
    assert not doomed.exists()


def test_the_refusal_happens_before_the_walk(tmp_path: Path) -> None:
    """Walking a hundred gigabytes and then rejecting the destination wastes
    exactly the minutes that made somebody reach for the tool."""
    corpus = fake_corpus(
        tmp_path / "corpus",
        script_body="import pathlib\npathlib.Path('RAN').write_text('x')\n",
    )
    (tmp_path / "project" / ".git").mkdir(parents=True)

    disk.measure(corpus, document=tmp_path / "project" / "disk-status.json")

    assert not (corpus / "RAN").exists(), "the generator ran before the check"


# --- exit status is the corpus's, unmodified -------------------------------


@pytest.mark.parametrize("status", [0, 1, 2])
def test_check_carries_the_corpus_exit_status_through(tmp_path: Path, status: int) -> None:
    """2 is critical and 1 is low. A wrapper that collapsed them to "failed"
    would report a full disk and a warm one identically."""
    corpus = fake_corpus(tmp_path, script_body=f"import sys\nsys.exit({status})\n")
    assert disk.check(corpus).status == status


def test_a_tool_that_cannot_be_launched_is_reported_not_raised(tmp_path: Path) -> None:
    corpus = fake_corpus(tmp_path)
    (corpus / disk.TOOLS["status"]).unlink()
    outcome = disk._run(corpus, disk.TOOLS["status"], [])
    assert outcome.status != 0
    assert not outcome.ok


def test_a_hanging_tool_times_out_rather_than_wedging(tmp_path: Path) -> None:
    corpus = fake_corpus(
        tmp_path, script_body="import time\ntime.sleep(30)\n"
    )
    outcome = disk._run(corpus, disk.TOOLS["status"], [], timeout=1)
    assert outcome.ran and outcome.status is None
    assert outcome.reason and "timed out" in outcome.reason


def test_rendering_a_document_that_was_never_written_says_so(tmp_path: Path) -> None:
    """Not an empty page, which would read as a machine with room on it."""
    outcome = disk.render(fake_corpus(tmp_path), document=tmp_path / "absent.json")
    assert not outcome.ran
    assert outcome.reason and "measure first" in outcome.reason


# --- the dry run survives the wrapper --------------------------------------


def test_reclaim_defaults_to_a_dry_run(tmp_path: Path) -> None:
    """Asserted on the argv actually built, not on the signature.

    A default that is correct in the signature and discarded when the command
    line is assembled is the failure this guards against.
    """
    corpus = fake_corpus(
        tmp_path,
        script_body="import sys\nprint(' '.join(sys.argv[1:]))\n",
    )
    assert "--apply" not in disk.reclaim(corpus).stdout


def test_apply_is_passed_only_when_asked_for(tmp_path: Path) -> None:
    corpus = fake_corpus(
        tmp_path,
        script_body="import sys\nprint(' '.join(sys.argv[1:]))\n",
    )
    assert "--apply" in disk.reclaim(corpus, apply=True).stdout


def test_the_cheapest_tier_is_the_default_on_this_side_too(tmp_path: Path) -> None:
    """Both defaults are load-bearing and the duplication is deliberate."""
    corpus = fake_corpus(
        tmp_path,
        script_body="import sys\nprint(' '.join(sys.argv[1:]))\n",
    )
    assert "--allow refetched" in disk.reclaim(corpus).stdout


def test_the_corpus_reclaimer_also_defaults_to_a_dry_run() -> None:
    """The other half of the pair. If the corpus ever flips its default, the
    wrapper's caution becomes decorative and this is where that is noticed."""
    reclaimer = corpus_checkout() / disk.TOOLS["reclaim"]
    result = subprocess.run(
        [sys.executable, str(reclaimer), "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert "Without it nothing is removed" in result.stdout


# --- the cookbook is one source with two surfaces --------------------------


def test_the_committed_docs_page_matches_the_recipes() -> None:
    """The drift check, and the reason the page can be trusted.

    A cookbook that describes last month's flags confidently is worse than no
    cookbook: the reader stops checking. Editing docs/disk.md by hand fails
    here rather than diverging silently.
    """
    page = Path("docs/disk.md")
    assert page.exists(), "docs/disk.md is not committed"
    expected = disk.cookbook_markdown()
    assert page.read_text(encoding="utf-8") == expected, (
        "docs/disk.md is out of step with dossier.disk.COOKBOOK. "
        "Regenerate: dossier disk cookbook --markdown > docs/disk.md"
    )


def test_the_page_says_it_is_generated_and_how() -> None:
    """A reader who does not know it is generated edits it, and is surprised."""
    page = Path("docs/disk.md").read_text(encoding="utf-8")
    assert page.startswith("<!-- Generated from dossier.disk.COOKBOOK")
    assert "dossier disk cookbook --write docs/disk.md" in page


def test_the_page_carries_no_byte_order_mark() -> None:
    """PowerShell's `>` writes one and every other platform does not.

    The page would then differ from what the generator produces depending on
    who last regenerated it, and the drift test would fail for a reason with
    nothing to do with the recipes. `--write` exists to avoid this.
    """
    assert not Path("docs/disk.md").read_bytes().startswith(b"\xef\xbb\xbf")


def test_every_recipe_reaches_both_surfaces() -> None:
    markdown = disk.cookbook_markdown()
    for recipe in disk.COOKBOOK:
        assert recipe.task in markdown
        assert recipe.command in markdown


def test_every_recipe_states_when_to_reach_for_it() -> None:
    """A command with no occasion attached is a command nobody runs."""
    for recipe in disk.COOKBOOK:
        assert recipe.when.strip(), recipe.task
        assert recipe.command.strip(), recipe.task


def test_the_cookbook_covers_the_two_expected_failures() -> None:
    """Both are states a reader will hit and read as a bug: the vendored corpus
    with no ci/, and a cp1252 console raising on the corpus's em dashes."""
    tasks = " ".join(r.task + " " + (r.note or "") for r in disk.COOKBOOK)
    assert "no disk tooling" in tasks
    assert "UnicodeEncodeError" in tasks


def test_the_terminal_cookbook_is_ascii_only() -> None:
    """A cp1252 console raises on anything else, and the recipe explaining
    that failure must not be the thing that triggers it."""
    for recipe in disk.COOKBOOK:
        for field in (recipe.task, recipe.command, recipe.when, recipe.note or ""):
            assert field.isascii(), f"{recipe.task}: {field!r}"


# --- the CLI wiring ---------------------------------------------------------


def test_the_disk_group_lists_its_commands(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["disk", "--help"])
    assert result.exit_code == 0
    for name in ("check", "status", "reclaim", "cookbook"):
        assert name in result.output


def test_the_cookbook_command_prints_the_recipes(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["disk", "cookbook"])
    assert result.exit_code == 0
    assert disk.COOKBOOK[0].task in result.output
    assert disk.COOKBOOK[0].command in result.output


def test_the_cookbook_command_regenerates_the_committed_page(runner: CliRunner) -> None:
    """The command named in the drift message actually produces the page.

    Compares **stdout**, not `result.output`, which merges stderr in. The page
    is what a `> docs/disk.md` redirect captures, so stdout is the stream under
    test; diagnostics on stderr are correct and must not fail this. Asserting
    against the merged stream made this red as soon as a note was added to the
    group callback, while the redirect it describes was still producing a
    clean page.
    """
    result = runner.invoke(cli, ["disk", "cookbook", "--markdown"])
    assert result.exit_code == 0
    assert result.stdout == disk.cookbook_markdown()
    # And the page itself never carries a diagnostic, whatever else is emitted.
    assert "note:" not in result.stdout


def test_a_corpus_without_the_tooling_exits_and_explains(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Never a silent no-op, and never an empty table."""
    (tmp_path / "ci").mkdir()
    result = runner.invoke(cli, ["disk", "check", "--corpus-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "cannot run the disk tooling" in result.output


def test_the_resolved_corpus_is_always_printed(runner: CliRunner, tmp_path: Path) -> None:
    """An implicit choice that stays silent is how a reader ends up looking at
    a different repository than the one they think they are."""
    corpus = fake_corpus(tmp_path)
    result = runner.invoke(cli, ["disk", "check", "--corpus-dir", str(corpus)])
    assert "corpus " in result.output
    assert str(corpus) in result.output
    assert "given with --corpus-dir" in result.output


def test_reclaim_help_leads_with_the_dry_run(runner: CliRunner) -> None:
    """The first example a reader copies should be the one that deletes
    nothing."""
    result = runner.invoke(cli, ["disk", "reclaim", "--help"])
    assert result.exit_code == 0
    first = result.output.index("dossier disk reclaim  ")
    applied = result.output.index("--apply")
    assert first < applied
    assert "a dry run, always" in result.output
