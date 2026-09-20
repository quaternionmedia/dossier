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


def test_monitor_summarises_the_invocations_by_status(monkeypatch):
    monkeypatch.setattr(human, "_get", lambda url: ({"invocations": [
        {"status": "success"}, {"status": "success"}, {"status": "running"},
        {"status": "pending"}]}, "", ""))
    m = human.monitor(base="http://x")
    assert m.reachable
    assert m.total == 4
    assert m.running == 2  # running + pending
    assert dict(m.by_status) == {"pending": 1, "running": 1, "success": 2}


def test_monitor_reports_an_unreachable_harness_rather_than_raising():
    m = human.monitor(base="http://127.0.0.1:59999")
    assert m.reachable is False
    assert m.problem
    assert m.total == 0


# --- sending a new goal ------------------------------------------------------


def test_send_goal_refuses_an_empty_goal_before_reaching_the_harness():
    """A goal with no words is a mistake, not a plan request. It is refused on
    this side, the way an unnamed answer is -- nothing is sent."""
    import pytest

    with pytest.raises(ValueError):
        human.send_goal("   ", base="http://x")


def test_send_goal_reads_the_plan_the_planner_drafts(monkeypatch):
    import json

    class _Reply:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({
                "invocation_id": "inv-9",
                "result": {
                    "goal": "tidy the sweep view",
                    "steps": [
                        {"step": 1, "action": "Analyze", "description": "understand"},
                        {"step": 2, "action": "Sequence", "description": "order"},
                    ],
                    "estimated_steps": 2,
                },
            }).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Reply())
    planned = human.send_goal("tidy the sweep view", context="repo x",
                              base="http://x")
    assert planned.accepted
    assert planned.invocation_id == "inv-9"
    assert planned.goal == "tidy the sweep view"
    assert planned.estimated == 2
    assert [s.action for s in planned.steps] == ["Analyze", "Sequence"]


def test_send_goal_reports_an_unreachable_harness_rather_than_raising():
    planned = human.send_goal("do a thing", base="http://127.0.0.1:59999")
    assert planned.accepted is False
    assert planned.detail  # a reason, never an exception
    assert planned.goal == "do a thing"


def test_send_goal_carries_a_planner_error_through(monkeypatch):
    class _Reply:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"error": "the planner refused", "invocation_id": "x"}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Reply())
    planned = human.send_goal("go", base="http://x")
    assert planned.accepted is False and "refused" in planned.detail
