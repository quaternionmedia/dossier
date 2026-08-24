"""A batch a person approves in one act, and the queue of what they cannot.

**BATCHING IS THE WHOLE FEATURE, AND IT IS NOT A CONVENIENCE.** Twenty-four
identical decisions presented one at a time are not twenty-four decisions; they
are one decision and twenty-three chances to stop reading. `PRINCIPLES.md` P13
says a system that interrupts constantly trains its people to stop reading the
interruptions, and the one that mattered arrives looking like the forty that did
not. A sweep is the clearest case there is: the same change, checked once,
applied everywhere it was checked to apply.

**SO WHAT MAY BE BATCHED IS EXACTLY WHAT IS IDENTICAL.** Nine repositories whose
constraint rewrites the same way are one approval. A repository that would be
downgraded is not part of that batch however convenient it would be -- it is a
different decision wearing the same shape, and rolling it in is how a batch
approval becomes a way to approve things nobody looked at.

**THE QUEUE IS NOT A FAILURE LIST.** What could not be prepared is work waiting
for a person, each item carrying why. A screen that showed the batch and hid the
queue would report a sweep as nine-for-nine when it was nine of twenty-four.

WHAT THIS CANNOT DO. Approve anything. It arranges what a person is looking at;
the act is theirs, `governance/qm/ci/attested-registry.yaml` says so, and the
signature on it is the only thing that makes the batch mean anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# What a person is being asked. Stated rather than implied by which list an item
# is in, so a row can say it out loud.
APPROVE = "approve"
"""Prepared, identical to its batch, and waiting on a yes."""

DECIDE = "decide"
"""Not identical to anything: its own decision, one at a time."""

BLOCKED = "blocked"
"""Nothing prepared it and nothing can, until something changes."""


@dataclass(frozen=True)
class Item:
    """One repository's share, as a person sees it."""

    project: str
    asking: str
    detail: str = ""
    edit: str | None = None

    @property
    def repo(self) -> str:
        """The short name, which is what fits on a row and what a person says."""
        return self.project.rsplit("/", 1)[-1]


@dataclass
class Batch:
    """Everything identical, approvable in one act."""

    change: str
    """What the batch does, in the words it will be approved under."""

    items: list[Item] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.items)

    def rows(self) -> list[tuple[str, ...]]:
        return [(item.repo, item.detail, APPROVE) for item in self.items]


@dataclass
class Review:
    """What a sweep puts in front of a person: uniform batches, and a queue.

    **BATCHES, PLURAL, AND THE REAL ARCHIVE IS WHY.** The first version had one
    batch holding everything prepared, and against twenty-four real repositories
    it was not uniform: seven declare `>=` and two declare `~=`, so seven get
    `>=0.116.0` and two get `~=0.116.0`. Those are two decisions. Presenting
    them as one keystroke would be a person approving nine things having read
    the seven -- which is the failure this whole module exists to prevent,
    arrived at by the tidier-looking design.

    So the work is grouped by the edit itself. Two approvals here, not one and
    not nine, and each is honestly one thing.
    """

    sweep: str
    change: str = ""
    """What is being swept, in words -- the package, the version, and how the
    package came to be chosen.

    **ON THE REVIEW, BECAUSE THE SUMMARY IS WHAT GETS READ.** This was carried
    only into each batch's name, so a sweep where every share was queued named
    the package nowhere on screen: a reader saw an address and two counts. The
    address identifies the work and does not describe it.
    """

    batches: list[Batch] = field(default_factory=list)
    queue: list[Item] = field(default_factory=list)

    @property
    def batch(self) -> Batch | None:
        """The largest batch, for a caller that wants the main one."""
        return max(self.batches, key=lambda b: b.size) if self.batches else None

    @property
    def approvable(self) -> int:
        return sum(batch.size for batch in self.batches)

    @property
    def total(self) -> int:
        return self.approvable + len(self.queue)

    @property
    def is_complete(self) -> bool:
        """True only when nothing is waiting. A batch alone is not a sweep."""
        return bool(self.approvable) and not self.queue

    def summary(self) -> str:
        """One line, with the queue counted first.

        First because it is the half a reader would otherwise not look for. A
        summary leading with nine approvals reads as done, and the twenty-four
        is the number that matters.
        """
        said = self.change or self.sweep
        if not self.total:
            return f"{said}: nothing to review"
        waiting = len(self.queue)
        count = len(self.batches)
        return (f"{said}: {waiting} waiting on a person, "
                f"{self.approvable} ready in {count} "
                f"batch{'' if count == 1 else 'es'} "
                f"({self.total} in the sweep)")


def review(sweep_address: str, change: str,
           outcomes: Iterable[Any]) -> Review:
    """Arrange one dispatcher run into a batch and a queue.

    Takes the harness's outcomes as they arrive -- anything with `project`,
    `state`, `detail` and `edit`. Not the harness's classes: the two
    repositories do not import each other, and a reviewer that needed the
    harness installed would be a coupling the seam exists to avoid.
    """
    grouped: dict[str, list[Item]] = {}
    queue: list[Item] = []

    for outcome in outcomes:
        project = getattr(outcome, "project", None) or "?"
        state = getattr(outcome, "state", "") or ""
        detail = getattr(outcome, "detail", "") or ""
        edit = getattr(outcome, "edit", None)

        if state == "done" and edit:
            grouped.setdefault(edit, []).append(Item(project, APPROVE, detail, edit))
        elif state == "refused":
            queue.append(Item(project, DECIDE, detail))
        else:
            queue.append(Item(project, BLOCKED, detail))

    batches = []
    for edit, items in grouped.items():
        items.sort(key=lambda item: item.project)
        # The edit is in the batch's name, because that is what is being
        # approved. "fastapi to 0.116.0" describes two of these identically and
        # a person approving the second one deserves to see which it is.
        batches.append(Batch(change=f"{change} ({edit})", items=items))
    # Biggest first: the common case is the one somebody is most likely to be
    # here for, and the smaller batches are the exceptions worth noticing after.
    batches.sort(key=lambda b: (-b.size, b.change))

    queue.sort(key=lambda item: (item.asking, item.project))
    return Review(sweep=sweep_address, change=change, batches=batches,
                  queue=queue)


def batch_is_uniform(batch: Batch) -> bool:
    """Whether every item really is the same decision.

    **THE CHECK THAT MAKES ONE KEYSTROKE HONEST.** A batch approval is one
    person saying yes to one thing; if the items differ, it is one person saying
    yes to several things having read one of them. Every prepared edit must be
    identical -- not similar, identical -- or this is not a batch.

    An empty batch is not uniform. There is nothing to approve, and reporting
    "all of them agree" about nothing is the more misleading answer.
    """
    if not batch.items:
        return False
    return len({item.edit for item in batch.items}) == 1


def approval_note(batch: Batch, by: str) -> str:
    """What is written down when somebody approves, in their name.

    Names the person, the change, and every repository it reached. A record
    saying "batch approved" is one nobody can audit afterwards -- the whole
    point of approving twenty-four things at once is that somebody can later
    see it was twenty-four and which.
    """
    repos = ", ".join(item.repo for item in batch.items)
    return (f"{by} approved {batch.change} across {batch.size} "
            f"repositor{'y' if batch.size == 1 else 'ies'}: {repos}")
