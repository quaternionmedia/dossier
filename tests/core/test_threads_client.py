"""Reading the harness's thread archive over the seam.

The tests worth reading are the three states. A panel that showed an empty table
when the truth was "nobody answered" is the failure this client is written
against, and it is the same distinction the harness payload makes between a
count of zero and a count nobody took.
"""

from __future__ import annotations

import httpx
import pytest

from dossier import threads as client


def transport(handler):
    """A client bound to a fake transport, so nothing here opens a socket."""
    return httpx.MockTransport(handler)


# The genuine class, captured once at import. Capturing it inside the helper
# meant the second call in one test wrapped the first fake -- so a test that
# swapped handlers kept the original one, and the failure looked like the code
# ignoring a transport error. The helper was wrong, not the client.
REAL_CLIENT = httpx.Client


def with_response(monkeypatch, handler):
    """Point `httpx.Client` at a handler. Safe to call more than once."""
    def fake(*args, **kwargs):
        kwargs["transport"] = transport(handler)
        return REAL_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", fake)


def ok(body):
    return lambda request: httpx.Response(200, json=body)


# --- where it looks -----------------------------------------------------------


def test_the_host_is_loopback_and_nothing_moves_it(monkeypatch):
    """THE ONE THAT MATTERS.

    The archive is somebody's conversations. Somebody running the harness on
    another port is ordinary; a client that could be pointed at another machine
    is how "served to this machine only" stops being true.

    Mutation: read the host from the environment too and this fails.
    """
    monkeypatch.setenv("DOSSIER_HARNESS_PORT", "9999")
    assert client.base_url() == "http://127.0.0.1:9999"
    monkeypatch.setenv("DOSSIER_HARNESS_HOST", "10.0.0.5")
    assert "10.0.0.5" not in client.base_url()
    assert client.base_url().startswith("http://127.0.0.1:")


def test_a_port_that_is_not_a_number_falls_back(monkeypatch):
    """This runs inside a redraw. A crash here takes the panel with it."""
    monkeypatch.setenv("DOSSIER_HARNESS_PORT", "not-a-port")
    assert client.base_url() == f"http://127.0.0.1:{client.DEFAULT_PORT}"


# --- the three states ---------------------------------------------------------


def test_an_unreachable_harness_is_not_an_empty_archive(monkeypatch):
    """Mutation: return an empty `Archive()` on a transport error and this
    fails -- which is a panel saying the archive is empty when nobody answered.
    """
    def refuse(request):
        raise httpx.ConnectError("nothing listening", request=request)

    with_response(monkeypatch, refuse)
    archive = client.fetch()
    assert archive.reachable is False
    assert archive.threads == []
    assert "not answering" in archive.note
    assert "python -m qmcp serve" in archive.note


def test_a_running_harness_with_no_index_says_which_it_is(monkeypatch):
    """Not running, and running with nothing indexed, are different failures
    and want different sentences."""
    with_response(monkeypatch, lambda request: httpx.Response(404, json={}))
    archive = client.fetch()
    assert (archive.reachable, archive.indexed) == (True, False)
    assert "has no index" in archive.note
    assert "threads index --write" in archive.note


def test_an_indexed_archive_reports_what_it_counted(monkeypatch):
    with_response(monkeypatch, ok({
        "generated_at": "2026-08-20T00:00:00Z",
        "totals": {"threads": 2},
        "threads": [{"id": "a", "source": "claude", "turns": 3},
                    {"id": "b", "source": "claude-code", "turns": 9}],
    }))
    archive = client.fetch()
    assert (archive.reachable, archive.indexed) == (True, True)
    assert len(archive.threads) == 2
    assert "not what exists" in archive.note


def test_an_empty_but_indexed_archive_is_not_an_error(monkeypatch):
    """An archive with nothing in it is a real state."""
    with_response(monkeypatch, ok({"generated_at": "x", "totals": {"threads": 0},
                                   "threads": []}))
    archive = client.fetch()
    assert archive.indexed is True
    assert archive.threads == []


def test_a_body_that_is_not_json_does_not_reach_the_panel(monkeypatch):
    with_response(monkeypatch,
                  lambda request: httpx.Response(200, content=b"<html>"))
    archive = client.fetch()
    assert archive.indexed is False
    assert "not JSON" in archive.note


def test_an_unexpected_status_is_a_state_not_an_exception(monkeypatch):
    with_response(monkeypatch, lambda request: httpx.Response(500, json={}))
    archive = client.fetch()
    assert archive.reachable is True and archive.indexed is False
    assert "500" in archive.note


# --- what the panel shows -----------------------------------------------------


def test_threads_that_disagree_are_listed_first(monkeypatch):
    """The only row here that is a finding rather than an inventory entry.

    Mutation: sort by date alone and this fails, which buries the finding under
    however many conversations there are.
    """
    from dossier.facets import threads_org

    with_response(monkeypatch, ok({
        "generated_at": "2026-08-20T00:00:00Z",
        "totals": {"threads": 3},
        "threads": [
            {"id": "a", "source": "claude", "turns": 1, "last_seen": "2026-08-20"},
            {"id": "b", "source": "claude", "turns": 1, "last_seen": "2026-08-19",
             "diverged": True},
            {"id": "c", "source": "claude", "turns": 1, "last_seen": "2026-08-18"},
        ],
    }))
    section = threads_org(None, None, 10)
    assert section.rows[0][0] == "b"
    assert section.rows[0][-1] == "disagrees"


def test_an_unreachable_harness_renders_the_reason_not_zero_rows(monkeypatch):
    from dossier.facets import threads_org

    def refuse(request):
        raise httpx.ConnectError("nothing listening", request=request)

    with_response(monkeypatch, refuse)
    section = threads_org(None, None, 10)
    assert section.rows == ()
    assert "not answering" in section.note


def test_the_project_view_shows_the_whole_archive(monkeypatch):
    """A conversation belongs to no repository. What a session *produced* is
    addressed to one and appears under Deltas; the conversation stays whole."""
    from dossier.facets import threads_org, threads_project

    with_response(monkeypatch, ok({
        "generated_at": "x", "totals": {"threads": 1},
        "threads": [{"id": "a", "source": "claude", "turns": 1}],
    }))

    class FakeProject:
        full_name = "quaternionmedia/qm"
        name = "qm"

    assert threads_project(None, FakeProject(), 10).rows == \
        threads_org(None, None, 10).rows


# --- what it cannot do --------------------------------------------------------


def test_the_client_never_writes(monkeypatch):
    """The archive is built by the harness from files it reads. A control panel
    that could edit it would be a second author of a record whose whole value
    is being one."""
    from pathlib import Path

    source = Path(client.__file__).read_text(encoding="utf-8")
    for verb in (".post(", ".put(", ".patch(", ".delete("):
        assert verb not in source, f"{verb} would make this a writer"


def test_nothing_here_imports_the_harness():
    """What crosses is HTTP and a schema. Importing would mean neither ships
    without the other."""
    from pathlib import Path

    source = Path(client.__file__).read_text(encoding="utf-8")
    assert "import qmcp" not in source
    assert "from qmcp" not in source


def test_deltas_for_tells_none_apart_from_nothing_settled(monkeypatch):
    """A thread that settled nothing and a harness that did not answer are
    different facts about the conversation."""
    with_response(monkeypatch, ok({"deltas": []}))
    assert client.deltas_for("claude", "c-1") == []

    def refuse(request):
        raise httpx.ConnectError("nothing listening", request=request)

    with_response(monkeypatch, refuse)
    assert client.deltas_for("claude", "c-1") is None
