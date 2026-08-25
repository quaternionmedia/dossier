"""One window onto the corpus's capability registry, and what it declines to say.

**THE VOCABULARY IS NOT TESTED HERE.** The four rungs and what each declines to
claim belong to `governance/qm`, and `ci/capabilities.py` in that corpus tests
them. What is tested here is that this window reads the file faithfully and adds
nothing: a rung that meant something different in dossier than in codecarto
would give two readings of one estate.

THE MUTATIONS, per P16, quoted as they printed:

An absent registry returning an empty `Reading` rather than a reason:

    AssertionError: a corpus pin predating the registry read as an estate with
    no capabilities
    assert True is False

`pointer` returning "" rather than UNKNOWN for a null:

    AssertionError: assert '' == 'unknown'

`reached` returning every rung for an unreadable phase:

    AssertionError: an unreadable phase reached every rung
    assert ('design', 'deployment', 'execution', 'monitoring') == ()
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dossier import capabilities as mod


def corpus(tmp_path: Path, body: str) -> Path:
    """A corpus checkout holding one registry."""
    path = tmp_path / "ci" / "capability-registry.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


ONE = """\
    schema: 1
    capabilities:
      - id: a/thing
        title: A thing
        repo: owner/repo
        phase: execution
        stated_by: Somebody
        stated_on: 2026-08-25
        what: It does a thing.
        evidence:
          design: records/DRAFT-x.md
          deployment: uv run thing
          execution: owner/repo/delta/x
          monitoring: null
        cannot_see: Whether it is any good.
    """


# --- what it declines to read ---------------------------------------------------


def test_an_absent_registry_is_a_reason_and_not_an_empty_estate(tmp_path: Path):
    """THE ONE THAT MATTERS.

    A submodule pinned before the registry existed is the ordinary case while
    this is new. Reading it as "no capabilities declared" would render a corpus
    nobody could measure exactly like a well-governed one.
    """
    reading = mod.read(tmp_path)

    assert reading.readable is False, (
        "a corpus pin predating the registry read as an estate with no "
        "capabilities")
    assert "pin may predate it" in reading.reason
    assert reading.capabilities == ()


def test_an_empty_registry_is_not_an_absent_one(tmp_path: Path):
    """Readable and declaring nothing is a different fact, and it says so."""
    root = corpus(tmp_path, "schema: 1\ncapabilities: []\n")
    reading = mod.read(root)

    assert reading.readable
    assert reading.capabilities == ()
    assert "not an estate with no capabilities" in mod.render(reading)


def test_a_registry_that_does_not_parse_says_so(tmp_path: Path):
    root = corpus(tmp_path, "capabilities: [unclosed\n")
    reading = mod.read(root)

    assert not reading.readable
    assert "did not parse" in reading.reason


def test_a_row_with_no_id_is_dropped_rather_than_named(tmp_path: Path):
    """The same rule the harness queue applies: a row that cannot be named
    cannot be matched to itself next time, and an invented identity is worse."""
    root = corpus(tmp_path, """\
        capabilities:
          - title: Nameless
            phase: design
        """)

    assert mod.read(root).capabilities == ()


# --- reading one declaration faithfully -----------------------------------------


def test_a_declaration_is_carried_verbatim(tmp_path: Path):
    one = mod.read(corpus(tmp_path, ONE)).capabilities[0]

    assert one.id == "a/thing"
    assert one.repo == "owner/repo"
    assert one.phase == "execution"
    assert one.pointer("deployment") == "uv run thing"


def test_a_null_rung_reads_as_unknown_and_never_as_false(tmp_path: Path):
    one = mod.read(corpus(tmp_path, ONE)).capabilities[0]

    assert one.pointer("monitoring") == mod.UNKNOWN
    assert one.pointer("nonsense") == mod.UNKNOWN


def test_the_rungs_below_a_claim_are_the_claim_and_everything_under_it(
        tmp_path: Path):
    one = mod.read(corpus(tmp_path, ONE)).capabilities[0]

    assert one.reached == ("design", "deployment", "execution")
    assert one.unclaimed == ("monitoring",)


def test_an_unreadable_phase_reaches_nothing_rather_than_everything(
        tmp_path: Path):
    root = corpus(tmp_path, """\
        capabilities:
          - id: a/thing
            phase: shipped
        """)
    one = mod.read(root).capabilities[0]

    assert one.reached == (), "an unreadable phase reached every rung"
    assert one.known_phase is False


def test_an_unreadable_phase_is_grouped_rather_than_dropped(tmp_path: Path):
    """Dropping it would make the estate look smaller and tidier than it is."""
    root = corpus(tmp_path, """\
        capabilities:
          - id: a/thing
            phase: shipped
        """)

    grouped = mod.read(root).by_phase()

    assert [c.id for c in grouped[mod.UNKNOWN]] == ["a/thing"]


# --- the gap, which is the thing worth rendering --------------------------------


def test_a_claim_above_an_unevidenced_rung_is_reported_as_a_gap(tmp_path: Path):
    """The corpus's own check refuses this, so a registry that passed its gate
    has none. Computed anyway: this window may be pointed at an older pin, and
    reporting a gap it cannot explain beats rendering a ladder with a hole."""
    root = corpus(tmp_path, """\
        capabilities:
          - id: a/thing
            title: A thing
            repo: owner/repo
            phase: execution
            evidence:
              design: records/DRAFT-x.md
              execution: owner/repo/delta/x
        """)
    one = mod.read(root).capabilities[0]

    assert one.unevidenced == ("deployment",)
    assert "GAP: claims execution" in mod.render(mod.read(root))


def test_a_complete_ladder_reports_no_gap(tmp_path: Path):
    reading = mod.read(corpus(tmp_path, ONE))

    assert reading.capabilities[0].unevidenced == ()
    assert "GAP" not in mod.render(reading)


def test_asking_for_gaps_when_there_are_none_does_not_claim_the_pointers_are_true(
        tmp_path: Path):
    """**THE SENTENCE THAT STOPS A CLEAN RESULT READING AS A VERIFIED ONE.**"""
    text = mod.render(mod.read(corpus(tmp_path, ONE)), only_gaps=True)

    assert "not evidence" in text


# --- what a person reads ---------------------------------------------------------


def test_the_rendering_says_a_pointer_is_not_a_finding(tmp_path: Path):
    text = mod.render(mod.read(corpus(tmp_path, ONE)))

    assert "where to look, never what was found" in text
    assert "runs no command" in text


def test_the_rendering_is_ascii_so_a_cp1252_console_can_print_it(tmp_path: Path):
    """The same failure `dossier.cli._make_output_encodable` documents."""
    mod.render(mod.read(corpus(tmp_path, ONE))).encode("cp1252")


def test_this_window_agrees_with_the_corpus_about_the_rungs():
    """Two windows onto one file must not disagree about its vocabulary.

    Asserted against the corpus checkout when one is present. Skipped rather
    than guessed at when it is not -- a test that quietly passed without the
    corpus would be asserting this module against itself.
    """
    pytest.importorskip("yaml")
    corpus_file = (Path(mod.DEFAULT_CORPUS_DIR) / "ci" / "capabilities.py")
    if not corpus_file.is_file():
        pytest.skip("no corpus checkout at this pin carries ci/capabilities.py")

    source = corpus_file.read_text(encoding="utf-8")
    for rung in mod.RUNGS:
        assert f'"{rung}"' in source, f"{rung} is not a rung in the corpus"
