"""dossier can ask the harness to run a tool, and reads the tools it offers.

Running a tool is the one write in `dossier.human` -- it starts something. Like
every read there it **never raises**: an unreachable harness, a refused run and
a tool that errored are three reasons, not a crash.
"""

from __future__ import annotations

from dossier import human


def test_tools_parses_the_list_the_harness_returns(monkeypatch):
    monkeypatch.setattr(human, "_get", lambda url: (
        {"tools": [{"name": "planner", "description": "plans a change"},
                   {"name": "executor"}]}, "", ""))
    listing = human.tools(base="http://x")
    assert listing.reachable
    assert [t.name for t in listing.tools] == ["planner", "executor"]
    assert listing.tools[0].description == "plans a change"


def test_tools_reports_an_unreachable_harness_rather_than_raising():
    listing = human.tools(base="http://127.0.0.1:59999")
    assert listing.reachable is False
    assert listing.problem  # a reason, not an exception


def test_run_tool_reports_an_unreachable_harness_rather_than_raising():
    ran = human.run_tool("planner", base="http://127.0.0.1:59999")
    assert ran.accepted is False
    assert ran.tool == "planner"
    assert ran.detail  # says why, never raises


def test_run_tool_names_the_invocation_it_started(monkeypatch):
    import io

    class _Reply:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"invocation_id": "inv-42"}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Reply())
    ran = human.run_tool("planner", {"x": 1}, base="http://x")
    assert ran.accepted and ran.invocation_id == "inv-42"


def test_run_tool_carries_a_tool_error_through(monkeypatch):
    class _Reply:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"error": "the tool refused"}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Reply())
    ran = human.run_tool("planner", base="http://x")
    assert ran.accepted is False and "refused" in ran.detail
