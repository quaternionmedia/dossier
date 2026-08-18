"""Backing the dossier up, and narrowing it to one owner.

WHY A MODULE AND NOT CLI BODIES. Both operations are destructive or nearly so,
and a destructive operation that only exists inside a command body cannot be
tested without invoking the command. These are plain functions over a session
and a path; `cli.py` wires them to `dossier db backup` and
`dossier projects purge`.

THE BACKUP IS SQLITE'S OWN. `Connection.backup()` copies through the online
backup API rather than copying the file, so a concurrent writer cannot leave a
torn page in the copy. A file copy of an open SQLite database is a copy that
usually works, which is worse than one that always does.

THE PURGE COUNTS BEFORE IT DELETES, AND RETURNS THE COUNT EITHER WAY. `apply`
defaults to False so the caller has to ask twice: once for the plan, once for
the deletion. A dry run and a real run walk exactly the same rows, so what the
plan reports is what the deletion does.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import select

from dossier.overview import owner_of
from dossier.models.schemas import (
    DeltaPhase,
    DocumentSection,
    Project,
    ProjectBranch,
    ProjectComponent,
    ProjectContributor,
    ProjectDelta,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
)

# Every table that hangs off a project by `project_id`. A table missing from
# this list leaves orphan rows that no view will ever show and every count will
# include, so it is spelled out rather than discovered.
CHILD_TABLES = (
    DocumentSection,
    ProjectBranch,
    ProjectContributor,
    ProjectDelta,
    ProjectDependency,
    ProjectIssue,
    ProjectLanguage,
    ProjectPullRequest,
    ProjectRelease,
)


def backup(source: Path, destination: Path) -> Path:
    """Copy `source` to `destination` through SQLite's online backup API."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return destination


def timestamped_name(source: Path, now: datetime | None = None) -> Path:
    """A backup path beside the source, stamped to the second.

    `now` is a parameter so a test can assert the name rather than parse it.
    """
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return source.with_name(f"{source.stem}.{stamp}.backup{source.suffix}")


@dataclass
class PurgePlan:
    """What a purge would remove, or did."""

    keep_owner: str
    applied: bool = False
    projects: list[str] = field(default_factory=list)
    rows_by_table: dict[str, int] = field(default_factory=dict)

    @property
    def total_rows(self) -> int:
        return len(self.projects) + sum(self.rows_by_table.values())


def purge_other_owners(session: Any, keep_owner: str, apply: bool = False) -> PurgePlan:
    """Remove every project not owned by `keep_owner`, and its rows.

    Ownership is read from `github_owner`, falling back to the owner half of
    `full_name`. A project with neither is *not* kept: an unattributable row
    cannot be shown to belong to the org, and keeping it would put it back in
    the denominator this exists to clean.
    """
    plan = PurgePlan(keep_owner=keep_owner, applied=apply)
    doomed = []
    for project in session.exec(select(Project)).all():
        if owner_of(project) != keep_owner:
            doomed.append(project)

    if not doomed:
        return plan

    ids = [p.id for p in doomed]
    plan.projects = sorted(p.name for p in doomed)

    for model in CHILD_TABLES:
        rows = session.exec(select(model).where(model.project_id.in_(ids))).all()
        if rows:
            plan.rows_by_table[model.__tablename__] = len(rows)
        if apply:
            for row in rows:
                session.delete(row)

    links = session.exec(
        select(ProjectComponent).where(
            ProjectComponent.parent_id.in_(ids) | ProjectComponent.child_id.in_(ids)
        )
    ).all()
    if links:
        plan.rows_by_table[ProjectComponent.__tablename__] = len(links)
    if apply:
        for link in links:
            session.delete(link)
        for project in doomed:
            session.delete(project)
        session.commit()
    return plan


# --- deltas ------------------------------------------------------------------

# A stub is a delta carrying no evidence that any work exists: no description,
# no branch, no issue and no pull request. It is a row somebody started typing
# and left. The rule is stated rather than guessed at from the name, because a
# name-length heuristic would delete a real delta called `ci` and spare a junk
# one called `testhtr` -- which is the wrong way round on both counts.
def is_stub(delta: Any) -> bool:
    return not any((
        (delta.description or "").strip(),
        (delta.branch_name or "").strip(),
        delta.issue_number,
        delta.pr_number,
    ))


def prune_stub_deltas(session: Any, apply: bool = False) -> list[str]:
    """Remove every delta carrying no evidence of work. Returns their names."""
    doomed = [d for d in session.exec(select(ProjectDelta)).all() if is_stub(d)]
    names = sorted(f"{d.name}" for d in doomed)
    if apply and doomed:
        for delta in doomed:
            session.delete(delta)
        session.commit()
    return names


# An open pull request is work in flight, and a delta is what this database
# calls that. `is_draft` is the one distinction worth carrying across: rad's
# corpus treats draft as "incomplete and nothing else", so a draft PR is in
# implementation and a ready one is in review.
def phase_for(pull_request: Any) -> Any:
    return DeltaPhase.IMPLEMENTATION if pull_request.is_draft else DeltaPhase.REVIEW


def deltas_from_pull_requests(session: Any, apply: bool = False) -> list[str]:
    """Make one delta per open pull request, keyed on project and PR number.

    Re-running updates rather than duplicating: identity is the project plus
    the PR number, which is the only pair that stays stable when a title is
    edited. Deltas not derived from a PR are left alone -- a delta this pass
    did not create is not a delta that should go.
    """
    existing = {
        (d.project_id, d.pr_number): d
        for d in session.exec(select(ProjectDelta)).all()
        if d.pr_number
    }
    touched: list[str] = []
    open_prs = session.exec(
        select(ProjectPullRequest).where(ProjectPullRequest.state == "open")
    ).all()

    for pr in open_prs:
        name = f"pr-{pr.pr_number}"
        row = existing.get((pr.project_id, pr.pr_number))
        phase = phase_for(pr)
        if row is None:
            row = ProjectDelta(
                project_id=pr.project_id,
                name=name,
                title=pr.title,
                description=f"Open pull request #{pr.pr_number} by {pr.author or 'unknown'}.",
                phase=phase,
                delta_type="feature",
                priority="medium",
                pr_number=pr.pr_number,
                branch_name=pr.head_branch,
            )
            if apply:
                session.add(row)
        else:
            row.title = pr.title
            row.phase = phase
            row.branch_name = pr.head_branch or row.branch_name
        touched.append(name)

    if apply:
        session.commit()
    return sorted(touched)
