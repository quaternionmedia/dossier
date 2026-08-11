"""Reading disk documents into the store, and the difference between two readings.

## Which side of the line this is on

`dossier/disk.py` runs the corpus's disk tooling and therefore imports
`subprocess`. This module does not, and `tests/test_disk.py` asserts it. The
corpus's rule is that a renderer may not run a command; the same split that put
refreshing in `dossier/corpus.py` and reading in `dossier/governance.py` puts
running in `disk.py` and reading in here.

The naming is asymmetric with the governance pair and worth stating once so
nobody has to work it out: there, the runner is named for what it drives
(`corpus`) and the read model for the domain (`governance`). Here the runner
took the domain name first, so the read model carries the `_store` suffix. The
line between them is identical.

## Append, not replace, and what that costs

`governance.load_documents` replaces what it read, because the only interesting
governance fact is the current one. This loader appends. The question worth
asking of a disk is not how full it is -- the volume says so -- but **what grew
since last time**, and no single reading can answer that.

The cost is a table that grows by one row per load, and it is bounded rather
than ignored: `load_document(keep=N)` prunes the oldest snapshots past N.

## A delta against an unknown is unknown, and this is the whole point

Every corpus document spells an unestablished fact `{"unknown": "<reason>"}`,
and the store keeps that as a value/reason pair. Arithmetic is where the
convention is easiest to lose: subtracting a measured 40GB from a target nobody
could read yields `-40GB`, which is not a missing number but a confident,
specific claim that 40GB was reclaimed. Nobody reading a dashboard would doubt
it.

So `delta_between` refuses four subtractions, and says which:

* either side unknown -- nobody could measure one end
* the target is absent from the earlier snapshot -- it may have existed at that
  size all along and simply not been in the policy yet, so calling it growth
  invents a change nobody observed
* the target is absent from the later one -- it was dropped from the policy,
  which is not the same as being reclaimed
* the two snapshots describe different machines -- refused outright, because a
  laptop's cache growth against a workstation's volume is a trend that never
  happened
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from .models.disk import DiskSnapshot, DiskTarget, DiskVolume

#: Snapshots kept per machine by default. One load per working day is roughly
#: five months of history, which is longer than any question anybody has asked
#: of this data and small enough that nobody notices the rows.
DEFAULT_KEEP = 100

#: What a target's change is called. Words rather than a signed number alone,
#: because the sign is the least readable part of a table and `gone` and
#: `unknown` have no sign at all.
CHANGES = ("grew", "shrank", "same", "new", "gone", "unknown")


def this_machine() -> str:
    """A label for the host, for scoping snapshots.

    The hostname, which is what the operator already calls this box. It is a
    label and never a key: nothing looks a machine up by it except to keep two
    machines' histories from being read as one.
    """
    return socket.gethostname()


def unknown_reason(value: object) -> Optional[str]:
    """The reason, if this value is a corpus document's unknown form."""
    if isinstance(value, dict) and "unknown" in value and len(value) == 1:
        return str(value["unknown"])
    return None


def _moment(text: object) -> Optional[datetime]:
    """An ISO-8601 instant from a document, as a naive UTC datetime.

    Naive because the rest of this store is: `utcnow` in models/schemas.py
    produces one, and a column holding both kinds compares them by raising.
    """
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


@dataclass
class LoadOutcome:
    """What one load did."""

    loaded: bool
    path: Path
    reason: Optional[str] = None
    snapshot_id: Optional[int] = None
    generated_at: Optional[datetime] = None
    machine: Optional[str] = None
    volumes: int = 0
    targets: int = 0
    pruned: int = 0

    @property
    def summary(self) -> str:
        if not self.loaded:
            return f"unavailable - {self.reason}"
        return (
            f"snapshot {self.snapshot_id}: {self.volumes} volume(s), "
            f"{self.targets} target(s), generated {self.generated_at}"
        )


def load_document(
    session: Session,
    document: Optional[Path] = None,
    machine: Optional[str] = None,
    keep: int = DEFAULT_KEEP,
) -> LoadOutcome:
    """Append one disk document to the store as a new snapshot.

    A document that cannot be read leaves the store untouched and says why,
    rather than writing an empty snapshot. An empty snapshot would enter the
    delta as "everything vanished", which is the most alarming way to report
    a file that was simply not there.
    """
    import json

    from .disk import document_path

    path = Path(document) if document is not None else document_path()
    if not path.exists():
        return LoadOutcome(False, path, f"no document at {path} -- measure first")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return LoadOutcome(False, path, f"{path} could not be read: {error}")
    if payload.get("schema") != 1 or "volumes" not in payload:
        return LoadOutcome(False, path, f"{path} is not a disk status document")

    generated_at = _moment(payload.get("generated_at"))
    if generated_at is None:
        # Refused rather than defaulted to now. A snapshot stamped with the
        # load time sorts as the newest reading regardless of what it
        # describes, so one undated document poisons every later delta.
        return LoadOutcome(
            False, path, "the document carries no readable generated_at"
        )

    generator = payload.get("generator") or {}
    reading = payload.get("reading") or {}
    totals = payload.get("totals") or {}
    reclaimable = totals.get("reclaimable_bytes") or {}
    label = machine or this_machine()

    snapshot = DiskSnapshot(
        machine=label,
        generated_at=generated_at,
        staleness_budget_hours=reading.get("staleness_budget_hours"),
        policy_path=generator.get("policy"),
        tool=generator.get("tool"),
        volumes_critical=totals.get("volumes_critical"),
        volumes_warn=totals.get("volumes_warn"),
        volumes_unknown=totals.get("volumes_unknown"),
        targets_measured=totals.get("targets_measured"),
        targets_unknown=totals.get("targets_unknown"),
        reclaimable_refetched=reclaimable.get("refetched"),
        reclaimable_rebuilt=reclaimable.get("rebuilt"),
        reclaimable_destructive=reclaimable.get("destructive"),
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)

    volumes = 0
    for entry in payload.get("volumes") or []:
        reason = unknown_reason(entry.get("usage"))
        session.add(
            DiskVolume(
                snapshot_id=snapshot.id,
                path=str(entry.get("path")),
                total_bytes=entry.get("total_bytes"),
                used_bytes=entry.get("used_bytes"),
                free_bytes=entry.get("free_bytes"),
                free_ratio=entry.get("free_ratio"),
                usage_unknown=reason,
                state=entry.get("state") or ("unknown" if reason else None),
                severity=entry.get("severity") or ("unknown" if reason else None),
                thresholds_fired="\n".join(entry.get("thresholds_fired") or []) or None,
            )
        )
        volumes += 1

    targets = 0
    for entry in payload.get("targets") or []:
        measured = entry.get("measured") or {}
        reason = unknown_reason(measured)
        units = measured.get("units") or []
        largest = units[0] if units else {}
        session.add(
            DiskTarget(
                snapshot_id=snapshot.id,
                name=str(entry.get("name")),
                title=entry.get("title"),
                kind=entry.get("kind"),
                safety=entry.get("safety"),
                owner=entry.get("owner"),
                # The pair. A target behind a dead daemon has no byte count and
                # a reason, and never a zero.
                bytes=None if reason else measured.get("bytes"),
                bytes_unknown=reason,
                files=None if reason else measured.get("files"),
                units_total=None if reason else measured.get("units_total"),
                unreadable=None if reason else measured.get("unreadable"),
                largest_path=largest.get("path"),
                largest_bytes=largest.get("bytes"),
            )
        )
        targets += 1

    session.commit()
    pruned = prune(session, label, keep)
    return LoadOutcome(
        True,
        path,
        snapshot_id=snapshot.id,
        generated_at=generated_at,
        machine=label,
        volumes=volumes,
        targets=targets,
        pruned=pruned,
    )


def prune(session: Session, machine: str, keep: int) -> int:
    """Drop the oldest snapshots for one machine, keeping the newest ``keep``.

    Scoped to the machine, so a store holding two machines keeps ``keep`` of
    each rather than letting a chatty host evict a quiet one's history.
    """
    if keep <= 0:
        return 0
    rows = session.exec(
        select(DiskSnapshot)
        .where(DiskSnapshot.machine == machine)
        .order_by(DiskSnapshot.generated_at.desc())
    ).all()
    doomed = rows[keep:]
    for snapshot in doomed:
        for model in (DiskVolume, DiskTarget):
            for child in session.exec(
                select(model).where(model.snapshot_id == snapshot.id)
            ).all():
                session.delete(child)
        session.delete(snapshot)
    if doomed:
        session.commit()
    return len(doomed)


def snapshots(
    session: Session, machine: Optional[str] = None, limit: int = 20
) -> list[DiskSnapshot]:
    """Newest first. ``machine`` defaults to every machine in the store."""
    statement = select(DiskSnapshot).order_by(DiskSnapshot.generated_at.desc())
    if machine is not None:
        statement = statement.where(DiskSnapshot.machine == machine)
    return list(session.exec(statement.limit(limit)).all())


def volumes_of(session: Session, snapshot_id: int) -> list[DiskVolume]:
    return list(
        session.exec(
            select(DiskVolume).where(DiskVolume.snapshot_id == snapshot_id)
        ).all()
    )


def targets_of(session: Session, snapshot_id: int) -> list[DiskTarget]:
    return list(
        session.exec(
            select(DiskTarget).where(DiskTarget.snapshot_id == snapshot_id)
        ).all()
    )


@dataclass
class TargetChange:
    """One target, across two snapshots.

    ``change`` is bytes and may be ``None``. When it is, ``unknown`` says why,
    and ``status`` is one of `new`, `gone` or `unknown` rather than a number
    the reader would otherwise take at face value.
    """

    name: str
    title: Optional[str]
    safety: Optional[str]
    before: Optional[int] = None
    after: Optional[int] = None
    change: Optional[int] = None
    status: str = "unknown"
    unknown: Optional[str] = None


@dataclass
class VolumeChange:
    """One volume, across two snapshots. ``change`` is the change in FREE bytes.

    Free rather than used, because free is the number that runs out. A negative
    change is the disk filling up, which is the direction worth noticing.
    """

    path: str
    before_free: Optional[int] = None
    after_free: Optional[int] = None
    change: Optional[int] = None
    severity: Optional[str] = None
    unknown: Optional[str] = None


@dataclass
class Delta:
    """What changed between two readings of one machine."""

    machine: Optional[str] = None
    older: Optional[DiskSnapshot] = None
    newer: Optional[DiskSnapshot] = None
    hours: Optional[float] = None
    volumes: list[VolumeChange] = field(default_factory=list)
    targets: list[TargetChange] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.reason is None

    @property
    def grew(self) -> list[TargetChange]:
        """Targets that gained bytes, largest gain first -- the answer to
        "what is doing this to me"."""
        return sorted(
            (t for t in self.targets if t.status == "grew"),
            key=lambda t: -(t.change or 0),
        )

    @property
    def unreadable(self) -> list[TargetChange]:
        return [t for t in self.targets if t.change is None]


def _target_change(name: str, older: Optional[DiskTarget], newer: Optional[DiskTarget]) -> TargetChange:
    title = (newer or older).title if (newer or older) else None
    safety = (newer or older).safety if (newer or older) else None

    if older is None:
        return TargetChange(
            name, title, safety,
            after=newer.bytes if newer else None,
            status="new",
            unknown=(
                "not in the earlier snapshot. It may have been this size all "
                "along and simply not in the policy yet, so there is no change "
                "to report"
            ),
        )
    if newer is None:
        return TargetChange(
            name, title, safety,
            before=older.bytes,
            status="gone",
            unknown=(
                "not in the later snapshot. Being dropped from the policy is "
                "not the same as being reclaimed"
            ),
        )
    if older.bytes is None or newer.bytes is None:
        return TargetChange(
            name, title, safety,
            before=older.bytes, after=newer.bytes,
            status="unknown",
            unknown=(
                older.bytes_unknown or newer.bytes_unknown
                or "one of the two readings has no byte count"
            ),
        )

    change = newer.bytes - older.bytes
    return TargetChange(
        name, title, safety,
        before=older.bytes, after=newer.bytes, change=change,
        status="grew" if change > 0 else "shrank" if change < 0 else "same",
    )


def delta_between(
    session: Session, older: DiskSnapshot, newer: DiskSnapshot
) -> Delta:
    """What changed between two snapshots of the same machine.

    Refuses two machines outright. Comparing them would produce a trend that
    never happened on either, and the numbers would look entirely plausible.
    """
    if older.machine != newer.machine:
        return Delta(
            reason=(
                f"these snapshots describe different machines "
                f"({older.machine} and {newer.machine}); a difference between "
                "them is not a change that happened anywhere"
            )
        )
    if older.generated_at > newer.generated_at:
        older, newer = newer, older

    hours = (newer.generated_at - older.generated_at).total_seconds() / 3600

    before_targets = {t.name: t for t in targets_of(session, older.id)}
    after_targets = {t.name: t for t in targets_of(session, newer.id)}
    targets = [
        _target_change(name, before_targets.get(name), after_targets.get(name))
        for name in sorted(set(before_targets) | set(after_targets))
    ]

    before_volumes = {v.path: v for v in volumes_of(session, older.id)}
    after_volumes = {v.path: v for v in volumes_of(session, newer.id)}
    volumes = []
    for path in sorted(set(before_volumes) | set(after_volumes)):
        was, now = before_volumes.get(path), after_volumes.get(path)
        if was is None or now is None or was.free_bytes is None or now.free_bytes is None:
            volumes.append(
                VolumeChange(
                    path,
                    before_free=was.free_bytes if was else None,
                    after_free=now.free_bytes if now else None,
                    severity=now.severity if now else None,
                    unknown=(
                        "absent from one of the two snapshots"
                        if was is None or now is None
                        else (was.usage_unknown or now.usage_unknown
                              or "one reading has no free-space figure")
                    ),
                )
            )
            continue
        volumes.append(
            VolumeChange(
                path,
                before_free=was.free_bytes,
                after_free=now.free_bytes,
                change=now.free_bytes - was.free_bytes,
                severity=now.severity,
            )
        )

    return Delta(
        machine=newer.machine,
        older=older,
        newer=newer,
        hours=round(hours, 1),
        volumes=volumes,
        targets=targets,
    )


def latest_delta(session: Session, machine: Optional[str] = None) -> Delta:
    """The change between the two most recent snapshots of one machine.

    One snapshot is not an error and not an empty delta: it is a machine that
    has been measured once, and the honest report is that there is nothing to
    compare it with yet.
    """
    wanted = machine or this_machine()
    rows = snapshots(session, machine=wanted, limit=2)
    if len(rows) < 2:
        # The machine is named in both reasons. A store can hold more than one,
        # and "no snapshots" without saying which host was looked for sends the
        # reader hunting for a bug in the loader rather than passing --machine.
        return Delta(
            machine=wanted,
            newer=rows[0] if rows else None,
            reason=(
                f"only one snapshot for {wanted}, so there is nothing to "
                "compare it with. Load a second reading later"
                if rows
                else f"no snapshots for {wanted} yet"
            ),
        )
    return delta_between(session, rows[1], rows[0])
