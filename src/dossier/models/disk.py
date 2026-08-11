"""Storage for the corpus's generated disk documents, and what changed between them.

These tables hold what `ci/disk_status.py` reports. They follow
`models/governance.py` in every respect but one, and the exception is the whole
reason they exist.

**These tables are append-only, and the governance tables are not.** A
governance load replaces what it read, because the only interesting governance
fact is the current one. Disk is the opposite: the question that matters here
is not "how full is it" -- the volume already answers that -- but **"what grew
since last time"**, and nothing can answer that from a single reading. So each
load writes a new `DiskSnapshot` and its rows, and the previous ones stay.

That is a decision with a cost, and the cost is bounded rather than ignored:
`dossier disk load --keep N` prunes the oldest snapshots, defaulting to a
number that holds months of ordinary use.

**Every snapshot is labelled with the machine it describes.** The corpus
generator refuses to write its document inside a repository because every fact
in it is one machine at one moment. A store is a weaker boundary than a
repository -- it is a file somebody can copy -- so the scope travels *in the
row* rather than being implied by where the row lives. A store that ends up
holding two machines' snapshots stays readable; one that silently merged them
would report a laptop's cache growth against a workstation's volume.

**Every field the document may report as unknown is stored as a pair:** a
nullable value column and a `*_unknown` reason column, exactly as
`models/governance.py` does it, and for the same reason. The convention in
every corpus document is `{"unknown": "<reason>"}`, a value meaning the fact
could not be established, which says why.

| value | unknown | means |
|---|---|---|
| set | `None` | the measured fact |
| `None` | set | nobody could measure it, for the stated reason |
| `None` | `None` | the document stated a real null |

That pair is load-bearing twice over here. Once as it is in governance -- a
cache behind a permission error must not render like a cache with nothing in
it. And once more in arithmetic: **a delta against an unknown is unknown, not
zero.** Subtracting a measured 40GB from a target nobody could read produces
`-40GB`, which is a confident, specific, wrong claim that something was
reclaimed. `disk.delta_between` refuses that subtraction and says why instead.

**This is a read model.** Nothing here writes back to the document, and
nothing computes a disk fact: every figure arrives from the corpus generator.
The one thing computed here is the difference between two rows this store
already holds, which is arithmetic on stored facts rather than a second
measurement.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from .schemas import utcnow


class DiskSnapshot(SQLModel, table=True):
    """One reading of one machine, at one moment.

    The unit of append. Everything else in this module hangs off a snapshot by
    id, so a prune is a delete of the parent and its children rather than a
    query that has to know which rows were current.
    """

    __tablename__ = "disk_snapshot"

    id: Optional[int] = Field(default=None, primary_key=True)

    # The machine this describes. Not decoration: see the module docstring.
    # A store is a file somebody can copy, so the scope is in the row.
    machine: str = Field(index=True)

    # The document's own timestamp, never the load's. A snapshot loaded today
    # from a document written last week describes last week, and a view that
    # showed the load time would date it wrongly by six days.
    generated_at: datetime = Field(index=True)
    loaded_at: datetime = Field(default_factory=utcnow)

    # Carried verbatim so a reader can date a figure without the corpus
    # checkout that produced it. The budget is the document's own, not
    # dossier's: encoding a number here would be a second definition of it.
    staleness_budget_hours: Optional[float] = None
    policy_path: Optional[str] = None
    tool: Optional[str] = None

    # Totals, kept so a list of snapshots renders without loading every child.
    # Derived by the generator, not recomputed here.
    volumes_critical: Optional[int] = None
    volumes_warn: Optional[int] = None
    volumes_unknown: Optional[int] = None
    targets_measured: Optional[int] = None
    targets_unknown: Optional[int] = None
    reclaimable_refetched: Optional[int] = None
    reclaimable_rebuilt: Optional[int] = None
    reclaimable_destructive: Optional[int] = None


class DiskReclaim(SQLModel, table=True):
    """One reclaim run, recorded as the pair of readings it sits between.

    A reclaim is not a separate kind of event from a measurement -- it is a
    measurement, an action, and another measurement. Storing it as the two
    snapshot ids means the change it caused is computed by exactly the same
    arithmetic as any other change, carries the same refusals, and composes
    with observed deltas rather than needing a second vocabulary.

    **`claimed_bytes` and `freed_bytes` are different facts, and both are
    kept.** The reclaimer reports what it removed; the volume reports what came
    back. They diverge for ordinary reasons -- something else was writing at
    the time, or the space was freed inside a container disk that does not
    shrink -- and the policy already says so in prose about Docker's VHDX.
    Recording only the first would let the tool claim 23GB it did not give
    back; recording only the second would blame it for a concurrent download.
    The gap between them is the interesting number, and it is only visible
    because both are stored.
    """

    __tablename__ = "disk_reclaim"

    id: Optional[int] = Field(default=None, primary_key=True)
    machine: str = Field(index=True)

    started_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: Optional[datetime] = None

    # What was asked for. Kept verbatim so a row explains itself without the
    # shell history that produced it.
    allow: str = "refetched"
    targets: Optional[str] = None  # comma-joined; null means every permitted
    applied: bool = False

    # The pair. `after_snapshot_id` is null for a dry run and for a run that
    # died before its second reading -- which is not the same as a run that
    # freed nothing, so the delta reports it as unavailable rather than zero.
    before_snapshot_id: Optional[int] = Field(default=None, foreign_key="disk_snapshot.id")
    after_snapshot_id: Optional[int] = Field(default=None, foreign_key="disk_snapshot.id")

    claimed_bytes: Optional[int] = None
    claimed_paths: Optional[int] = None
    freed_bytes: Optional[int] = None
    freed_unknown: Optional[str] = None

    # `outcome` is one of: planned, applied, failed. `planned` is a dry run and
    # is stored deliberately -- a plan that was never carried out is a fact
    # about what somebody considered, and it is the row a later reader needs
    # when the disk filled again and nobody remembers whether they ran it.
    outcome: str = "planned"
    exit_status: Optional[int] = None
    reason: Optional[str] = None
    output: Optional[str] = None


class DiskVolume(SQLModel, table=True):
    """One filesystem, in one snapshot."""

    __tablename__ = "disk_volume"

    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_id: int = Field(index=True, foreign_key="disk_snapshot.id")

    path: str = Field(index=True)

    total_bytes: Optional[int] = None
    used_bytes: Optional[int] = None
    free_bytes: Optional[int] = None
    free_ratio: Optional[float] = None
    usage_unknown: Optional[str] = None

    # `severity` is the generator's word -- ok, warn, critical, unknown -- and
    # this column does not re-spell it. A renderer that renames a state has
    # defined a second vocabulary for it, and the two drift.
    state: Optional[str] = None
    severity: Optional[str] = None
    thresholds_fired: Optional[str] = None  # newline-joined, verbatim


class DiskTarget(SQLModel, table=True):
    """One reclaimable target, in one snapshot.

    `bytes` and `bytes_unknown` are the pair the whole module turns on. A
    target the generator could not measure has `bytes` null and a reason set,
    and every consumer -- the view, the API, the delta -- has to carry that
    distinction rather than defaulting it to zero.
    """

    __tablename__ = "disk_target"

    id: Optional[int] = Field(default=None, primary_key=True)
    snapshot_id: int = Field(index=True, foreign_key="disk_snapshot.id")

    name: str = Field(index=True)
    title: Optional[str] = None
    kind: Optional[str] = None

    # What it costs to get the bytes back. The corpus's word, verbatim, and
    # the field a reader sorts by before deciding anything.
    safety: Optional[str] = None
    owner: Optional[str] = None

    bytes: Optional[int] = None
    bytes_unknown: Optional[str] = None

    files: Optional[int] = None
    units_total: Optional[int] = None

    # How many paths the generator could not read. A sum over a directory with
    # locked files in it is a floor, not a measurement, and a view that hides
    # this reports a minimum as a total.
    unreadable: Optional[int] = None

    largest_path: Optional[str] = None
    largest_bytes: Optional[int] = None
