"""One change across many repositories, and what shape each share is.

THE TEST WORTH READING IS THE DOWNGRADE ONE. A version bump is not monotonic
across an organisation just because it is a bump in the repository somebody was
looking at. Sweeping `fastapi` to 0.116.0 across the real archive would have
rewritten six repositories backwards, including this one.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine

from dossier.models.schemas import Project, ProjectDependency
import dossier.sweep as sweep_module
from dossier.sweep import (
    JUDGEMENT,
    MECHANICAL,
    UNKNOWN,
    already_ahead,
    bump,
    find,
    plan,
    shared_needs,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def declare(session, repo, package, spec, source="pyproject.toml"):
    project = session.exec(
        __import__("sqlmodel").select(Project).where(Project.name == repo)).first()
    if project is None:
        project = Project(name=repo, full_name=repo, github_owner="org")
        session.add(project)
        session.commit()
        session.refresh(project)
    session.add(ProjectDependency(project_id=project.id, name=package,
                                  version_spec=spec, source=source,
                                  dep_type="runtime"))
    session.commit()
    return project


# --- the downgrade ------------------------------------------------------------


def test_a_repository_already_ahead_is_not_swept_backwards(session):
    """THE ONE THAT MATTERS.

    Found against the real archive: `dossier` declares `>=0.128.0` and a sweep
    to 0.116.0 would have rewritten it to `>=0.116.0`. Mechanically correct,
    and a downgrade nobody asked for -- applied to six repositories at once,
    which is what a sweep is for and why it is dangerous.

    Mutation: drop the `already_ahead` branch and this fails.
    """
    declare(session, "org/behind", "fastapi", ">=0.100.0")
    declare(session, "org/ahead", "fastapi", ">=0.128.0")

    swept = plan(find(session, "fastapi"), "0.116.0")
    shapes = {s.project: s.shape for s in swept.shares}

    assert shapes["org/behind"] == MECHANICAL
    assert shapes["org/ahead"] == JUDGEMENT
    ahead = next(s for s in swept.shares if s.project == "org/ahead")
    assert "ahead" in ahead.why and "back" in ahead.why


def test_already_ahead_is_false_when_nothing_can_be_compared():
    """Unknown is not "no". A constraint nobody can parse must not be reported
    as safely behind the target."""
    assert already_ahead(None, "1.0.0") is False
    assert already_ahead("whatever-this-is", "1.0.0") is False


def test_an_equal_version_counts_as_ahead():
    """Rewriting `>=1.2.3` to `>=1.2.3` is a change with no content, and a pull
    request per repository for no change is worse than none."""
    assert already_ahead(">=1.2.3", "1.2.3") is True


# --- what can be rewritten ----------------------------------------------------


def test_a_bare_constraint_is_what_the_model_stores():
    """`version_spec` holds `>=0.115.0`, not `fastapi>=0.115.0`. A pattern
    expecting the name matched none of the twenty-four real rows and shaped
    every share `judgement`, which read as caution rather than as a bug.

    Mutation: require a name in the pattern and this fails.
    """
    assert bump(">=0.115.0", "0.116.0") == ">=0.116.0"
    assert bump("~=0.100", "0.116.0") == "~=0.116.0"


def test_a_missing_operator_becomes_a_floor():
    assert bump("1.2.3", "2.0.0") == ">=2.0.0"


def test_two_constraints_are_refused_rather_than_flattened():
    """`<1.0.0,>=0.92.0` has a ceiling somebody put there on purpose, and
    rewriting it to one number throws that away.

    Mutation: split on the comma and rewrite the first part, and this fails.
    """
    assert bump("<1.0.0,>=0.92.0", "0.116.0") is None


def test_something_unparseable_is_refused_rather_than_guessed():
    """The failure a mechanical tool is supposed to be incapable of."""
    assert bump("whatever the lockfile said", "1.0.0") is None
    assert bump(None, "1.0.0") is None


# --- shapes -------------------------------------------------------------------


def test_a_manifest_this_cannot_rewrite_is_judgement_not_failure(session):
    """Somebody has to look. Saying so is the honest outcome, and it keeps the
    share in the sweep rather than dropping it."""
    declare(session, "org/odd", "fastapi", ">=1.0.0", source="Pipfile.lock")
    swept = find(session, "fastapi")
    assert swept.shares[0].shape == JUDGEMENT
    assert "Pipfile.lock" in swept.shares[0].why


def test_no_manifest_recorded_is_unknown_rather_than_mechanical(session):
    """Not zero work and not none: unread. A share with nowhere to write the
    constraint cannot be rewritten by anything.

    Mutation: default the shape to `mechanical` and this fails.
    """
    declare(session, "org/vague", "fastapi", ">=1.0.0", source=None)
    swept = find(session, "fastapi")
    assert swept.shares[0].shape == UNKNOWN


def test_every_share_says_why_it_is_the_shape_it_is(session):
    """A shape without a reason is a verdict."""
    declare(session, "org/a", "fastapi", ">=1.0.0")
    declare(session, "org/b", "fastapi", ">=1.0.0", source="Pipfile.lock")
    for share in plan(find(session, "fastapi"), "2.0.0").shares:
        assert share.why, f"{share.project} has no reason"


# --- the sweep is one delta ---------------------------------------------------


def test_every_share_is_part_of_the_sweep(session):
    """Not `crosses`: the repositories do not interact, they each take the same
    change, and the sweep closes when all of them have.

    Mutation: emit `crosses` and this fails.
    """
    declare(session, "org/a", "fastapi", ">=1.0.0")
    declare(session, "org/b", "fastapi", ">=1.0.0")

    swept = find(session, "fastapi")
    relations = swept.relations()
    assert len(relations) == 2
    assert {r["relation"] for r in relations} == {"part-of"}
    assert {r["target"] for r in relations} == {swept.address}


def test_the_sweep_is_named_for_the_change_not_the_day(session):
    """A sweep named by date is a different delta every run, and the second one
    carries none of the first one's approvals."""
    declare(session, "org/a", "fastapi", ">=1.0.0")
    first = plan(find(session, "fastapi"), "2.0.0")
    second = plan(find(session, "fastapi"), "2.0.0")
    assert first.address == second.address
    assert "fastapi-2.0.0" in first.address


def test_the_blast_radius_is_the_repository_count(session):
    declare(session, "org/a", "fastapi", ">=1.0.0")
    declare(session, "org/b", "fastapi", ">=1.0.0")
    declare(session, "org/c", "fastapi", ">=1.0.0")
    assert find(session, "fastapi").blast_radius == 3


def test_a_package_nobody_declares_is_an_empty_sweep(session):
    """Empty and not an error: nothing to do is a real answer."""
    declare(session, "org/a", "fastapi", ">=1.0.0")
    swept = find(session, "nothing-uses-this")
    assert swept.blast_radius == 0
    assert swept.relations() == []


# --- where to start -----------------------------------------------------------


def test_shared_needs_orders_by_how_many_repositories_share_it(session):
    """What is worth sweeping is what many repositories share -- which is also
    where getting it wrong costs the most, and it is the same number."""
    declare(session, "org/a", "fastapi", ">=1.0.0")
    declare(session, "org/b", "fastapi", ">=1.0.0")
    declare(session, "org/c", "fastapi", ">=1.0.0")
    declare(session, "org/a", "click", ">=8.0.0")
    declare(session, "org/b", "click", ">=8.0.0")
    declare(session, "org/a", "lonely", ">=1.0.0")

    found = shared_needs(session, at_least=2)
    assert found[0] == ("fastapi", 3)
    assert ("click", 2) in found
    assert all(name != "lonely" for name, _ in found), "one repository is not shared"


def test_the_summary_counts_each_shape(session):
    declare(session, "org/a", "fastapi", ">=1.0.0")
    declare(session, "org/b", "fastapi", ">=9.0.0")
    summary = plan(find(session, "fastapi"), "2.0.0").summary()
    assert "2 repositories" in summary
    assert "mechanical" in summary and "judgement" in summary


# --- the target version comes from the data ------------------------------------


def test_the_target_is_the_furthest_ahead_repository():
    """**A SWEEP'S TARGET IS DERIVED, NOT TYPED IN.**

    The panel used a constant, `0.116.0`, for whatever package the sweep landed
    on — so sweeping anything but `fastapi` proposed a version out of an
    unrelated project's history. The organisation already contains the answer:
    bring everyone to where the furthest-ahead repository already is.

    Mutation: return the lowest version and this fails.
    """
    found = sweep_module.furthest_ahead(sweep_module.Sweep(
        package="fastapi",
        shares=[
            sweep_module.Share(project="a", declared=">=0.100.0"),
            sweep_module.Share(project="b", declared=">=0.135.2"),
            sweep_module.Share(project="c", declared=">=0.116.0"),
        ]))
    assert found == "0.135.2"


def test_a_target_is_never_a_version_nobody_has_adopted():
    """Conservative by construction: the derived target is always a version
    some repository already asks for, so a sweep cannot propose a release the
    organisation has never used.

    Mutation: add one to the highest version and this fails.
    """
    declared = [">=1.2.0", "==1.4.1", ">=1.3.0"]
    found = sweep_module.furthest_ahead(sweep_module.Sweep(
        package="x",
        shares=[sweep_module.Share(project=str(n), declared=d)
                for n, d in enumerate(declared)]))
    assert found == "1.4.1"


def test_nothing_comparable_gives_no_target_rather_than_a_guess():
    """THE ONE THAT MATTERS.

    No comparable version is a real answer — there is no target to derive — and
    the caller must ask a person rather than pick one. Returning a default here
    is exactly how a constant got into the panel in the first place.

    Mutation: fall back to a literal version and this fails.
    """
    for declared in (None, "", "not-a-constraint", "*"):
        found = sweep_module.furthest_ahead(sweep_module.Sweep(
            package="x",
            shares=[sweep_module.Share(project="a", declared=declared)]))
        assert found is None, f"{declared!r} produced {found!r}"


def test_a_derived_target_never_moves_anybody_backwards():
    """The derived target is the maximum, so `already_ahead` is true for at
    most the repository it came from and never proposes a downgrade.

    This is the property the constant broke: sweeping to 0.116.0 would have
    rewritten `>=0.135.2` downwards.
    """
    shares = [sweep_module.Share(project="a", declared=">=0.100.0"),
              sweep_module.Share(project="b", declared=">=0.135.2")]
    target = sweep_module.furthest_ahead(
        sweep_module.Sweep(package="x", shares=shares))
    for share in shares:
        assert not sweep_module.bump(share.declared, target) or \
            not _moves_backwards(share.declared, target)


def _moves_backwards(declared: str, target: str) -> bool:
    from packaging.version import Version
    import re
    found = re.search(r"(\d+(?:\.\d+)*)", declared or "")
    return bool(found) and Version(found.group(1)) > Version(target)
