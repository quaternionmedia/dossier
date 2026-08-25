"""Which repository a row is about.

**NOT EVERY ROW IN `project` IS A REPOSITORY.** Four of them are delta
addresses — `quaternionmedia/qm/delta/pr-57` — carrying `github_owner` and
`github_repo` that name the repository the delta belongs to. They are not
mistakes and there is nothing to clean up; they are addresses in a table whose
name suggests otherwise.

Two readings got this wrong in different ways. The clone command took the last
segment of the name and offered to clone `pr-57` into a directory beside this
checkout. The overview's attention list read them as repositories nobody had
synced, and recommended syncing four things that can never be synced — noise
that could not be cleared by acting on it, which is the worst kind.

So the question has one answer, here, and both ask it.
"""

from __future__ import annotations

from typing import Any


def repository_of(project: Any) -> tuple[str, str]:
    """The `owner/name` and bare directory name a row belongs to.

    Falls back to the stated name only for a plain `owner/name`: guessing at an
    address with more parts than that is what produced a pull request offered
    as somewhere to clone.

    Returns `("", "")` for a row naming no repository at all, which a caller
    skips rather than guesses at.
    """
    owner = getattr(project, "github_owner", None)
    repo = getattr(project, "github_repo", None)
    if owner and repo:
        return f"{owner}/{repo}", repo
    stated = getattr(project, "full_name", None) or getattr(project, "name", None) or ""
    if stated.count("/") == 1:
        return stated, stated.split("/")[-1]
    return stated, ""


def is_a_repository(project: Any) -> bool:
    """Whether this row *is* a repository rather than an address inside one.

    A delta address carries the owner and repo of the repository it sits in, so
    those fields alone cannot tell the two apart — what distinguishes them is
    whether the row's own name is exactly that repository.
    """
    repo, name = repository_of(project)
    if not name:
        return False
    stated = getattr(project, "full_name", None) or getattr(project, "name", None) or ""
    return stated == repo
