"""Everything the system needs a person for, in one list.

**FIVE PLACES ASKED FOR A PERSON AND NONE OF THEM KNEW ABOUT THE OTHERS.** A
harness question in the Waiting tab, a sweep batch waiting on approval, a sweep
share nothing could prepare, an ingest with no path yet, and a menu command that
needs a decision. Each was reasonable alone. Together they meant a person had to
visit five screens to find out whether anything wanted them, and `PRINCIPLES.md`
P13 is exactly about what that costs: a system that interrupts from everywhere
trains people to stop reading the interruptions.

**THE ABSTRACTION IS THE ASK, NOT THE ASKER.** An `Interaction` says what is
wanted from a person and what answering it would do. Where it came from is a
field. That inversion is the whole point -- a new source adds rows to one list
rather than a sixth place to look.

**FOUR KINDS, AND THEY ARE DIFFERENT ACTIONS RATHER THAN DIFFERENT WORDS.**
`approve` is yes or no to something already prepared. `answer` is a question with
options. `provide` needs a value nobody can guess. `decide` is a judgement with
no prepared answer at all. A screen that rendered them alike would make the
one-keystroke case look like the one that needs thought.

**RAD IS A PRESENTATION AND NOT THE MECHANISM.** Every interaction here can be
reached without a menu -- a button, a command, a key. rad routes to them and is
optional by construction: nothing in this module imports it, and
`tests/core/test_interaction.py` proves the layer works with rad absent. That
optionality is real and is not the same as rad being unimportant; the trio uses
it, documents it, and holds it as a contract. Those are different claims and the
code has to support the first while the organisation makes the second.

WHAT THIS CANNOT DO. Answer anything. It gathers and orders; the acts are a
person's, and `governance/qm/ci/attested-registry.yaml` names the ones that stay
a person's whatever the interface makes convenient.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

APPROVE = "approve"
"""Yes or no to something already prepared. One keystroke, honestly."""

ANSWER = "answer"
"""A question with options somebody chose in advance."""

PROVIDE = "provide"
"""A value nothing can guess -- a path, a version, a name."""

DECIDE = "decide"
"""A judgement with no prepared answer. The kind that needs thought, and the
kind a screen must never dress up as the others."""

KINDS = (APPROVE, ANSWER, PROVIDE, DECIDE)

# Where an ask came from. A field rather than a class, so a new source is a
# string and some rows rather than a sixth place to look.
FROM_HARNESS = "harness"
FROM_SWEEP = "sweep"
FROM_ARCHIVE = "archive"


def _no_menu(action: str) -> str:
    """The route when nobody offered one.

    Empty rather than a guess: a menu is optional here, and an interaction that
    invented `m 6 4` on a host with no ring would be telling somebody to press
    keys that do nothing.
    """
    return ""


@dataclass(frozen=True)
class Interaction:
    """One thing wanted from a person."""

    id: str
    kind: str
    prompt: str
    source: str

    options: tuple[str, ...] = ()
    """What may be answered, where the answer is from a set. Empty for
    `provide` and `decide`, which is how a renderer knows not to draw buttons
    for a question with no prepared answers."""

    covers: int = 1
    """How many things one answer settles. A batch of seven is one interaction
    covering seven, not seven interactions -- that distinction is the whole
    reason batching is worth doing."""

    route: str = ""
    """Where to go to act on it, in the words a person would use. Never a
    function: this layer is read by a terminal, and will be read by a page."""

    address: str = ""
    detail: str = ""

    @property
    def is_batched(self) -> bool:
        return self.covers > 1

    @property
    def weight(self) -> int:
        """How much is riding on this one answer. Used for ordering, not for
        urgency -- nothing here knows what is urgent."""
        return self.covers


@dataclass
class Queue:
    """Everything waiting on a person, from every source."""

    items: list[Interaction] = field(default_factory=list)
    unreachable: list[str] = field(default_factory=list)
    """Sources that could not be asked. **Not zero interactions** -- a source
    that did not answer is not a source with nothing to say, and a queue that
    silently omitted it would report a quiet day."""

    def of_kind(self, kind: str) -> list[Interaction]:
        return [i for i in self.items if i.kind == kind]

    def by_source(self) -> dict[str, list[Interaction]]:
        found: dict[str, list[Interaction]] = {}
        for item in self.items:
            found.setdefault(item.source, []).append(item)
        return found

    @property
    def covered(self) -> int:
        """How many things are settled if a person answers everything here."""
        return sum(i.covers for i in self.items)

    def ordered(self) -> list[Interaction]:
        """Most-covering first, then by kind, then stably by id.

        BATCHES FIRST BECAUSE THEY ARE THE CHEAPEST ANSWERS, not because they
        are the most important -- one keystroke settling seven repositories is
        a better use of the first minute than a judgement settling one. Nothing
        here claims to know what is urgent.
        """
        order = {kind: n for n, kind in enumerate(KINDS)}
        return sorted(self.items,
                      key=lambda i: (-i.covers, order.get(i.kind, 9), i.id))

    def summary(self) -> str:
        if self.unreachable and not self.items:
            return (f"nothing to answer from the sources that replied; "
                    f"{len(self.unreachable)} could not be asked "
                    f"({', '.join(self.unreachable)})")
        if not self.items:
            return "nothing is waiting on a person"
        parts = [f"{len(self.items)} waiting", f"{self.covered} settled if all "
                 f"are answered"]
        if self.unreachable:
            parts.append(f"{len(self.unreachable)} source(s) could not be asked")
        return ", ".join(parts)


def from_harness_asks(rows: Iterable[Any]) -> list[Interaction]:
    """Outstanding questions a harness put to a person.

    A row with options is an `answer`; one without is a `decide`. The harness
    knows which it asked, and turning a free question into a multiple choice
    would put words in somebody's mouth.
    """
    found = []
    for row in rows:
        status = str(_get(row, "status") or "").lower()
        if status and status not in ("pending", "outstanding", "open"):
            continue
        options = tuple(_get(row, "options") or ())
        found.append(Interaction(
            id=str(_get(row, "request_id") or _get(row, "id") or "?"),
            kind=ANSWER if options else DECIDE,
            prompt=str(_get(row, "prompt") or "a harness asked something"),
            source=FROM_HARNESS,
            options=options,
            route="Waiting tab",
            address=str(_get(row, "address") or ""),
        ))
    return found


def from_sweep_review(review: Any,
                      route_for: Callable[[str], str] = _no_menu
                      ) -> list[Interaction]:
    """A sweep's batches and its queue.

    A batch is **one** interaction covering N repositories, which is the whole
    reason the batching exists. Emitting one per repository here would undo it
    two layers above where it was decided.
    """
    # **ASKED FOR, NOT IMPORTED.** These routes were literals. They happened
    # to be right -- `Do` was never reordered -- and would have been wrong the
    # day it was, with nothing anywhere to say so. Reading them from the menu
    # directly would make an optional mechanism a required one, which is the
    # seam this layer exists on, so the host hands the answer in.
    to_the_sweep = route_for("sweep.review")

    found = []
    for index, batch in enumerate(getattr(review, "batches", []) or []):
        found.append(Interaction(
            id=f"sweep-batch-{index}",
            kind=APPROVE,
            prompt=f"approve {batch.change}",
            source=FROM_SWEEP,
            options=("approve", "hold"),
            covers=batch.size,
            route=to_the_sweep,
            detail=", ".join(item.repo for item in batch.items),
        ))
    for item in getattr(review, "queue", []) or []:
        found.append(Interaction(
            id=f"sweep-{item.repo}",
            kind=DECIDE,
            prompt=f"{item.repo}: {item.detail}",
            source=FROM_SWEEP,
            route=to_the_sweep,
        ))
    return found


def needs_an_export(archive: Any,
                    route_for: Callable[[str], str] = _no_menu
                    ) -> list[Interaction]:
    """An archive nobody has put anything into yet.

    `provide`, because no list of options contains a path on somebody's disk.
    """

    if getattr(archive, "reachable", False) and getattr(archive, "indexed", False):
        return []
    return [Interaction(
        id="archive-empty",
        kind=PROVIDE,
        prompt="the thread archive has nothing indexed; point at an export",
        source=FROM_ARCHIVE,
        route=route_for("reach.ingest"),
    )]


def gather(sources: dict[str, Callable[[], list[Interaction]]]) -> Queue:
    """Every source, each surviving the others' failures.

    A source that raises becomes a name in `unreachable` rather than an empty
    contribution. The distinction is the point: nothing to say and nobody
    answering look identical in a total and are opposite facts.
    """
    queue = Queue()
    for name, read in sources.items():
        try:
            queue.items.extend(read())
        except Exception:                          # noqa: BLE001
            queue.unreachable.append(name)
    return queue


def _get(row: Any, name: str) -> Any:
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)
