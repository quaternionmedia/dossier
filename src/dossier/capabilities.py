"""What each named thing this estate can do has reached, as one window sees it.

    dossier capabilities              every capability and its rungs
    dossier capabilities --gap        only the ones whose claim outruns its evidence

**THE VOCABULARY IS THE CORPUS'S AND THIS ADDS NONE OF ITS OWN.** The four rungs
-- design, deployment, execution, monitoring -- and what each declines to claim
are `governance/qm/records/DRAFT-a-capability-has-four-phases.md`. The claims are
`ci/capability-registry.yaml`. `codecarto` is the other window onto the same
file, and a rung that meant something different here would give two readings of
one estate with nothing able to say which is right.

**IT RUNS NO COMMANDS**, which is the constraint that shapes everything below.
`dossier.corpus` states the rule: a renderer that can shell out becomes a second
place a governance rule is defined. So this cannot establish that a capability's
`deployment` command resolves -- it reads the pointer and reports that a pointer
exists. Evidence is each project's own gate to produce and publish; this reads
what was published.

**WHICH MAKES THE GAP THE THING WORTH RENDERING.** A claim of `execution` beside
a `deployment` pointer nobody has checked is the ordinary state of this list, and
it is the state the record was written about. `gap` names it rather than leaving
a reader to compare two columns.

WHAT IT CANNOT SEE. Whether any pointer is true. Whether a capability that is
absent from the registry exists -- an unregistered capability is invisible here
and reads exactly like a well-governed estate. And anything at a corpus pin
older than the registry: that reports `unknown` rather than an empty list,
because a submodule pinned before the file existed is not an estate with no
capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The corpus's own default location, the same one `dossier.governance` uses.
DEFAULT_CORPUS_DIR = Path("governance/qm")
REGISTRY = Path("ci") / "capability-registry.yaml"

RUNGS = ("design", "deployment", "execution", "monitoring")
"""Ordered, and read from the corpus's record rather than invented here. If
these ever disagree with `ci/capabilities.py`'s own tuple, that file is right
and this is the copy to repair."""

UNKNOWN = "unknown"


@dataclass(frozen=True)
class Capability:
    """One declaration, as the registry stated it."""

    id: str
    title: str
    repo: str
    phase: str
    stated_by: str = ""
    stated_on: str = ""
    what: str = ""
    cannot_see: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def known_phase(self) -> bool:
        return self.phase in RUNGS

    @property
    def reached(self) -> tuple[str, ...]:
        """The rungs at or below the claim. Empty when the phase is not a rung."""
        if not self.known_phase:
            return ()
        return RUNGS[: RUNGS.index(self.phase) + 1]

    def pointer(self, rung: str) -> str:
        """Where to look for one rung's evidence, or `unknown`.

        A missing key and an explicit `null` read the same, and neither says the
        rung was checked and found wanting.
        """
        value = (self.evidence or {}).get(rung)
        return str(value) if value else UNKNOWN

    @property
    def unevidenced(self) -> tuple[str, ...]:
        """Rungs at or below the claim with no pointer at all.

        **The corpus's own check refuses these**, so a registry that passed its
        gate has none. Computed anyway: this window may be pointed at a corpus
        pin from before that check existed, and reporting a gap it cannot
        explain is better than rendering a ladder with a hole in it.
        """
        return tuple(r for r in self.reached if self.pointer(r) == UNKNOWN)

    @property
    def unclaimed(self) -> tuple[str, ...]:
        """Rungs above the claim. The ordinary state, and not a fault."""
        return tuple(r for r in RUNGS if r not in self.reached)


@dataclass(frozen=True)
class Reading:
    """Every capability the corpus declares, or why none could be read."""

    capabilities: tuple[Capability, ...] = ()
    reason: str = ""
    """Why the registry could not be read. Empty when it was."""

    source: str = ""

    @property
    def readable(self) -> bool:
        return not self.reason

    def by_phase(self) -> dict[str, list[Capability]]:
        """The list grouped by claim, in rung order.

        An unreadable phase is grouped under `unknown` rather than dropped: a
        declaration nobody can place is a fact about the registry, and dropping
        it would make the estate look smaller and tidier than it is.
        """
        found: dict[str, list[Capability]] = {rung: [] for rung in RUNGS}
        found[UNKNOWN] = []
        for capability in self.capabilities:
            found[capability.phase if capability.known_phase else UNKNOWN].append(
                capability)
        return found


def read(corpus_dir: Path | str | None = None) -> Reading:
    """Every capability the corpus declares. **Runs nothing.**

    An absent registry is a reason rather than an empty list. A corpus pinned
    before the registry existed is the ordinary case while this is new, and it
    must not render like an estate that declares no capabilities.
    """
    import yaml

    root = Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS_DIR
    path = root / REGISTRY
    if not path.is_file():
        return Reading(reason=(
            f"no capability registry at {path.as_posix()}. The corpus pin may "
            f"predate it; `git submodule update --remote` moves the pin."),
            source=str(path))

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        return Reading(reason=f"{path.as_posix()} did not parse: {error}",
                       source=str(path))

    declared = data.get("capabilities")
    if not isinstance(declared, list):
        return Reading(reason=f"{path.as_posix()}: `capabilities` is not a list",
                       source=str(path))

    found = []
    for entry in declared:
        if not isinstance(entry, dict) or not entry.get("id"):
            # A row that cannot be named cannot be matched to itself next time.
            # The same rule `dossier.harness.asks_of` applies to queue rows.
            continue
        found.append(Capability(
            id=str(entry["id"]),
            title=str(entry.get("title", "")),
            repo=str(entry.get("repo", "")),
            phase=str(entry.get("phase", UNKNOWN)),
            stated_by=str(entry.get("stated_by", "")),
            stated_on=str(entry.get("stated_on", "")),
            what=str(entry.get("what", "")).strip(),
            cannot_see=str(entry.get("cannot_see", "")).strip(),
            evidence=entry.get("evidence") or {},
        ))
    return Reading(capabilities=tuple(found), source=str(path))


def render(reading: Reading, only_gaps: bool = False) -> str:
    """The ladder, for a person deciding where attention is owed."""
    if not reading.readable:
        return f"  {reading.reason}"

    if not reading.capabilities:
        return ("  The registry is readable and declares nothing. That is an "
                "empty registry, not an estate with no capabilities.")

    lines: list[str] = []
    for rung in (*RUNGS, UNKNOWN):
        group = reading.by_phase()[rung]
        if only_gaps:
            group = [c for c in group if c.unevidenced or not c.known_phase]
        if not group:
            continue
        lines.append(f"  {rung.upper()}")
        for capability in group:
            lines.append(f"    {capability.id:<28} {capability.title}")
            lines.append(f"      {capability.repo}   stated by "
                         f"{capability.stated_by or 'nobody'} "
                         f"{capability.stated_on}")
            for name in RUNGS:
                mark = "claimed" if name in capability.reached else "--"
                lines.append(f"        {name:<11} {mark:<8} "
                             f"{capability.pointer(name)}")
            if capability.unevidenced:
                lines.append(f"      GAP: claims {capability.phase} and names "
                             f"nothing for "
                             f"{', '.join(capability.unevidenced)}")
            lines.append("")

    if only_gaps and not lines:
        return ("  Every claim names a pointer for every rung at or below it. "
                "That is the registry being readable,\n  and it is not evidence "
                "that any pointer is true.")

    lines.append("A pointer is where to look, never what was found. This window "
                 "runs no command and")
    lines.append("resolves no address, so a capability naming a command that "
                 "does not exist reads clean here.")
    return "\n".join(lines)
