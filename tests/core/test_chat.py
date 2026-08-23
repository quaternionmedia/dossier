"""Reading one archived conversation.

**NO REAL ARCHIVE MATERIAL APPEARS IN THIS FILE.** The thread archive carries
conversation titles, session identifiers and repository names the organisation
has decided must never be published, and a test fixture is published the moment
it is committed. Every conversation here is invented, and the shapes are what is
under test, not the words.
"""

from __future__ import annotations

import json

import pytest

from dossier import chat, threads


def conversation(**over) -> threads.Conversation:
    found = dict(
        reachable=True, where="http://127.0.0.1:3141/v1/threads/claude/abc",
        source="claude", identifier="abc", title="Deciding the port allocation",
        started_at="2026-08-01T09:00:00Z", partial=False,
        turns=[
            {"id": "t1", "role": "user", "at": "09:00", "text": "which port?"},
            {"id": "t2", "role": "assistant", "at": "09:01", "text": "three of them"},
        ],
    )
    found.update(over)
    return threads.Conversation(**found)


# --- who is speaking ----------------------------------------------------------


@pytest.mark.parametrize("role, shown", [
    ("user", "you"), ("human", "you"), ("USER", "you"),
    ("assistant", "it"), ("model", "it"), ("Assistant", "it"),
    ("system", "system"), ("tool", "tool"),
])
def test_a_role_becomes_one_word(role: str, shown: str):
    """Exporters disagree about capitalisation, and about whether the machine is
    `assistant` or `model`. Showing both raw would look like two speakers."""
    assert chat.speaker(role) == shown


def test_an_unknown_role_is_not_filed_under_the_machine():
    """THE ONE THAT MATTERS for this function.

    An exporter's new role must read as unknown rather than being quietly
    attributed to somebody. Filing it under `it` would put words in the
    machine's mouth, and nothing downstream could tell.

    Mutation: default to `it` instead of `?` and this fails.
    """
    assert chat.speaker("orchestrator") == chat.UNKNOWN_SPEAKER
    assert chat.speaker("") == chat.UNKNOWN_SPEAKER


# --- the transcript -----------------------------------------------------------


def test_every_turn_is_numbered_and_attributed():
    drawn = chat.draw(conversation())
    assert "  1  you" in drawn.text()
    assert "  2  it" in drawn.text()


def test_a_turn_with_no_text_is_drawn_rather_than_skipped():
    """**SKIPPING IT WOULD SILENTLY RENUMBER EVERY TURN AFTER IT.** A turn that
    exists and said nothing is a fact about the export.

    Mutation: skip empty turns and this fails on the numbering.
    """
    drawn = chat.draw(conversation(turns=[
        {"role": "user", "at": "", "text": ""},
        {"role": "assistant", "at": "", "text": "after"},
    ]))
    assert chat.EMPTY in drawn.text()
    assert "  2  it" in drawn.text(), drawn.text()


def test_a_truncated_export_says_so():
    """`partial` is the harness's claim about the export. A reader comparing
    turn counts against the index needs to be told, not to discover it by the
    two disagreeing.

    Mutation: drop the partial line and this fails.
    """
    assert "PARTIAL" in chat.draw(conversation(partial=True)).text()
    assert "PARTIAL" not in chat.draw(conversation(partial=False)).text()


def test_an_empty_conversation_says_the_archive_is_empty_not_that_it_failed():
    """Zero turns and an unreachable harness are different facts, and the two
    sentences must not be swapped."""
    drawn = chat.draw(conversation(turns=[]))
    assert "no turns in the archive" in drawn.text()
    assert "did not answer" not in drawn.text()


def test_an_unreachable_harness_draws_no_turns_at_all():
    """THE ONE THAT MATTERS.

    An empty transcript would state that the conversation was empty, which is a
    different claim from not having been able to read it.

    Mutation: fall through and draw the (absent) turns and this fails.
    """
    drawn = chat.draw(threads.Conversation(
        False, "http://127.0.0.1:3141/v1/threads/claude/abc",
        problem="nothing is answering at http://127.0.0.1:3141",
        remedy="`uv run qm dashboard --start harness`"))
    assert "nothing is answering" in drawn.text()
    assert "dashboard --start harness" in drawn.text()
    assert "would look like an answer" in drawn.text()
    assert "every turn" in drawn.channels_dropped


def test_long_turns_wrap_and_stay_indented_under_their_speaker():
    """A turn that ran to the left margin would read as a new speaker."""
    drawn = chat.draw(conversation(turns=[
        {"role": "user", "at": "", "text": "word " * 80}]), width=50)
    body = [line for line in drawn.lines if line.startswith("     ")]
    assert len(body) > 3
    assert all(len(line) <= 50 for line in body), max(body, key=len)


def test_the_rendering_names_what_it_cannot_carry():
    """A reader comparing this with the source conversation needs to know which
    channels are missing here rather than assume there were none."""
    assert "attachments" in chat.draw(conversation()).channels_dropped


# --- fetching it --------------------------------------------------------------


def test_an_identifier_is_quoted_into_the_url():
    """Archive identifiers are somebody else's and have carried slashes. An
    unquoted one addresses a different route, and the 404 blames the archive.

    Mutation: drop the quoting and this fails.
    """
    found = threads.conversation("claude", "a/b c", base="http://127.0.0.1:9")
    assert "a%2Fb%20c" in found.where


def test_an_unreachable_harness_is_a_sentence_and_not_an_exception():
    """The harness is a separate process on a separate port and is very often
    not running. The caller wants something to print."""
    found = threads.conversation("claude", "abc", base="http://127.0.0.1:9")
    assert found.reachable is False
    assert "nothing is answering" in found.problem
    assert found.remedy


def test_a_thread_is_located_by_lookup_and_not_by_parsing_its_name(monkeypatch):
    """**THE NAME IS NOT SPLIT BACK APART.** The table shows the delta address
    the harness built from `source` and `id`. Rebuilding the pair by parsing
    that name would be a second copy of somebody else's naming rule, agreeing
    right up until the prefix changed.

    Mutation: derive the pair from the string and this fails, because the name
    here does not contain the source.
    """
    monkeypatch.setattr(threads, "fetch", lambda **kw: threads.Archive(
        reachable=True, indexed=True,
        threads=[{"address": "thread-abc", "source": "chatgpt", "id": "xyz-1"}]))
    assert threads.locate("thread-abc") == ("chatgpt", "xyz-1")


def test_an_unreachable_archive_locates_nothing(monkeypatch):
    monkeypatch.setattr(threads, "fetch",
                        lambda **kw: threads.Archive(reachable=False))
    assert threads.locate("thread-abc") is None


def test_a_name_the_archive_does_not_carry_locates_nothing(monkeypatch):
    monkeypatch.setattr(threads, "fetch", lambda **kw: threads.Archive(
        reachable=True, indexed=True,
        threads=[{"address": "thread-other", "source": "claude", "id": "1"}]))
    assert threads.locate("thread-abc") is None


def test_a_row_missing_its_source_is_not_half_located(monkeypatch):
    """A partial row would otherwise produce ("", id) and a request for a
    source that does not exist."""
    monkeypatch.setattr(threads, "fetch", lambda **kw: threads.Archive(
        reachable=True, indexed=True,
        threads=[{"address": "thread-abc", "id": "xyz-1"}]))
    assert threads.locate("thread-abc") is None


# --- what must not happen -----------------------------------------------------


def test_nothing_here_offers_to_write_a_transcript_to_disk():
    """**THE ARCHIVE IS PERSONAL MATERIAL AND MUST NOT BE PUBLISHED.**

    A viewer that grew an export path would be a decision about publication
    wearing the clothes of a convenience, and it would arrive as a one-line
    change nobody read twice. This is the check that makes that change visible.

    Mutation: add a `path` or `out` parameter to anything in `chat` and this
    fails.
    """
    import inspect

    for name, thing in vars(chat).items():
        if not inspect.isfunction(thing) or name.startswith("_"):
            continue
        taken = set(inspect.signature(thing).parameters)
        forbidden = taken & {"path", "out", "outfile", "destination", "to_file"}
        assert not forbidden, (
            f"chat.{name} takes {sorted(forbidden)}. Writing a transcript to "
            f"disk is a decision about publishing personal material, not a "
            f"convenience to add in passing.")

    source = inspect.getsource(chat)
    assert "open(" not in source and "write_text" not in source, (
        "chat.py writes to a file. See the module docstring: turns are drawn "
        "and dropped.")


# --- what the table shows is not what an address is ---------------------------


def test_the_name_the_table_shows_locates_the_thread(monkeypatch):
    """THE ONE THE FIRST VERSION GOT WRONG.

    `facets._delta_name` renders `owner/repo/delta/thread-abc` as `thread-abc`,
    because a column cannot hold an address. Comparing the cell against the full
    address matched nothing, and every read reported that the harness did not
    have the thread — a true-sounding sentence about the wrong comparison.

    Mutation: compare against the full address only and this fails.
    """
    monkeypatch.setattr(threads, "fetch", lambda **kw: threads.Archive(
        reachable=True, indexed=True,
        threads=[{"address": "acme/proj/delta/thread-abc",
                  "source": "claude", "id": "xyz-1"}]))
    assert threads.locate("thread-abc") == ("claude", "xyz-1")


def test_a_full_address_locates_it_too(monkeypatch):
    """A caller holding a real address should not have to trim it first."""
    monkeypatch.setattr(threads, "fetch", lambda **kw: threads.Archive(
        reachable=True, indexed=True,
        threads=[{"address": "acme/proj/delta/thread-abc",
                  "source": "claude", "id": "xyz-1"}]))
    assert threads.locate("acme/proj/delta/thread-abc") == ("claude", "xyz-1")


def test_a_tail_that_matches_a_different_project_is_not_accepted(monkeypatch):
    """**THE HAZARD OF MATCHING THE TAIL.** Two projects can hold a thread whose
    name ends the same way, and an address exists precisely to tell them apart.
    A full address given by the caller must match that address and no other.

    Mutation: match only on the tail and this fails.
    """
    monkeypatch.setattr(threads, "fetch", lambda **kw: threads.Archive(
        reachable=True, indexed=True,
        threads=[{"address": "other/proj/delta/thread-abc",
                  "source": "chatgpt", "id": "wrong"}]))
    assert threads.locate("acme/proj/delta/thread-abc") is None


def test_a_row_with_no_address_at_all_is_skipped(monkeypatch):
    """A harness older than the delta fields sends none, and the facet draws
    `--`. It must not match an empty name."""
    monkeypatch.setattr(threads, "fetch", lambda **kw: threads.Archive(
        reachable=True, indexed=True,
        threads=[{"source": "claude", "id": "xyz-1"}]))
    assert threads.locate("") is None
    assert threads.locate("--") is None
