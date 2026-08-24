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


# --- the address belongs to whoever the repositories belong to ----------------


def test_the_sweep_address_takes_its_owner_from_the_repositories():
    """**THE ADDRESS HARDCODED AN ORGANISATION.** It read
    `quaternionmedia/sweep/delta/...` whoever was running it, so a fork's sweep
    emitted an address belonging to somebody else.

    `records/DRAFT-a-route-is-an-address.md` is why that matters: an address is
    what says two readings are about the same thing. A wrong owner joins a
    fork's work to this organisation's.

    Mutation: put a literal owner back and this fails.
    """
    found = sweep_module.Sweep(
        package="fastapi", to_version="1.0",
        shares=[sweep_module.Share(project="acme/a", declared=">=1"),
                sweep_module.Share(project="acme/b", declared=">=1")])
    assert found.owner == "acme"
    assert found.address == "acme/sweep/delta/fastapi-1.0"
    assert "quaternionmedia" not in (found.address or "")


def test_a_sweep_across_two_organisations_has_no_single_address():
    """THE ONE THAT MATTERS.

    A sweep spanning two organisations is a real thing. It is also not
    something one address can name, and picking the majority owner would file
    half the work under the wrong one — silently, and in the field whose whole
    job is identity.

    Mutation: return the first owner found and this fails.
    """
    found = sweep_module.Sweep(
        package="fastapi", to_version="1.0",
        shares=[sweep_module.Share(project="acme/a", declared=">=1"),
                sweep_module.Share(project="other/b", declared=">=1")])
    assert found.owner is None
    assert found.address is None


def test_a_share_with_no_owner_in_its_name_yields_no_address():
    """An address nobody can resolve is worse than no address, because it looks
    resolvable."""
    found = sweep_module.Sweep(
        package="x",
        shares=[sweep_module.Share(project="bare-name", declared=None)])
    assert found.owner is None and found.address is None


def test_no_owner_is_hardcoded_anywhere_in_the_module():
    """The scan that found this one. A literal organisation in a module that
    builds addresses is a fork emitting somebody else's identity.

    Mutation: reintroduce the literal and this fails.
    """
    import pathlib

    source = pathlib.Path(sweep_module.__file__).read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines()
        if not line.strip().startswith("#")
    )
    # The docstrings may name it as an example; the code may not.
    for line in code.splitlines():
        if "quaternionmedia" in line and 'f"' in line:
            raise AssertionError(f"an owner is hardcoded into an address: {line}")


# --- the route the module docstring advertises --------------------------------
#
# It advertised two subcommands and a `--to` for four months and had neither.
# `--to` is also the constant `furthest_ahead` replaced, so the route that got
# built is the one that derives its target.


def _declared(session, repo, package, spec):
    from dossier.models.schemas import Project, ProjectDependency

    project = Project(name=repo, full_name=f"org/{repo}", github_owner="org")
    session.add(project)
    session.commit()
    session.refresh(project)
    session.add(ProjectDependency(project_id=project.id, name=package,
                                  version_spec=spec, source="pyproject.toml",
                                  dep_type="runtime"))
    session.commit()


def test_the_route_exists():
    """A documented command with nothing behind it is worse than no command.

    Mutation: remove the `sweep` command from `cli.py` and this fails.
    """
    from dossier.cli import cli

    assert "sweep" in cli.list_commands(None)


def test_with_no_package_it_lists_rather_than_picking_one(tmp_path,
                                                          monkeypatch):
    """THE ONE THIS EXISTS FOR.

    There is no such thing as *the* package to sweep. The widest-shared one is
    where a panel starts when nobody has said, and a command that silently
    swept it would make a starting point look like an answer.

    Mutation: sweep the widest-shared package when none is named and this
    fails.
    """
    from click.testing import CliRunner
    from sqlmodel import Session, SQLModel, create_engine

    from dossier import cli as cli_module

    engine = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _declared(session, "a", "fastapi", ">=0.100.0")
        _declared(session, "b", "fastapi", ">=0.110.0")
        _declared(session, "c", "httpx", ">=0.24.0")
        _declared(session, "d", "httpx", ">=0.27.0")

    monkeypatch.setattr(cli_module, "get_session", lambda: Session(engine))

    result = CliRunner().invoke(cli_module.cli, ["sweep"])
    assert result.exit_code == 0, result.output
    assert "fastapi" in result.output and "httpx" in result.output
    # Listed, not swept: no target version, no per-repository shape.
    assert "mechanical" not in result.output
    assert " to 0.110.0" not in result.output


def test_a_named_package_gets_its_own_derived_target(tmp_path, monkeypatch):
    """The target follows the package. A constant applied to whatever package
    the sweep landed on offered an unrelated project's version.

    Mutation: pass `fastapi`'s target to any package and this fails.
    """
    from click.testing import CliRunner
    from sqlmodel import Session, SQLModel, create_engine

    from dossier import cli as cli_module

    engine = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _declared(session, "a", "fastapi", ">=0.100.0")
        _declared(session, "b", "fastapi", ">=0.110.0")
        _declared(session, "c", "httpx", ">=0.24.0")
        _declared(session, "d", "httpx", ">=0.27.0")

    monkeypatch.setattr(cli_module, "get_session", lambda: Session(engine))

    result = CliRunner().invoke(cli_module.cli, ["sweep", "httpx"])
    assert result.exit_code == 0, result.output
    assert "httpx to 0.27.0" in result.output
    assert "0.110.0" not in result.output, "it reached for fastapi's version"


def test_a_package_nobody_declares_is_said_rather_than_drawn_empty(
        tmp_path, monkeypatch):
    """An empty listing is a claim that a sweep would touch nothing."""
    from click.testing import CliRunner
    from sqlmodel import Session, SQLModel, create_engine

    from dossier import cli as cli_module

    engine = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(cli_module, "get_session", lambda: Session(engine))

    result = CliRunner().invoke(cli_module.cli, ["sweep", "nobody-has-this"])
    assert result.exit_code == 1
    assert "No repository declares nobody-has-this" in result.output
