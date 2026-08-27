"""Which views can answer right now, and what the others are waiting for.

**AN EMPTY VIEW AND AN UNAVAILABLE ONE ARE DIFFERENT FACTS.** `dossier.views`
used to close by admitting they looked identical, and several of this application's views
lived in that gap: Details and Documentation need a repository chosen, Topology
and Harness need a separate process running, Outstanding needs a reading that
has to have been taken first. Each rendered a blank panel and said nothing.

This answers the registry's `needs` against the state of the machine, so a view
that cannot answer says why and **says what to do about it** -- the remedy is
part of the need rather than something a reader has to work out.

**THE ANSWER IS A MEASUREMENT, NOT A GUESS.** Every check here reads something:
the database for a selection, the harness's own `/health` for whether it is
running, the disk for a clone, the corpus for its generated documents. A need
this cannot check reports `unknown`, which is neither met nor unmet -- the same
distinction the harness payload draws, and for the same reason: a thing nobody
could measure must not render like a thing measured and found wanting.

WHAT THIS CANNOT SEE. Whether a view whose needs are met has anything worth
reading in it. A quiet estate and a satisfied precondition look alike, and they
should -- `Outstanding` showing zero rows is the answer, not a failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dossier import views

MET = "met"
UNMET = "unmet"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Answer:
    """One need, and whether this machine satisfies it."""

    need: views.Need
    state: str
    detail: str = ""

    @property
    def blocks(self) -> bool:
        """**`unknown` does not block.** A need nobody could check is not a
        need found wanting, and refusing to show a view on the strength of a
        measurement that failed would be the worse error of the two."""
        return self.state == UNMET


@dataclass(frozen=True)
class Readiness:
    """What one view is waiting for, if anything."""

    view: views.View
    answers: tuple[Answer, ...] = ()

    @property
    def ready(self) -> bool:
        return not any(answer.blocks for answer in self.answers)

    @property
    def blocking(self) -> tuple[Answer, ...]:
        return tuple(answer for answer in self.answers if answer.blocks)

    def route(self) -> str:
        """Where to go first, or empty when nothing blocks.

        The first blocking need's remedy. First rather than all of them: a
        reader who is told three things to do does none, and the needs are
        ordered so that the one to do first is written first.
        """
        blocking = self.blocking
        return blocking[0].need.satisfied_by if blocking else ""



def check(need: views.Need, *, selection: object | None = None,
          corpus: Path | str | None = None,
          clone_of: str | None = None,
          harness_base: str | None = None) -> Answer:
    """Whether this machine satisfies one need, right now.

    Each branch reads something. Where the reading itself fails -- a harness
    that cannot be reached is a *measurement*, a corpus path that cannot be
    stat'd is not -- the answer is `unknown` rather than `unmet`.
    """
    if need.key == views.PROJECT:
        if selection is None:
            return Answer(need, UNMET, "no repository is selected")
        return Answer(need, MET)

    if need.key == views.HARNESS:
        from dossier.threads import base_url
        root = (harness_base or base_url()).rstrip("/")
        try:
            import urllib.request

            with urllib.request.urlopen(f"{root}/health", timeout=3) as reply:
                reply.read()
            return Answer(need, MET, f"answering at {root}")
        except Exception:                              # noqa: BLE001
            # Not running is the ordinary case and is a real answer: the
            # harness is a separate process and very often has not been
            # started.
            return Answer(need, UNMET, f"nothing is answering at {root}")

    if need.key == views.CLONE:
        if not clone_of:
            # **NOT `unknown`, AND THE DIFFERENCE MATTERS.** `unknown` does not
            # block, so a caller that named a selection without naming which
            # repository it was got `Branches` reported ready when the clone
            # had never been looked for. A need whose subject is missing is a
            # need nobody has *asked*, and the honest answer is that it is
            # unmet until somebody does.
            if selection is not None:
                return Answer(need, UNMET,
                              "a repository is selected and its name was not "
                              "passed here, so no clone was looked for")
            return Answer(need, UNMET,
                          "no repository selected, so no clone to look for")
        from dossier.branches import find_clone
        found = find_clone(clone_of)
        if found is None:
            return Answer(need, UNMET, f"no clone of {clone_of} on this machine")
        return Answer(need, MET, str(found))

    if need.key == views.CORPUS:
        root = Path(corpus) if corpus else Path("governance/qm")
        if not root.is_dir():
            return Answer(need, UNMET,
                          f"no corpus at {root.as_posix()}")
        if not (root / "governance-status.yaml").is_file():
            return Answer(need, UNMET,
                          "the corpus is here and its generated documents are "
                          "not; the pin may predate them")
        return Answer(need, MET)

    if need.key == views.ATTENTION:
        # The overview's reading is taken on demand and is not a stored
        # artifact, so whether it has run cannot be read from anywhere. Saying
        # `unknown` is the honest answer, and it deliberately does not block.
        return Answer(need, UNKNOWN,
                      "whether the overview's reading has been taken is not "
                      "recorded anywhere this can read")

    return Answer(need, UNKNOWN, f"no check exists for {need.key!r}")


def readiness(view: views.View, **state) -> Readiness:
    """One view, and what it is waiting for."""
    return Readiness(view=view,
                     answers=tuple(check(need, **state) for need in view.needs))


def survey(**state) -> tuple[Readiness, ...]:
    """Every view, in registry order."""
    return tuple(readiness(view, **state) for view in views.VIEWS)


def render(found: tuple[Readiness, ...]) -> str:
    """What a person reads to know where they can go.

    **GROUPED BY WHAT IS MISSING, NOT BY VIEW.** Nine views wait on a
    repository being selected, and listing them one after another prints one
    fact nine times in nearly the same words. A reader meeting that wall does
    not learn there are nine problems; they learn to stop reading. One
    missing thing, one entry, and the views it holds up named after it.
    """
    ready = [r for r in found if r.ready]
    waiting = [r for r in found if not r.ready]

    lines = [f"  {len(ready)} of {len(found)} views can answer now.", ""]

    # **GROUPED ON WHAT IS MISSING, NOT ON HOW IT IS WORDED.** The first
    # version keyed on the `because` sentence too, and `views._of_one_repository`
    # writes a different sentence per view on purpose -- "these facts belong to
    # one repository", "issues belong to one repository". Nine distinct
    # sentences meant nine groups of one, which is the wall this was written to
    # remove. The per-view sentence still earns its place inside that view; it
    # is the wrong key for a survey.
    grouped: dict[tuple[str, str], list[str]] = {}
    for r in waiting:
        first = r.blocking[0].need
        grouped.setdefault((first.key, first.satisfied_by), []).append(
            r.view.title)

    for (key, by), titles in grouped.items():
        lines.append(f"  {len(titles)} waiting on {key}: {', '.join(titles)}")
        lines.append(f"      -> {by}")
        lines.append("")

    if not waiting:
        lines.append("  Nothing is waiting on a precondition.")
        lines.append("")
    lines.append("  A view that is ready may still be empty, and that is a "
                 "different fact:")
    lines.append("  an estate with nothing outstanding reads zero rows on "
                 "purpose.")
    return "\n".join(lines)
