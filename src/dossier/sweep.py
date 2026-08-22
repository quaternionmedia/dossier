"""One change, carried across every repository that needs it.

    dossier sweep find <package>
    dossier sweep plan <package> --to <version>

**A SWEEP IS ONE DELTA WITH MANY PARTS.** Bumping `fastapi` is not twenty-four
pieces of work that happen to look alike; it is one piece of work with a
twenty-four repository blast radius, and closing it means closing all of them.
That is exactly what `part-of` says, so a sweep is a delta and each repository's
share is `part-of` it -- `governance/qm/records/DRAFT-deltas-compose.md`.

Stating it that way buys the thing a list of pull requests cannot: the sweep has
a single state. Twenty-three merged and one failing is a sweep in progress, not
twenty-three successes and a straggler nobody is counting.

**THE SHAPE OF THE WORK DECIDES THE TOOL.** Most of a dependency sweep is
mechanical -- find the constraint, change the number, run the tests. A model is
the wrong instrument for that: it is slower, it costs something, and it can be
wrong about an edit that a parser is never wrong about. So this module works out
*what shape* each repository's share is, and something else decides what to run.
`qmcp.sweep` is that something else, and `Shape` is the whole vocabulary between
them.

**WHAT THIS CANNOT DO.** Know whether a version is safe, or whether a repository
should take it. It reads what is declared and reports who declares it. The
decision to sweep is a person's, the approval is a person's, and this is the
part that can be checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlmodel import select

from dossier.models.schemas import Project, ProjectDependency

# What kind of work one repository's share is, which decides what runs it.
#
# THIS IS THE WHOLE ARCHITECTURE, AND IT IS FOUR WORDS. A dispatcher that asked
# "which agent" would be choosing between implementations; asking "what shape"
# lets the answer be a parser today, a local model tomorrow, and a person for
# the cases that were always going to be a person's. Nothing here names a tool.
MECHANICAL = "mechanical"
"""A constraint to rewrite. A parser does this correctly every time."""

JUDGEMENT = "judgement"
"""Something ambiguous: an unusual manifest, a test failure to read. A model or
a person, and which one is a deployment decision rather than a design one."""

HUMAN = "human"
"""A person's by constitution -- `ci/attested-registry.yaml`. Never dispatched."""

UNKNOWN = "unknown"
"""Nothing here could tell. Not zero work and not none: unread."""

SHAPES = (MECHANICAL, JUDGEMENT, HUMAN, UNKNOWN)

# Manifests whose constraints this can rewrite without reading prose. A file
# outside this set is `judgement` rather than a failure: somebody has to look,
# and saying so is the honest outcome.
MECHANICAL_MANIFESTS = ("pyproject.toml", "requirements.txt", "package.json")

# A bare constraint -- `>=0.115.0`, `~=0.100` -- because that is what the model
# stores in `version_spec`. A first version of this expected `name op version`
# and matched none of the twenty-four real rows, which shaped every share
# `judgement` and looked like a cautious tool rather than a broken pattern.
_CONSTRAINT = re.compile(r"^\s*(?P<op>[<>=!~^]*)\s*"
                         r"(?P<version>[0-9][0-9A-Za-z.\-+]*)\s*$")


@dataclass(frozen=True)
class Share:
    """One repository's part of a sweep."""

    project: str
    declared: str | None
    """The constraint as the repository states it, or None when it declares the
    package with no version -- which is a real answer and not a missing one."""

    manifest: str | None = None
    shape: str = UNKNOWN
    why: str = ""
    """Why this shape, in words. A shape without a reason is a verdict."""

    @property
    def address(self) -> str:
        return f"{self.project}/delta/the-work"


@dataclass
class Sweep:
    """One change and every repository it touches."""

    package: str
    to_version: str | None = None
    shares: list[Share] = field(default_factory=list)

    @property
    def blast_radius(self) -> int:
        """How many repositories this change reaches."""
        return len(self.shares)

    @property
    def address(self) -> str:
        """The sweep's own delta. Named for the change, not for the day it ran.

        A sweep named by date would be a different delta every time somebody
        re-ran it, and the second one would carry none of the first one's
        approvals.
        """
        target = self.to_version or "current"
        return f"quaternionmedia/sweep/delta/{self.package}-{target}"

    def by_shape(self) -> dict[str, list[Share]]:
        found: dict[str, list[Share]] = {shape: [] for shape in SHAPES}
        for share in self.shares:
            found.setdefault(share.shape, []).append(share)
        return found

    def relations(self) -> list[dict[str, Any]]:
        """Each repository's share, `part-of` the sweep.

        Not `crosses`: the repositories do not interact here. They each take the
        same change, and the sweep is closed when all of them have. `part-of` is
        the relation that says closing the whole requires closing this.
        """
        return [
            {"schema": 1, "source": share.address, "relation": "part-of",
             "target": self.address,
             "stated_by": f"dossier sweep: declares {self.package}"}
            for share in self.shares
        ]

    def summary(self) -> str:
        counts = {shape: len(rows) for shape, rows in self.by_shape().items()
                  if rows}
        target = f" to {self.to_version}" if self.to_version else ""
        lines = [
            f"{self.package}{target}: {self.blast_radius} repositor"
            f"{'y' if self.blast_radius == 1 else 'ies'}",
            "  " + ", ".join(f"{n} {shape}" for shape, n in counts.items()),
        ]
        return "\n".join(lines)


def find(session: Any, package: str) -> Sweep:
    """Every repository declaring `package`, and what shape its share is.

    Reads what is declared. A repository that depends on something transitively
    is not here, and that is a limit of the data rather than a claim that it is
    unaffected -- `dossier sync` records declared dependencies, so that is what
    can be swept.
    """
    rows = session.exec(
        select(Project, ProjectDependency)
        .join(ProjectDependency, ProjectDependency.project_id == Project.id)
        .where(ProjectDependency.name == package)
    ).all()

    shares = [
        _share(project, dependency, package)
        for project, dependency in rows
    ]
    shares.sort(key=lambda s: s.project)
    return Sweep(package=package, shares=shares)


# What the models write when they have nothing. Treated as absent rather than
# as a value, because that is what they mean by it.
SENTINELS = ("unknown", "", "none", "null")


def _real(value: Any) -> str | None:
    """A stored value, or None when it is one of the model's sentinels."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in SENTINELS else text


def _share(project: Any, dependency: Any, package: str) -> Share:
    # `version_spec` and `source`, which are what the model calls them. A first
    # pass guessed `version` and `source_file`; every one of the twenty-four
    # real rows came back with both fields None and every share was shaped
    # `unknown`, which read as missing data rather than as a wrong field name.
    # A uniform result is a tooling fault until shown otherwise.
    #
    # **THE SENTINEL IS THE WORD, NOT NONE.** `ProjectDependency.source`
    # defaults to the string `"unknown"`, so a row with no manifest arrives
    # carrying a truthy value that is not a filename. Reading it as one shapes
    # the share `judgement` -- "a manifest this cannot rewrite" -- when the
    # truth is that there is no manifest at all. The model was already saying
    # unknown; this is honouring it rather than re-deciding it.
    manifest = _real(getattr(dependency, "source", None))
    declared = _real(getattr(dependency, "version_spec", None))
    name = project.full_name or project.name

    if manifest and manifest.rsplit("/", 1)[-1] in MECHANICAL_MANIFESTS:
        return Share(project=name, declared=declared, manifest=manifest,
                     shape=MECHANICAL,
                     why=f"{manifest} is a manifest this can rewrite")
    if manifest:
        return Share(project=name, declared=declared, manifest=manifest,
                     shape=JUDGEMENT,
                     why=f"{manifest} is not a manifest this can rewrite")
    return Share(project=name, declared=declared, manifest=None,
                 shape=UNKNOWN,
                 why="no manifest recorded, so nothing knows where the "
                     "constraint is written")


def bump(declared: str | None, to_version: str) -> str | None:
    """The constraint rewritten to `to_version`, or None when it cannot be.

    Returns None rather than guessing. A constraint this cannot parse is a
    `judgement` share, and turning it into a wrong edit silently is the failure
    a mechanical tool is supposed to be incapable of.

    A COMMA IS A REFUSAL. `<1.0.0,>=0.92.0` is two constraints, and rewriting it
    to one number would throw away a ceiling somebody put there on purpose.
    """
    if not declared or "," in declared:
        return None
    found = _CONSTRAINT.match(declared)
    if not found:
        return None
    operator = found.group("op") or ">="
    return f"{operator}{to_version}"


def already_ahead(declared: str | None, to_version: str) -> bool:
    """Whether this repository already asks for at least `to_version`.

    **THE REAL ARCHIVE FOUND THIS ONE.** Sweeping `fastapi` to 0.116.0 across
    twenty-four repositories would have rewritten `>=0.135.2` to `>=0.116.0` --
    a downgrade, applied mechanically, to a repository that was ahead of the
    sweep. A version bump is not monotonic across an organisation just because
    it is a bump in the repository somebody was looking at.

    False when nothing can be compared. Unknown is not "no".
    """
    if not declared:
        return False
    found = _CONSTRAINT.match(declared.split(",")[0])
    if not found:
        return False
    try:
        from packaging.version import InvalidVersion, Version

        return Version(found.group("version")) >= Version(to_version)
    except (ImportError, InvalidVersion):
        return False


def furthest_ahead(sweep: Sweep) -> str | None:
    """The highest version any repository in this sweep already asks for.

    **A SWEEP'S TARGET IS DERIVED, NOT TYPED IN.** The panel used a constant --
    `0.116.0` -- for whatever package the sweep landed on, so sweeping anything
    but `fastapi` proposed a version from an unrelated project's history. A
    number that arrives from nowhere is a number nobody can check.

    This is the number the organisation already contains: bring everyone to
    where the furthest-ahead repository already is. It is conservative by
    construction -- it can never propose a version no repository has adopted --
    and it needs no network, which matters because `already_ahead` exists
    precisely because a bump is not monotonic across an organisation.

    Returns None when nothing declares a comparable version, which is a real
    answer: there is no target to derive, and the caller must ask a person
    rather than pick one.
    """
    try:
        from packaging.version import InvalidVersion, Version
    except ImportError:                            # pragma: no cover
        return None

    best: Any = None
    best_text: str | None = None
    for share in sweep.shares:
        if not share.declared:
            continue
        found = _CONSTRAINT.match(share.declared.split(",")[0])
        if not found:
            continue
        try:
            version = Version(found.group("version"))
        except InvalidVersion:
            continue
        if best is None or version > best:
            best, best_text = version, found.group("version")
    return best_text


def plan(sweep: Sweep, to_version: str) -> Sweep:
    """The same sweep with a target version, re-shaped against it.

    A share whose constraint cannot be rewritten moves from `mechanical` to
    `judgement` here, which is the point: the shape is a property of the work
    *and the change*, not of the repository alone.
    """
    shares = []
    for share in sweep.shares:
        if share.shape != MECHANICAL:
            shares.append(share)
            continue
        if already_ahead(share.declared, to_version):
            shares.append(Share(
                project=share.project, declared=share.declared,
                manifest=share.manifest, shape=JUDGEMENT,
                why=f"already asks for {share.declared}, which is at or ahead "
                    f"of {to_version} -- sweeping it would move it back"))
        elif bump(share.declared, to_version) is None:
            shares.append(Share(
                project=share.project, declared=share.declared,
                manifest=share.manifest, shape=JUDGEMENT,
                why=f"{share.declared!r} is not a constraint this can rewrite"))
        else:
            shares.append(share)
    return Sweep(package=sweep.package, to_version=to_version, shares=shares)


def shared_needs(session: Any, at_least: int = 2) -> list[tuple[str, int]]:
    """Packages declared by at least `at_least` repositories, widest first.

    The starting point: what is worth sweeping is what many repositories share,
    because that is where one decision saves the most repeated ones -- and where
    getting it wrong costs the most, which is the same number.
    """
    from sqlalchemy import func

    rows = session.exec(
        select(ProjectDependency.name,
               func.count(func.distinct(ProjectDependency.project_id)))
        .group_by(ProjectDependency.name)
        .having(func.count(func.distinct(ProjectDependency.project_id)) >= at_least)
        .order_by(func.count(func.distinct(ProjectDependency.project_id)).desc())
    ).all()
    return [(name, count) for name, count in rows]
