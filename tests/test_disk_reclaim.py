"""Reclaim as a delta: the action recorded as the pair of readings it sits between.

Two things are being defended here.

**Claimed and freed are different facts.** The reclaimer reports what it
removed; the volume reports what came back. On a container disk that does not
shrink they differ by the whole amount. A tool that reported only the first
would announce space that is still gone, and one that reported only the second
would blame the reclaimer for a concurrent download.

**Composition recomputes, it does not add up.** An unknown is not zero, so
summing a chain would launder a run nobody measured into a confident total.
Composing asks the store the same question of the two endpoints and gets an
answer with the same refusals attached.

Every apply path below runs against a stand-in corpus whose "reclaimer" is a
script that deletes a temp directory. The suite must never be able to empty the
developer's real caches -- that is a test nobody runs twice.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier import disk as disk_tools
from dossier import disk_store

from .test_disk_store import document, measured_target, unknown_target


@pytest.fixture
def session():
    built = create_engine("sqlite://")
    SQLModel.metadata.create_all(built)
    with Session(built) as active:
        yield active


def fake_corpus(tmp_path: Path, sizes: list[int]) -> Path:
    """A corpus whose disk tooling is scripted, and whose readings we control.

    `sizes` is the byte total each successive `disk_status.py --write` reports,
    so a reclaim can be made to look like it freed something without anything
    on the real machine being touched.
    """
    root = tmp_path / "corpus"
    (root / "ci").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / disk_tools.POLICY).write_text("schema: 1\nreclaimers: []\n", encoding="utf-8")

    counter = root / "ci" / "counter.txt"
    counter.write_text("0", encoding="utf-8")

    (root / disk_tools.TOOLS["status"]).write_text(
        "import json, sys, pathlib\n"
        f"sizes = {sizes!r}\n"
        "here = pathlib.Path(__file__).resolve().parent\n"
        "counter = here / 'counter.txt'\n"
        "n = int(counter.read_text())\n"
        "counter.write_text(str(n + 1))\n"
        "size = sizes[min(n, len(sizes) - 1)]\n"
        "free = 1000 - size\n"
        "doc = {\n"
        "  'schema': 1,\n"
        "  'generated_at': '2026-08-%02dT00:00:00Z' % (10 + n),\n"
        "  'generator': {'tool': 'ci/disk_status.py', 'policy': 'ci/disk-policy.yaml'},\n"
        "  'reading': {'staleness_budget_hours': 6},\n"
        "  'totals': {'reclaimable_bytes': {'refetched': size}},\n"
        "  'volumes': [{'path': 'C:/', 'total_bytes': 1000, 'used_bytes': size,\n"
        "               'free_bytes': free, 'free_ratio': free / 1000,\n"
        "               'state': 'ok', 'severity': 'ok', 'thresholds_fired': []}],\n"
        "  'targets': [{'name': 'cache', 'title': 'A cache', 'kind': 'directory_contents',\n"
        "               'safety': 'refetched', 'owner': 'x',\n"
        "               'measured': {'bytes': size, 'files': 1, 'units_total': 1,\n"
        "                            'unreadable': 0,\n"
        "                            'units': [{'path': 'C:/cache', 'bytes': size}]}}]\n"
        "}\n"
        "args = sys.argv[1:]\n"
        "if '--write' in args:\n"
        "    out = pathlib.Path(args[args.index('--write') + 1])\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    out.write_text(json.dumps(doc), encoding='utf-8')\n"
        "    print('wrote', out)\n",
        encoding="utf-8",
    )
    (root / disk_tools.TOOLS["reclaim"]).write_text(
        "import sys\n"
        "applied = '--apply' in sys.argv\n"
        "print(('Removed' if applied else 'Would remove') + ' 3 paths, 400.0GB')\n",
        encoding="utf-8",
    )
    (root / disk_tools.TOOLS["dashboard"]).write_text("", encoding="utf-8")
    return root


@pytest.fixture
def document_at(tmp_path, monkeypatch):
    """Point the module's document path at a temp file, not ~/.dossier."""
    target = tmp_path / "disk-status.json"
    monkeypatch.setattr(disk_tools, "document_path", lambda: target)
    return target


# --- the reclaimer's summary is read, never recomputed ----------------------


def test_the_plan_total_is_read_from_the_reclaimers_own_summary() -> None:
    """A total assembled here would be a second definition of what it did."""
    assert disk_tools.parse_plan("Would remove 22 paths, 104.5GB") == (104_500_000_000, 22)
    assert disk_tools.parse_plan("Removed 3 paths, 0.6GB") == (600_000_000, 3)


def test_output_with_no_summary_line_yields_no_total() -> None:
    """Not zero. A run whose summary could not be read removed an unknown
    amount, and zero is a claim nobody established."""
    assert disk_tools.parse_plan("something went wrong") == (None, None)


# --- a run is stored as the pair it sits between ----------------------------


def test_a_dry_run_is_recorded_and_removes_nothing(
    session, tmp_path: Path, document_at
) -> None:
    root = fake_corpus(tmp_path, [400, 400])
    record, outcome = disk_tools.reclaim_and_record(session, root, apply=False)

    assert outcome.ok
    assert record.outcome == "planned"
    assert record.applied is False
    assert record.claimed_bytes == 400_000_000_000
    assert record.after_snapshot_id is None


def test_a_dry_run_has_no_delta_and_says_why(
    session, tmp_path: Path, document_at
) -> None:
    """Not an empty delta, which reads as "it freed nothing"."""
    root = fake_corpus(tmp_path, [400, 400])
    record, _ = disk_tools.reclaim_and_record(session, root, apply=False)
    delta = disk_store.reclaim_delta(session, record)
    assert not delta.available
    assert "dry run" in delta.reason


def test_an_applied_run_is_bracketed_by_two_readings(
    session, tmp_path: Path, document_at
) -> None:
    root = fake_corpus(tmp_path, [400, 100])
    record, outcome = disk_tools.reclaim_and_record(session, root, apply=True)

    assert record.outcome == "applied"
    assert record.before_snapshot_id is not None
    assert record.after_snapshot_id is not None


def test_freed_is_what_the_volume_gave_back_not_what_was_claimed(
    session, tmp_path: Path, document_at
) -> None:
    """The whole point of storing both. The stand-in reclaimer claims 400GB
    and the readings move free space by 300 bytes; the record keeps each."""
    root = fake_corpus(tmp_path, [400, 100])
    record, _ = disk_tools.reclaim_and_record(session, root, apply=True)

    assert record.claimed_bytes == 400_000_000_000
    assert record.freed_bytes == 300
    assert record.claimed_bytes != record.freed_bytes


def test_a_reclaims_delta_is_the_same_shape_as_an_observed_one(
    session, tmp_path: Path, document_at
) -> None:
    """One type for both, so they compose without a second vocabulary."""
    root = fake_corpus(tmp_path, [400, 100])
    record, _ = disk_tools.reclaim_and_record(session, root, apply=True)

    delta = disk_store.reclaim_delta(session, record)
    assert delta.available
    assert delta.source == "reclaim"
    assert delta.reclaim_id == record.id
    change = next(t for t in delta.targets if t.name == "cache")
    assert change.change == -300
    assert change.status == "shrank"


def test_a_failing_reclaim_is_still_measured_afterwards(
    session, tmp_path: Path, document_at
) -> None:
    """A run that errored halfway has still removed something, and a record
    with no second reading would report that as nothing."""
    root = fake_corpus(tmp_path, [400, 100])
    (root / disk_tools.TOOLS["reclaim"]).write_text(
        "import sys\nprint('Removed 1 paths, 1.0GB')\nsys.exit(3)\n", encoding="utf-8"
    )
    record, outcome = disk_tools.reclaim_and_record(session, root, apply=True)

    assert not outcome.ok
    assert record.outcome == "failed"
    assert record.exit_status == 3
    assert record.after_snapshot_id is not None
    assert record.freed_bytes == 300


def test_a_run_with_no_reading_afterwards_reports_freed_as_unknown(
    session, tmp_path: Path, document_at
) -> None:
    """Never zero. Zero is a measurement nobody took."""
    root = fake_corpus(tmp_path, [400])
    record, _ = disk_tools.reclaim_and_record(session, root, apply=True)
    # Break the generator so the second reading cannot be written.
    assert record.after_snapshot_id is not None  # the fixture does produce one

    root2 = fake_corpus(tmp_path / "second", [400])
    (root2 / disk_tools.TOOLS["status"]).write_text(
        "import sys\nsys.exit(1)\n", encoding="utf-8"
    )
    record2, _ = disk_tools.reclaim_and_record(session, root2, apply=True)
    assert record2.freed_bytes is None
    assert record2.freed_unknown


def test_the_volume_change_is_unknown_when_a_volume_could_not_be_read(
    session, tmp_path: Path
) -> None:
    """A sum over readable volumes only is a floor wearing the clothes of a
    total, and a floor labelled `freed` is the number quoted back later."""
    unreadable = [{"path": "C:\\", "usage": {"unknown": "device not ready"}}]
    first = disk_store.load_document(
        session, document(tmp_path, "2026-08-10T00:00:00Z", name="a.json"), machine="box"
    )
    second = disk_store.load_document(
        session,
        document(tmp_path, "2026-08-11T00:00:00Z", volumes=unreadable, name="b.json"),
        machine="box",
    )
    assert disk_store.freed_between(session, first.snapshot_id, second.snapshot_id) is None


# --- composition ------------------------------------------------------------


def three_snapshots(session, tmp_path: Path):
    ids = []
    for day, size in ((10, 100), (11, 400), (12, 250)):
        outcome = disk_store.load_document(
            session,
            document(
                tmp_path,
                f"2026-08-{day}T00:00:00Z",
                targets=[measured_target("cache", size)],
                name=f"{day}.json",
            ),
            machine="box",
        )
        ids.append(outcome.snapshot_id)
    return ids


def test_composing_two_deltas_spans_both(session, tmp_path: Path) -> None:
    from dossier.models import DiskSnapshot

    a, b, c = three_snapshots(session, tmp_path)
    first = disk_store.delta_between(
        session, session.get(DiskSnapshot, a), session.get(DiskSnapshot, b)
    )
    second = disk_store.delta_between(
        session, session.get(DiskSnapshot, b), session.get(DiskSnapshot, c)
    )
    combined = disk_store.compose(session, first, second)

    assert combined.available
    assert combined.source == "composed"
    assert combined.contiguous
    # 100 -> 400 -> 250 composes to +150, not to the +300 and -150 added up
    # blindly, and not to either leg.
    assert next(t for t in combined.targets if t.name == "cache").change == 150


def test_composition_recomputes_rather_than_adding_the_parts(
    session, tmp_path: Path
) -> None:
    """The property that keeps an unknown from being laundered into a total.

    The middle leg is unmeasurable, so a sum would have to treat it as zero and
    would report the outer two as if the gap were nothing. Recomputing from the
    endpoints gives an answer whose unknowns are still unknown.
    """
    from dossier.models import DiskSnapshot

    ids = []
    for day, targets in (
        (10, [measured_target("cache", 100)]),
        (11, [unknown_target("cache")]),
        (12, [measured_target("cache", 900)]),
    ):
        outcome = disk_store.load_document(
            session,
            document(tmp_path, f"2026-08-{day}T00:00:00Z", targets=targets, name=f"{day}.json"),
            machine="box",
        )
        ids.append(outcome.snapshot_id)

    legs = [
        disk_store.delta_between(
            session, session.get(DiskSnapshot, ids[i]), session.get(DiskSnapshot, ids[i + 1])
        )
        for i in (0, 1)
    ]
    assert all(
        next(t for t in leg.targets if t.name == "cache").change is None for leg in legs
    )

    combined = disk_store.compose(session, *legs)
    # Both legs are unknown, and yet the span is measurable: 100 -> 900.
    # A sum of the legs could only have produced 0 or unknown, and one of those
    # is a lie about a target that grew by 800.
    assert next(t for t in combined.targets if t.name == "cache").change == 800


def test_a_gap_in_the_chain_is_flagged_rather_than_hidden(
    session, tmp_path: Path
) -> None:
    """The figures stay right; the attribution does not survive a gap."""
    from dossier.models import DiskSnapshot

    a, b, c = three_snapshots(session, tmp_path)
    first = disk_store.delta_between(
        session, session.get(DiskSnapshot, a), session.get(DiskSnapshot, b)
    )
    # b -> c is skipped; a -> c is composed from a leg that stops at b and one
    # that starts at c, so the span holds a change neither leg covers.
    outcome = disk_store.load_document(
        session,
        document(
            tmp_path, "2026-08-13T00:00:00Z",
            targets=[measured_target("cache", 900)], name="13.json",
        ),
        machine="box",
    )
    last = disk_store.delta_between(
        session, session.get(DiskSnapshot, c), session.get(DiskSnapshot, outcome.snapshot_id)
    )
    combined = disk_store.compose(session, first, last)
    assert combined.available
    assert combined.contiguous is False


def test_composing_across_machines_is_refused(session, tmp_path: Path) -> None:
    from dossier.models import DiskSnapshot

    for machine, day in (("laptop", 10), ("laptop", 11), ("tower", 12), ("tower", 13)):
        disk_store.load_document(
            session,
            document(tmp_path, f"2026-08-{day}T00:00:00Z", name=f"{machine}{day}.json"),
            machine=machine,
        )
    laptop = disk_store.latest_delta(session, machine="laptop")
    tower = disk_store.latest_delta(session, machine="tower")
    combined = disk_store.compose(session, laptop, tower)
    assert not combined.available
    assert "different machines" in combined.reason


def test_composing_nothing_says_so(session) -> None:
    assert not disk_store.compose(session).available


def test_composing_only_unavailable_deltas_says_so(session, tmp_path: Path) -> None:
    """A chain of dry runs has nothing to span, and must not report zero."""
    disk_store.load_document(session, document(tmp_path), machine="box")
    lonely = disk_store.latest_delta(session, machine="box")
    assert not lonely.available
    combined = disk_store.compose(session, lonely)
    assert not combined.available
    assert "no link carried two readings" in combined.reason


# --- reclaiming from the dashboard ------------------------------------------
#
# Every test here points the app at the stand-in corpus. The suite must never
# be able to empty the developer's real caches.


async def disk_app(engine, corpus: Path):
    from dossier.tui import DossierApp

    app = DossierApp(session_factory=lambda: Session(engine), initial_tab="tab-disk")
    app._disk_corpus_override = corpus
    return app


@pytest.fixture
def engine():
    """Shared across threads, which the reclaim worker needs.

    A bare `sqlite://` hands every connection its own empty in-memory database,
    so the worker thread would find no tables -- which is a fixture bug that
    looks exactly like the feature being broken.
    """
    from sqlalchemy.pool import StaticPool

    built = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(built)
    yield built
    built.dispose()


@pytest.mark.asyncio
async def test_apply_refuses_without_a_plan_from_this_session(
    engine, tmp_path: Path, document_at
) -> None:
    """Planning is not a formality to get past. The numbers move, and applying
    a plan nobody has seen is applying it against a disk that has changed.

    The wait matters as much as the assertion. Without it this test passes
    against a version with the guard removed -- the worker is merely still
    running when the count is taken -- which is an inert test on the one guard
    standing between a keypress and a hundred gigabytes.
    """
    app = await disk_app(engine, fake_corpus(tmp_path, [400, 100]))
    async with app.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        app.action_disk_apply()
        await app.workers.wait_for_complete()
        await pilot.pause()

        with Session(engine) as check:
            assert disk_store.reclaims(check) == []


@pytest.mark.asyncio
async def test_planning_removes_nothing_and_arms_the_apply(
    engine, tmp_path: Path, document_at
) -> None:
    app = await disk_app(engine, fake_corpus(tmp_path, [400, 400]))
    async with app.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        app.action_disk_plan()
        await app.workers.wait_for_complete()
        await pilot.pause()

        with Session(engine) as check:
            runs = disk_store.reclaims(check)
        assert len(runs) == 1
        assert runs[0].applied is False
        assert runs[0].outcome == "planned"
        assert app._disk_planned


@pytest.mark.asyncio
async def test_applying_after_a_plan_records_what_came_back(
    engine, tmp_path: Path, document_at
) -> None:
    """The whole request: execute the cleanup, and watch the space return."""
    app = await disk_app(engine, fake_corpus(tmp_path, [400, 400, 100, 100]))
    async with app.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        app.action_disk_plan()
        await app.workers.wait_for_complete()
        await pilot.pause()

        app.action_disk_apply()
        await app.workers.wait_for_complete()
        await pilot.pause()

        with Session(engine) as check:
            applied = [r for r in disk_store.reclaims(check) if r.applied]
            assert len(applied) == 1
            record = applied[0]
            assert record.outcome == "applied"
            assert record.claimed_bytes == 400_000_000_000
            assert record.freed_bytes == 300  # what the readings actually moved

            delta = disk_store.reclaim_delta(check, record)
            assert delta.available
            assert delta.source == "reclaim"


@pytest.mark.asyncio
async def test_an_apply_disarms_the_next_one(
    engine, tmp_path: Path, document_at
) -> None:
    """A plan that has been carried out is not a licence for the next one."""
    app = await disk_app(engine, fake_corpus(tmp_path, [400, 400, 100, 100]))
    async with app.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        app.action_disk_plan()
        await app.workers.wait_for_complete()
        app.action_disk_apply()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not app._disk_planned


@pytest.mark.asyncio
async def test_the_tab_reports_what_the_runs_gave_back(
    engine, tmp_path: Path, document_at
) -> None:
    app = await disk_app(engine, fake_corpus(tmp_path, [400, 400, 100, 100]))
    async with app.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        app.action_disk_plan()
        await app.workers.wait_for_complete()
        app.action_disk_apply()
        await app.workers.wait_for_complete()
        await pilot.pause()

        message = str(app.query_one("#disk-delta-age").content)
        assert "reclaim run(s) recorded" in message
        assert "gave back" in message


@pytest.mark.asyncio
async def test_the_tab_offers_the_keys_before_anything_has_been_run(
    engine, tmp_path: Path, document_at
) -> None:
    """A dashboard with an action nobody can find is a dashboard without it."""
    with Session(engine) as seed:
        disk_store.load_document(seed, document(tmp_path), machine=disk_store.this_machine())

    app = await disk_app(engine, fake_corpus(tmp_path, [400]))
    async with app.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        message = str(app.query_one("#disk-delta-age").content)
        assert "plans one" in message
        assert "applies the plan" in message


@pytest.mark.asyncio
async def test_the_keys_do_nothing_off_the_disk_tab(
    engine, tmp_path: Path, document_at
) -> None:
    """`x` and `X` are ordinary letters everywhere else in this app."""
    app = await disk_app(engine, fake_corpus(tmp_path, [400, 100]))
    async with app.run_test(size=(200, 50)) as pilot:
        await pilot.pause()
        app.query_one("#project-tabs").active = "tab-governance"
        await pilot.pause()
        app.action_disk_plan()
        await app.workers.wait_for_complete()
        await pilot.pause()

        with Session(engine) as check:
            assert disk_store.reclaims(check) == []


def test_the_dashboard_reclaims_at_the_cheapest_tier_only() -> None:
    """A dashboard that could empty the recycle bin on a keypress is one
    nobody should leave open. Widening belongs where somebody types the word."""
    from dossier.tui.app import DossierApp

    assert DossierApp.DISK_TIER == "refetched"


def test_a_volume_that_ended_smaller_is_not_described_as_freed() -> None:
    """A negative number wearing the word `freed` is worse than no number.

    This is a real reading: a `user-temp` sweep removed two paths while other
    processes wrote 37KB, so the volume finished smaller than it started.
    """
    from dossier.models import DiskReclaim
    from dossier.tui.app import DossierApp

    record = DiskReclaim(
        machine="box", allow="refetched", applied=True, outcome="applied",
        claimed_bytes=5_000, freed_bytes=-37_000,
    )
    message = DossierApp._reclaim_message(None, record, None)
    assert "gave back" not in message
    assert "smaller than it started" in message
    assert "something else was writing" in message


def test_a_small_reclaim_is_not_recorded_as_having_removed_nothing() -> None:
    """The reclaimer's summary rounds to GB, so a 5KB sweep prints 0.0GB. The
    exact count travels beside it, and is preferred."""
    assert disk_tools.parse_plan("Removed 2 paths, 0.0GB (5120 bytes)") == (5120, 2)
    # Older output without the parenthetical still parses, at GB precision.
    assert disk_tools.parse_plan("Removed 2 paths, 1.5GB") == (1_500_000_000, 2)


def test_the_dashboards_message_never_reports_claimed_alone() -> None:
    """On a container disk that does not shrink, claimed and freed differ by
    the whole amount, and announcing only the first announces space that is
    still gone."""
    from dossier.models import DiskReclaim
    from dossier.tui.app import DossierApp

    record = DiskReclaim(
        machine="box", allow="refetched", applied=True, outcome="applied",
        claimed_bytes=23_600_000_000, freed_bytes=0,
    )
    message = DossierApp._reclaim_message(None, record, None)
    assert "23.6GB" in message
    assert "gave back" in message
    assert "disagree" in message


def test_a_composed_delta_keeps_its_parts(session, tmp_path: Path) -> None:
    """So a view can show the chain as well as its total."""
    from dossier.models import DiskSnapshot

    a, b, c = three_snapshots(session, tmp_path)
    legs = [
        disk_store.delta_between(
            session, session.get(DiskSnapshot, x), session.get(DiskSnapshot, y)
        )
        for x, y in ((a, b), (b, c))
    ]
    combined = disk_store.compose(session, *legs)
    assert len(combined.parts) == 2
