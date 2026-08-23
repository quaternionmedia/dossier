"""Which branches carry work that exists nowhere else.

**THE BRANCHES FACET ADMITS IT CANNOT ANSWER THIS.** Its own note says *"a
branch here is work in flight or work never cleaned up, and the two are
indistinguishable from this side"* — because that side is the GitHub sync, which
knows a branch's tip and not whether its commits are anywhere else.

They are distinguishable, from a clone. A branch whose every commit is reachable
from another ref is a label over history somebody already has; a branch with
commits on no other ref is the only copy of something. Deleting the first is
tidying and deleting the second is loss, and they look identical in a list.

**READ FROM CLONES ON THIS MACHINE, WHICH IS THE POINT.** Unlike every other
facet this is deliberately local: the question is what would be lost if this
disk died, and that question has no answer on a server. A repository with no
clone here reports `unknown` rather than zero — `qm pins` in the governance
corpus makes the same distinction for submodule pins, for the same reason.

WHAT THIS CANNOT DO. Say whether unique work is *wanted*. A stale experiment and
an unfinished feature look the same, and the branch name is the only clue. It
also cannot see a commit that is in no branch at all — reachable only from the
reflog — which is a real way to lose work and not one a branch listing finds.

**AND IT COUNTS COMMITS, NOT CHANGES.** A branch whose work reached `main` by
some other route — rewritten, reimplemented, or superseded — still has a commit
no other ref carries, and is reported at risk. That is the honest answer: git
knows the commit is unique and cannot know the change is redundant. Three
branches in `codecartographer` read this way on 2026-08-23, and all three were
in fact spent. Deciding that is reading, which is why this names the branches
rather than a total.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Namespaces `docs/ref/namespaces.md` says are never deleted. A downstream
# submodule pins a `project/` tip, and rebasing or removing one breaks it.
PERMANENT_PREFIXES = ("project/", "workspace/")
PERMANENT_EXACT = frozenset({"main", "master"})

# Branch families a bot owns. Counting them as work at risk buries the branches
# a person made in a list of dependency bumps, and nobody loses a bot's branch.
AUTOMATION_PREFIXES = ("dependabot/", "renovate/", "pre-commit-ci/")

AT_RISK = "at risk"
MERGED = "merged"
CONTAINED = "contained"
PERMANENT = "permanent"
AUTOMATION = "automation"


@dataclass
class Survey:
    """What one clone's branches are, or why they could not be read."""

    repo: str
    path: str = ""
    found: bool = False
    counts: dict[str, int] = field(default_factory=dict)
    at_risk: list[tuple[str, int]] = field(default_factory=list)
    reason: str = ""

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    return done.stdout if done.returncode == 0 else ""


def _refs(repo: Path) -> list[str]:
    listed = _git(repo, "for-each-ref", "--format=%(refname)",
                  "refs/heads", "refs/remotes")
    return [r.strip() for r in listed.splitlines()
            if r.strip() and not r.endswith("/HEAD")]


def unique_commits(repo: Path, ref: str, every_ref: list[str]) -> int:
    """Commits reachable from `ref` and from no *remote* ref.

    **REMOTES, NOT ALL REFS — AND THE DIFFERENCE IS THE WHOLE QUESTION.** This
    first compared against every ref, local ones included. Two local branches at
    the same commit then each excluded the other, both reported zero, and
    unpushed work read as safe. A false negative on exactly the question being
    asked: what survives this disk. Another name on the same machine is not a
    second copy.

    A remote-tracking ref is what somebody else has. So the count is commits
    this clone holds that no remote does, which is the definition of work in one
    place — the same one `qm pins` uses for submodule commits.

    **AND EVERY REF IS LISTED RATHER THAN EXCLUDED BY PATTERN.** An earlier
    version asked `rev-list <ref> --not --exclude=refs/heads/<name> --branches`,
    and `--exclude` matches relative to the glob that follows it, so the pattern
    never matched, every branch excluded nothing, and every count came back
    zero. That reported nothing anywhere at risk — which is both wrong and the
    answer somebody about to delete branches wants to hear.
    """
    remotes = [r for r in every_ref
               if r.startswith("refs/remotes/") and r != ref]
    if not remotes:
        # Nothing has been pushed anywhere. Every commit here is in one place.
        out = _git(repo, "rev-list", "--count", ref)
        return int(out.strip() or 0)
    out = _git(repo, "rev-list", "--count", ref, "--not", *remotes)
    return int(out.strip() or 0)


def classify(repo: Path, ref: str, every_ref: list[str], default: str) -> str:
    name = ref.split("refs/heads/", 1)[-1]
    if name in PERMANENT_EXACT or name.startswith(PERMANENT_PREFIXES):
        return PERMANENT
    if name.startswith(AUTOMATION_PREFIXES):
        return AUTOMATION
    merged = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ref, default],
        capture_output=True)
    if merged.returncode == 0:
        return MERGED
    return CONTAINED if unique_commits(repo, ref, every_ref) == 0 else AT_RISK


def _here() -> Path:
    """This clone's root — `src/dossier/branches.py` is three levels down."""
    return Path(__file__).resolve().parents[2]


def find_clone(name: str, roots: list[Path] | None = None) -> Path | None:
    """A clone of `name` beside this one, or None.

    **THE SAME RULE `qm demo` USES**: a repository beside this clone. dossier
    stores no local path for a project — `disk.py` takes its search roots from
    whoever calls it — so a facet that wants a clone has to find one, and
    inventing a second convention for where repositories live would be a second
    thing to keep true.

    The bare repository name only. Matching on the owner half as well would
    mean this had opinions about directory layout, and it has none: it looks
    for a directory with that name and a `.git` in it.
    """
    if roots is None:
        here = _here()
        roots = [here.parent, here.parent.parent]
    for root in roots:
        try:
            candidate = root / name
        except (OSError, ValueError):
            continue
        if (candidate / ".git").exists():
            return candidate
    return None


def survey(repo_name: str, path: Path | str | None) -> Survey:
    """Classify the local branches of one clone.

    Local branches only. A remote branch that is unmerged is an open pull
    request, which is ordinary and is what the Pull requests facet is for.
    """
    if path is None:
        return Survey(repo_name, reason="no clone on this machine")
    repo = Path(path)
    if not (repo / ".git").exists():
        return Survey(repo_name, path=str(repo),
                      reason="not a git clone at that path")

    default = "origin/main"
    if not _git(repo, "rev-parse", "--verify", "--quiet", default).strip():
        default = "origin/master"
        if not _git(repo, "rev-parse", "--verify", "--quiet", default).strip():
            return Survey(repo_name, path=str(repo), found=True,
                          reason="no origin/main or origin/master to measure against")

    every = _refs(repo)
    local = [r for r in every if r.startswith("refs/heads/")]

    counts: dict[str, int] = {}
    at_risk: list[tuple[str, int]] = []
    for ref in local:
        kind = classify(repo, ref, every, default)
        counts[kind] = counts.get(kind, 0) + 1
        if kind == AT_RISK:
            name = ref.split("refs/heads/", 1)[-1]
            at_risk.append((name, unique_commits(repo, ref, every)))

    at_risk.sort(key=lambda pair: (-pair[1], pair[0]))
    return Survey(repo_name, path=str(repo), found=True, counts=counts,
                  at_risk=at_risk)
