"""Where one project meets the others.

A project page that lists only its own facts answers "what is this?" and not
"what does changing it touch?". This computes the second question: the other
projects this one shares something with, and what the sharing is.

FOUR KINDS OF INTERSECTION, AND THEY ARE NOT THE SAME STRENGTH.

  * **Governance** -- the corpus, carried as a submodule. Repositories in the
    roster pin the same corpus, so a corpus change reaches all of them by
    propagation. This is the strongest link here: it is a declared adoption
    with a branch, a pin and a distance from the corpus tip.
  * **Dependencies** -- two projects declaring the same package. Real and
    weak: sharing `pytest` says almost nothing, sharing an internal package
    says a great deal, and this cannot tell them apart. It reports the overlap
    and the manifest it was read from, and leaves the reading to a person.
  * **Contributors** -- the same people. The link that predicts which changes
    land together, and the one no dependency graph shows.
  * **Declared components** -- links somebody entered by hand. Fewest, and the
    only ones carrying an intent rather than an observation.

WHAT IT CANNOT DO. See an integration nobody declared. Two services that talk
over HTTP share no package, no submodule and possibly no author, and nothing
here will find them. The absence of a row is not evidence of independence, and
the view says so rather than implying coverage it does not have.

It reuses `dossier.overview.Section` so one renderer draws both, and a reader
learns one table shape rather than two.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlmodel import select

from dossier.models.governance import GovernanceRepository
from dossier.models.schemas import (
    Project,
    ProjectComponent,
    ProjectContributor,
    ProjectDependency,
)
from dossier.overview import Section, _ago, _age_days, _trim, owner_of

# Packages so widely declared that a shared one says nothing about two projects
# being related. Listed rather than inferred from a count, because the cutoff
# would otherwise move every time a repository is synced.
UBIQUITOUS = frozenset({
    "pytest", "ruff", "mypy", "black", "flake8", "isort", "setuptools", "wheel",
    "pip", "typing-extensions", "requests", "urllib3", "certifi",
    "eslint", "prettier", "typescript", "jest", "vite",
})


def _governance(session: Any, project: Any, now: Any) -> Section:
    """The corpus this project pins, and everyone else pinning it."""
    slug = (project.github_repo or project.name.split("/")[-1] or "").lower()
    row = session.exec(
        select(GovernanceRepository).where(func.lower(GovernanceRepository.name) == slug)
    ).first()

    if row is None:
        return Section(
            "Governance", ("", ""), (),
            note=("This project is not in the corpus roster, so it pins no corpus and "
                  "no propagation reaches it. That is a fact about the roster, not a "
                  "verdict about the project."),
        )

    cohort = session.exec(select(func.count()).select_from(GovernanceRepository)).one()
    cohort = cohort[0] if isinstance(cohort, tuple) else cohort
    rows = (
        ("submodule branch", row.branch_ref or "--"),
        ("pinned commit", (row.branch_commit or "--")[:12]),
        ("behind corpus", str(row.behind_corpus) if row.behind_corpus is not None
         else (row.behind_corpus_unknown or "--")),
        ("ahead of corpus", str(row.ahead_of_corpus) if row.ahead_of_corpus is not None
         else (row.ahead_of_corpus_unknown or "--")),
        ("seed drift", row.seed_drift or row.seed_drift_unknown or "--"),
        ("last propagation", _ago(_age_days(row.last_propagation, now))
         if row.last_propagation else (row.last_propagation_unknown or "--")),
        ("phase (claim)", row.phase or "--"),
        ("precondition (evidence)", row.precondition or row.precondition_unknown or "--"),
        ("release", row.release_state or row.release_unknown or "--"),
        ("shares this corpus with", f"{cohort - 1} other repositories in the roster"),
    )
    return Section(
        "Governance", ("", ""), rows,
        note=("The corpus is carried as a submodule, so every repository above pins the "
              "same documents and a corpus change reaches them by propagation. Values "
              "are the generator's own words; phase is a claim and precondition is "
              "evidence."),
    )


def _dependencies(session: Any, project: Any, limit: int) -> Section:
    """Other projects declaring the same packages."""
    mine = {
        d.name: d.source
        for d in session.exec(
            select(ProjectDependency).where(ProjectDependency.project_id == project.id)
        ).all()
    }
    interesting = {n for n in mine if n.lower() not in UBIQUITOUS}
    if not interesting:
        return Section(
            "Shared dependencies", ("repo", "packages", "shared", "manifest"), (),
            note=("Nothing declared here is shared beyond the ubiquitous tools. A "
                  "project with no manifest synced looks identical to one with no "
                  "dependencies."),
        )

    others = session.exec(
        select(ProjectDependency, Project)
        .join(Project, Project.id == ProjectDependency.project_id)
        .where(ProjectDependency.project_id != project.id)
        .where(ProjectDependency.name.in_(interesting))
    ).all()

    overlap: dict[str, set[str]] = {}
    manifests: dict[str, set[str]] = {}
    for dep, other in others:
        if other.is_fork:
            continue
        key = other.full_name or other.name
        overlap.setdefault(key, set()).add(dep.name)
        manifests.setdefault(key, set()).add(dep.source)

    ranked = sorted(overlap.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    rows = tuple(
        (_trim(name, 30), str(len(shared)),
         _trim(", ".join(sorted(shared)), 46),
         _trim(", ".join(sorted(manifests[name])), 24))
        for name, shared in ranked[:limit]
    )
    return Section(
        "Shared dependencies", ("repo", "packages", "shared", "manifest"), rows,
        note=("Ubiquitous tooling is excluded, so a row here is a package two projects "
              "chose. It is still an observation and not an integration: sharing a "
              "library is not the same as talking to each other. Forks are excluded."),
    )


def _contributors(session: Any, project: Any, limit: int) -> Section:
    """People who work on this project and on others."""
    mine = {
        c.username for c in session.exec(
            select(ProjectContributor).where(ProjectContributor.project_id == project.id)
        ).all()
    }
    if not mine:
        return Section("Shared contributors", ("repo", "people", "who"), (),
                       note="No contributors synced for this project.")

    rows_by_repo: dict[str, set[str]] = {}
    for contributor, other in session.exec(
        select(ProjectContributor, Project)
        .join(Project, Project.id == ProjectContributor.project_id)
        .where(ProjectContributor.project_id != project.id)
        .where(ProjectContributor.username.in_(mine))
    ).all():
        if other.is_fork:
            continue
        rows_by_repo.setdefault(other.full_name or other.name, set()).add(
            contributor.username)

    ranked = sorted(rows_by_repo.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    rows = tuple(
        (_trim(name, 30), str(len(people)), _trim(", ".join(sorted(people)), 52))
        for name, people in ranked[:limit]
    )
    return Section(
        "Shared contributors", ("repo", "people", "who"), rows,
        note=("The link that predicts which changes land together, and the one no "
              "dependency graph shows. Forks are excluded: their contributors are "
              "upstream's."),
    )


def _declared(session: Any, project: Any) -> Section:
    """Links somebody entered by hand."""
    links = session.exec(
        select(ProjectComponent).where(
            (ProjectComponent.parent_id == project.id)
            | (ProjectComponent.child_id == project.id)
        )
    ).all()
    names = {p.id: (p.full_name or p.name) for p in session.exec(select(Project)).all()}
    rows = tuple(
        ("parent of" if link.parent_id == project.id else "child of",
         _trim(names.get(link.child_id if link.parent_id == project.id
                         else link.parent_id, "(missing)"), 40),
         link.relationship_type or "--")
        for link in links
    )
    return Section(
        "Declared components", ("direction", "repo", "kind"), rows,
        note=("Entered by hand, so these are the only links here carrying an intent "
              "rather than an observation."),
    )


def build(session: Any, project: Any, limit: int = 10, now: Any = None) -> tuple[Section, ...]:
    """Every intersection this project has, strongest kind first."""
    from datetime import datetime, timezone

    now = now or datetime.now(timezone.utc)
    return (
        _governance(session, project, now),
        _declared(session, project),
        _dependencies(session, project, limit),
        _contributors(session, project, limit),
    )
