"""Tests whose brief is to satisfy each guard while doing the thing it forbids.

`governance/qm/AGENTS.md` item 13: breaking a guard and watching it go red
proves it fires on the case you thought of; it cannot find the case you did
not. So each test here is an attempt to route around a rule this repository
now relies on, written from the attacker's side rather than the author's.

Several failed when first written, and the code changed. They are kept because
a hole that was open once is the one most likely to reopen.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from dossier import overview as ov
from dossier.maintenance import (
    deltas_from_pull_requests,
    is_stub,
    prune_fork_deltas,
    prune_stub_deltas,
    purge_other_owners,
)
from dossier.models.schemas import (
    Project,
    ProjectDelta,
    ProjectPullRequest,
)

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)


@pytest.fixture()
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'adv.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


# --- routing around the fork exclusion ---------------------------------------


def test_every_sync_path_carries_the_fork_flag():
    """A second code path that creates projects is a second definition of what
    a project is. The API sync path built a `Project` and never set `is_fork`:
    every field it did set was correct, so the row looked like any other and
    counted in every figure.
    """
    api = Path("src/dossier/api/main.py").read_text(encoding="utf-8")
    cli = Path("src/dossier/cli.py").read_text(encoding="utf-8")
    assert "is_fork=repo.is_fork" in api, "the API sync path drops the flag"
    assert "is_fork=repo.is_fork" in cli


def test_a_fork_cannot_arrive_with_an_unknown_flag(engine):
    """`is_fork IS NULL` is falsy in Python, so a legacy row would read as
    'not a fork' and be counted. The column refuses the value instead."""
    with Session(engine) as s:
        s.add(Project(name="org/x", github_owner="org"))
        s.commit()
    raw = sqlite3.connect(str(engine.url).replace("sqlite:///", ""))
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute("insert into project (name, is_fork, is_archived) "
                    "values ('org/sneaky', NULL, 0)")
        raw.commit()


def test_dropping_the_owner_argument_does_not_readmit_forks(engine):
    """The exclusion once applied only when scoped, so calling `build` without
    an owner quietly changed the subject back."""
    with Session(engine) as s:
        s.add_all([
            Project(name="org/own", github_owner="org", github_stars=2,
                    last_synced_at=NOW),
            Project(name="org/fork", github_owner="org", github_stars=9_000,
                    is_fork=True, last_synced_at=NOW),
        ])
        s.commit()
        unscoped = {c.label: c.value for c in ov.build(s, now=NOW).masthead}
        assert unscoped["stars"] == "2"
        assert "forks excluded" in ov.build(s, now=NOW).scope


def test_a_forks_work_cannot_re_enter_through_derivation(engine):
    """Deriving deltas from open pull requests is re-run routinely. If it does
    not know about forks, every run puts upstream's work back on the board."""
    with Session(engine) as s:
        fork = Project(name="org/fork", github_owner="org", is_fork=True)
        s.add(fork)
        s.commit()
        s.refresh(fork)
        s.add(ProjectPullRequest(project_id=fork.id, pr_number=4,
                                 title="Bump certifi", state="open"))
        s.commit()
        assert deltas_from_pull_requests(s, apply=True) == []
        assert s.exec(select(ProjectDelta)).all() == []


def test_the_purge_keeps_the_forks_data_it_declines_to_count(engine):
    """Excluding a row from an aggregate and deleting it are different acts,
    and conflating them loses data nobody asked to lose."""
    with Session(engine) as s:
        s.add(Project(name="org/fork", full_name="org/fork", github_owner="org",
                      is_fork=True))
        s.commit()
        purge_other_owners(s, "org", apply=True)
        assert len(s.exec(select(Project)).all()) == 1


# --- routing around the stub rule --------------------------------------------


def test_whitespace_is_not_a_description():
    """A rule that checks a field is set, rather than non-empty, is satisfied
    by a space."""
    assert is_stub(ProjectDelta(project_id=1, name="x", title="x", description="   "))
    assert is_stub(ProjectDelta(project_id=1, name="x", title="x", branch_name=" "))


def test_a_real_delta_survives_every_prune(engine):
    """Both prunes run against the same table. A delta with evidence, on a
    project that is not a fork, must survive both."""
    with Session(engine) as s:
        p = Project(name="org/own", github_owner="org")
        s.add(p)
        s.commit()
        s.refresh(p)
        s.add(ProjectDelta(project_id=p.id, name="real", title="Real",
                           description="written by a person"))
        s.commit()
        prune_stub_deltas(s, apply=True)
        prune_fork_deltas(s, apply=True)
        assert [d.name for d in s.exec(select(ProjectDelta)).all()] == ["real"]


def test_two_projects_may_both_have_pull_request_seven(engine):
    """Identity is the project *and* the number. Keying on the number alone
    would silently merge two repositories' work."""
    with Session(engine) as s:
        a = Project(name="org/a", github_owner="org")
        b = Project(name="org/b", github_owner="org")
        s.add_all([a, b])
        s.commit()
        s.refresh(a)
        s.refresh(b)
        s.add_all([
            ProjectPullRequest(project_id=a.id, pr_number=7, title="A", state="open"),
            ProjectPullRequest(project_id=b.id, pr_number=7, title="B", state="open"),
        ])
        s.commit()
        deltas_from_pull_requests(s, apply=True)
        deltas_from_pull_requests(s, apply=True)
        rows = s.exec(select(ProjectDelta)).all()
        assert len(rows) == 2, "one delta per project, not one per number"
        assert {r.project_id for r in rows} == {a.id, b.id}


# --- routing around the ownership rule ---------------------------------------


def test_an_unattributable_project_is_not_quietly_adopted(engine):
    """Neither counted as the org's nor kept by the purge: it cannot be shown
    to belong, and a row that survives every filter accumulates forever."""
    with Session(engine) as s:
        s.add(Project(name="loose", last_synced_at=NOW))
        s.commit()
        figures = {c.label: c.value for c in ov.build(s, now=NOW, owner="org").masthead}
        assert figures["repositories"] == "0"
        assert purge_other_owners(s, "org").projects == ["loose"]


def test_the_overview_and_the_purge_agree_on_who_owns_a_row(engine):
    """Two definitions of ownership would let a row be counted in the org's
    figures and deleted as somebody else's on the same afternoon."""
    with Session(engine) as s:
        s.add(Project(name="implied", full_name="org/implied", last_synced_at=NOW))
        s.commit()
        counted = {c.label: c.value for c in ov.build(s, now=NOW, owner="org").masthead}
        assert counted["repositories"] == "1"
        assert purge_other_owners(s, "org").projects == []


# --- routing around the home-directory isolation -----------------------------


def test_no_module_reaches_the_real_home_for_its_state():
    """`DOSSIER_HOME` protects the config. It has to protect every path that
    writes there, or the suite still rewrites a real person's state through
    whichever module was missed."""
    offenders = []
    for path in Path("src/dossier").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if 'Path.home() / ".dossier"' in text and "DOSSIER_HOME" not in text:
            offenders.append(str(path))
    assert offenders == [], f"these reach the real home directly: {offenders}"


def test_the_isolation_is_active_for_this_suite():
    """An autouse fixture that stopped running would fail nothing else."""
    from dossier.config import DossierConfig

    assert os.environ.get("DOSSIER_HOME"), "the suite is not isolated"
    # Not "is the path outside the home directory" -- on Windows the temp
    # directory lives *inside* it, so that question answers no for a correctly
    # isolated run. The claim is that the suite is not using the real config.
    assert DossierConfig.get_config_path() != Path.home() / ".dossier" / "config.json"


# --- routing around the tag policy -------------------------------------------


def test_the_determinism_half_of_the_tag_claim_is_wired():
    """`tag-claims.yml` reads the annotation and says in its own header that it
    does not run the tests. Without a project-owned job doing that, the third
    claim a tag makes -- deterministic automated validation passed -- has
    nothing behind it, and the repository looks gated because two of three
    checks exist."""
    workflows = Path(".github/workflows")
    wired = [
        path for path in workflows.glob("*.yml")
        if "--test-output" in path.read_text(encoding="utf-8")
    ]
    assert wired, "no workflow feeds a captured run to check_tag_claims.py"


def test_the_captured_run_is_redirected_and_not_piped():
    """A pipe replaces the exit code with the last command's, so a failing
    suite would reach the checker as a file to read rather than a failure."""
    for path in Path(".github/workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        if "--test-output" not in text:
            continue
        assert "| tee" not in text, f"{path.name} pipes the run through tee"


def test_the_seed_tag_workflow_is_not_forked():
    """It is copied verbatim so a fix to the shared rule arrives on the next pin
    bump. A local edit would be clobbered by propagation or refuse it."""
    ours = Path(".github/workflows/tag-claims.yml").read_text(encoding="utf-8")
    seed = Path("governance/qm/project-seed/ci/tag-claims.yml").read_text(encoding="utf-8")
    assert ours == seed, "tag-claims.yml has diverged from the seed"
