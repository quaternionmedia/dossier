"""Recipes that name commands which exist, and say where the person is.

**A COOKBOOK IS READ BY SOMEBODY WHO IS ABOUT TO TYPE WHAT IT SAYS**, which
makes a wrong command worse than no page: it costs a reader the time to find out
it is wrong, and it spends the credibility of every recipe beside it. So the two
things asserted here are that every command exists, and that every workflow is
honest about where it stops for a person.
"""

from __future__ import annotations

from pathlib import Path

import click
import pytest

from dossier import cookbook

PAGE = Path("docs/cookbook.md")
HERE = Path(".")


# --- the person --------------------------------------------------------------


def test_every_workflow_says_where_the_person_is():
    """THE ONE THIS EXISTS FOR.

    A workflow with no gate may be right -- most of `Start a slice` is reading
    -- but "no decision happens here" is a claim, and an unstated one is
    indistinguishable from a gate somebody forgot to write.

    Mutation: remove `why_no_gate` from a gateless workflow and this fails.
    """
    silent = [w.name for w in cookbook.WORKFLOWS
              if not w.gates and not w.why_no_gate.strip()]
    assert not silent, f"no gate and no reason: {silent}"


def test_every_gate_says_what_is_being_decided():
    """A gate that says stop without saying what you are deciding is a pause,
    not a gate.

    Mutation: blank a gate's `decides` and this fails.
    """
    for workflow in cookbook.WORKFLOWS:
        for gate in workflow.gates:
            assert gate.decides.strip(), f"{workflow.name}: {gate.does}"
            assert len(gate.decides) > 40, (
                f"{workflow.name}: {gate.does!r} -- the decision is a label")


def test_a_reason_for_no_gate_is_a_reason_and_not_a_label():
    for workflow in cookbook.WORKFLOWS:
        if workflow.why_no_gate:
            assert len(workflow.why_no_gate) > 60, workflow.name


# --- the commands --------------------------------------------------------------


def _leaf_paths() -> set[tuple[str, ...]]:
    """Every command path the CLI answers to, groups included."""
    from dossier.cli import cli

    found: set[tuple[str, ...]] = set()

    def walk(node, prefix=()):
        for name in node.list_commands(None):
            here = (*prefix, name)
            found.add(here)
            child = node.get_command(None, name)
            if isinstance(child, click.Group):
                walk(child, here)

    walk(cli)
    return found


def _dossier_calls():
    for workflow in cookbook.WORKFLOWS:
        for step in workflow.steps:
            for line in (step.command, step.in_project):
                for piece in line.split("&&"):
                    words = piece.split()
                    if words and words[0] == "dossier":
                        yield workflow.name, tuple(words[1:])


def test_every_dossier_command_in_a_recipe_exists():
    """THE OTHER ONE THIS EXISTS FOR.

    A recipe naming a command that was renamed is a page that looks maintained
    and is not. Checked against `cli.list_commands` rather than a list here,
    which would be the same copy one layer down.

    Mutation: change any `dossier ...` line to a command that does not exist
    and this fails.
    """
    known = _leaf_paths()
    wrong = []
    for name, words in _dossier_calls():
        # Longest prefix of real command names; the rest are arguments.
        depth = 0
        while depth < len(words) and tuple(words[:depth + 1]) in known:
            depth += 1
        if depth == 0:
            wrong.append((name, " ".join(words)))
    assert not wrong, f"recipes name commands that do not exist: {wrong}"


def test_every_script_a_recipe_names_is_in_this_checkout():
    """The project-repository form runs the seed scripts in place, and a path
    that moved is a recipe that dies at the shell.

    Mutation: point an `in_project` command at a path that is not there and
    this fails.
    """
    missing = []
    for workflow in cookbook.WORKFLOWS:
        for step in workflow.steps:
            for word in step.in_project.split():
                if word.startswith("governance/") and not (HERE / word).exists():
                    missing.append((workflow.name, word))
    assert not missing, f"named but not in this checkout: {missing}"


def test_the_page_never_offers_the_corpus_cli_without_saying_so():
    """THE HOLE IN THE GUARD BELOW, FOUND BY TRYING TO ROUTE AROUND IT.

    The step-level check reads `Step.command`, and the page's TL;DR is written
    in the renderer -- so the summary a reader copies first offered four
    `uv run qm` lines that do not exist in the repository the page ships in,
    and the guard could not see them.

    Every `uv run qm` on the page now sits inside the paragraph that says the
    CLI is the corpus repository's, or beside its `in_project` form.

    Mutation: put a bare `uv run qm` line in the TL;DR block and this fails.
    """
    rendered = cookbook.as_markdown()
    head = rendered[:rendered.index("## Worked through")]
    fenced = [line for block in head.split("```")[1::2]
              for line in block.splitlines()
              if line.strip().startswith("uv run qm")]
    assert not fenced, f"the summary offers a command that is not here: {fenced}"
    assert "the CLI exists there and nowhere else" in head


def test_the_qm_cli_is_never_the_only_form_offered():
    """**`uv run qm` DOES NOT EXIST IN A PROJECT REPOSITORY.** A fork runs the
    seed scripts in place and installs nothing, so a step offering only the
    CLI form is a command most readers cannot run.

    Mutation: drop an `in_project` from a `uv run qm` step and this fails.
    """
    alone = [(w.name, s.does) for w in cookbook.WORKFLOWS for s in w.steps
             if s.command.startswith("uv run qm") and not s.in_project]
    assert not alone, f"only the corpus form is offered: {alone}"


# --- composition ---------------------------------------------------------------


def test_composition_names_workflows_that_exist():
    """`follows` and `feeds` are the whole reason these are composable, and a
    name with a typo composes with nothing.

    Mutation: misspell a name in `feeds` and this fails.
    """
    dangling = []
    for workflow in cookbook.WORKFLOWS:
        for other in (*workflow.follows, *workflow.feeds):
            if other not in cookbook.BY_NAME:
                dangling.append((workflow.name, other))
    assert not dangling, f"composes with nothing: {dangling}"


def test_composition_is_not_a_workflow_pointing_at_itself():
    for workflow in cookbook.WORKFLOWS:
        assert workflow.name not in workflow.follows
        assert workflow.name not in workflow.feeds


# --- the page ------------------------------------------------------------------


def test_a_sketch_is_marked_rather_than_hidden():
    """A cookbook showing only the finished recipes reads as the whole of what
    a person needs.

    Mutation: render sketches beside the worked ones with no heading and this
    fails.
    """
    assert any(w.state == cookbook.STUB for w in cookbook.WORKFLOWS)
    rendered = cookbook.as_markdown()
    assert "## Sketches" in rendered
    for workflow in cookbook.WORKFLOWS:
        if workflow.state == cookbook.STUB:
            assert rendered.index("## Sketches") < rendered.index(
                f"### {workflow.name}"), f"{workflow.name} is not under it"


def test_the_page_counts_what_it_holds_rather_than_stating_it():
    """Durable text carries as few integers as it can, and the ones it carries
    are read from the thing they describe.

    Mutation: type the totals into the page and this fails as soon as a
    workflow is added.
    """
    rendered = cookbook.as_markdown()
    assert f"**{len(cookbook.WORKFLOWS)}** workflows" in rendered
    gated = [w for w in cookbook.WORKFLOWS if w.gates]
    assert f"**{len(gated)}** of which stop for a person" in rendered


def test_the_page_is_recorded():
    """P12: it rides the ordinary test command, so a run leaves it current."""
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    rendered = cookbook.as_markdown()
    PAGE.write_text(rendered, encoding="utf-8")

    assert PAGE.stat().st_size > 0
    for workflow in cookbook.WORKFLOWS:
        assert f"### {workflow.name}" in rendered


def test_a_gate_reads_as_a_gate_on_the_page():
    """The whole point is that a reader can see where they stop.

    Mutation: render a gate as an ordinary numbered step and this fails.
    """
    rendered = cookbook.as_markdown()
    assert "**You decide:**" in rendered
    gates = sum(len(w.gates) for w in cookbook.WORKFLOWS)
    assert rendered.count("**You decide:**") == gates


@pytest.mark.parametrize("workflow", cookbook.WORKFLOWS,
                         ids=[w.name for w in cookbook.WORKFLOWS])
def test_a_workflow_states_an_intent_and_not_a_restatement_of_its_name(workflow):
    assert workflow.intent.strip()
    assert workflow.intent.lower() != workflow.name.lower()
    assert len(workflow.intent) > 40, f"{workflow.name}: the intent is a label"
    assert workflow.steps, f"{workflow.name} has no steps"
