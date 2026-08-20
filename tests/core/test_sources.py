"""Which stores this installation reads, and which it merely might.

The test worth reading is the first one. A settings screen reporting a real size
about a file the application does not open is worse than one reporting nothing:
a reader checks it, sees a plausible number, and stops looking.
"""

from __future__ import annotations

from pathlib import Path

from dossier import sources

# NOTHING HERE RELOADS `dossier.cli`, AND THAT IS DELIBERATE.
#
# The first version of this file did. `importlib.reload` replaces the module
# object, and `dossier.tui.app` imports from `dossier.cli` -- so every test that
# ran afterwards was holding a reference to a module that had been swapped, and
# sixty-three of them failed in a full run while passing in isolation. Test
# pollution that looks exactly like a regression, from tests written to check
# that a regression could not happen.
#
# `sources.database_url` exists as a function precisely so a test can replace it
# without touching module state. `health.candidate_databases` reads the
# environment at call time, so `monkeypatch.setenv` reaches it directly.


def using(monkeypatch, path):
    """Point this process's resolved database at `path`, without a reload."""
    url = f"sqlite:///{Path(path).as_posix()}"
    monkeypatch.setattr(sources, "database_url", lambda: url)
    monkeypatch.setenv("DOSSIER_DATABASE_URL", url)


# --- which one is live --------------------------------------------------------


def test_the_database_in_use_is_the_one_this_process_resolved(monkeypatch, tmp_path):
    """THE ONE THAT MATTERS.

    The settings screen reported `dossier_home()/dossier.db` and its size --
    a path the application does not necessarily open. On the machine this was
    written on there were two, and it was showing the wrong one.

    Mutation: read the path from `dossier_home()` instead of the resolved URL
    and this fails.
    """
    target = tmp_path / "live.db"
    target.write_bytes(b"x" * 2048)
    using(monkeypatch, target)

    live = [s for s in sources.databases() if s.in_use]
    assert len(live) == 1
    assert Path(live[0].where).resolve() == target.resolve()
    assert live[0].detail == "2.0 KB"


def test_without_an_override_every_candidate_is_listed(monkeypatch, tmp_path):
    """Listing them is half the diagnosis. Two databases with nothing on screen
    saying which is live is the state this is written against.

    This is the ordinary case, and it is the one that matters: on the machine
    this was written on there were two, and the settings screen was showing the
    one the application does not open.

    Mutation: return only the live one and this fails.
    """
    monkeypatch.delenv("DOSSIER_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dossier.db").write_bytes(b"x")
    monkeypatch.setattr(sources, "database_url", lambda: "sqlite:///dossier.db")

    found = sources.databases()
    assert len(found) > 1, "the working directory and the home candidate"
    assert sum(1 for s in found if s.in_use) == 1


def test_an_override_narrows_the_list_to_the_one_named(monkeypatch, tmp_path):
    """`health.candidate_databases` returns only the override when one is set:
    an operator who named a database meant that one, and reporting the others
    beside it would be a diagnostic about a database nobody asked about.

    So the view narrows too, and that is the design rather than a gap.
    """
    target = tmp_path / "live.db"
    target.write_bytes(b"x")
    using(monkeypatch, target)

    found = sources.databases()
    assert len(found) == 1
    assert found[0].in_use is True


def test_a_database_that_does_not_exist_says_so_rather_than_zero_bytes(
        monkeypatch, tmp_path):
    """`0 B` reads as an empty database. It has not been created."""
    target = tmp_path / "absent.db"
    using(monkeypatch, target)

    live = [s for s in sources.databases() if s.in_use][0]
    assert live.present is False
    assert live.detail == "not created yet"
    assert live.marker == "in use", "still the one it would open"


def test_one_path_reached_two_ways_is_one_row(monkeypatch, tmp_path):
    """The live database is usually also a candidate. Listing it twice would
    read as two databases."""
    target = tmp_path / "dossier.db"
    target.write_bytes(b"x")
    using(monkeypatch, target)
    monkeypatch.chdir(tmp_path)

    rows = [Path(s.where).resolve() for s in sources.databases()]
    assert len(rows) == len(set(rows))


def test_a_url_that_is_not_a_file_has_no_open_database(monkeypatch):
    """A non-sqlite URL is not a path, and pretending otherwise would put a
    made-up filename on the screen."""
    monkeypatch.setattr(sources, "database_url",
                        lambda: "postgresql://elsewhere/dossier")
    assert sources.open_database() is None


# --- sizes --------------------------------------------------------------------


def test_sizes_are_readable():
    assert sources.human_size(512) == "512 B"
    assert sources.human_size(2048) == "2.0 KB"
    assert sources.human_size(5 * 1024 * 1024) == "5.0 MB"


# --- the archive, which this side does not own --------------------------------


def test_an_unreachable_archive_is_a_row_with_a_reason(monkeypatch):
    """Never an absent row. A source silently omitted is the failure this
    module is about.

    Mutation: drop the archive when it does not answer and this fails.
    """
    import httpx

    from dossier import threads

    real = httpx.Client

    def refuse(*args, **kwargs):
        def handler(request):
            raise httpx.ConnectError("nothing listening", request=request)
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", refuse)
    row = sources.archive()
    assert row.label == "thread archive"
    assert row.present is False
    assert "not answering" in row.detail


def test_an_indexed_archive_reports_what_it_holds(monkeypatch):
    import httpx

    real = httpx.Client

    def answer(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "generated_at": "2026-08-20T00:00:00Z",
                "totals": {"threads": 203}, "threads": []}))
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", answer)
    row = sources.archive()
    assert row.in_use is True
    assert "203 thread(s)" in row.detail


# --- the whole list -----------------------------------------------------------


def test_every_source_carries_where_it_is(monkeypatch):
    """A row without a location is a row nobody can check."""
    for source in sources.all_sources(include_archive=False):
        assert source.where
        assert source.label


def test_the_archive_can_be_left_out_when_a_caller_cannot_wait(monkeypatch):
    """Reaching the harness is a network call with a timeout. The default is to
    ask; a caller drawing a screen may not want to wait."""
    without = sources.all_sources(include_archive=False)
    assert not any(s.label == "thread archive" for s in without)
