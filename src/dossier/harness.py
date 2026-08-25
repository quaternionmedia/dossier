"""Read what a harness reports about itself.

    qmcp dashboard --json > harness.json
    dossier harness ingest harness.json --write

WHAT CROSSES IS A SCHEMA, NOT AN IMPORT. The payload is what
`qmcp dashboard --json` prints: a schema version, the harness's own totals,
counts by tool and status, and the most recent invocations, each addressed as
`owner/repo/invocation/<id>`. Neither repository imports the other; the address
is the join, exactly as it is for deltas.

WHAT IS STORED AND WHY IT IS TWO THINGS. The totals are the harness's own
counts over its whole history, and the payload carries only an excerpt of the
rows -- so recomputing the totals from the rows would report the size of the
excerpt and call it the history. The totals are stored verbatim as a snapshot,
the rows are stored by address, and the snapshot's age is what tells a reader
how current either is.

NOTHING IS WRITTEN WITHOUT `--write`, and nothing is ever deleted. An
invocation absent from a payload is one this payload did not mention, not one
that was removed -- the payload is an excerpt by construction.

THE QUEUE CROSSES AS ROWS. `waiting` carries one entry per question the
harness put to a person, addressed as `owner/repo/ask/<id>`, with its prompt,
its options and its answer if it has one. Before that only the counts crossed,
so this side could say one thing was outstanding and never which -- and a count
is not something anybody can answer. A payload without `waiting` is a schema-2
payload and is read as before; the rows are absent, not empty.

A TOTAL THE HARNESS COULD NOT TAKE IS REFUSED, NOT STORED AS ZERO. Schema 2
carries `{"unknown": "<reason>"}` where a count could not be established, and
this reader refuses the whole payload rather than recording a harness that has
run nothing. Under schema 1 the harness emitted `0` and this reader coerced it
with `int(... or 0)`, so a harness whose database was missing its tables was
stored as a harness in perfect health -- and a table count did not tell them
apart, because a database of unrelated tables reports one like any other.

Refusing loses something and the trade is deliberate: the fact that a harness
was unreadable is reported to whoever ran the ingest and is not recorded in the
database, because the snapshot columns cannot hold `unknown` without a
migration. A stored zero is invisible; a refusal is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = 2

# The totals a snapshot is made of. Named because they are the ones that may
# arrive as `{"unknown": ...}` and the ones a refusal has to be able to name.
COUNTS = ("invocations", "failures", "human_requests", "human_responses")

# Every key the payload must carry for this to be that payload rather than some
# other JSON file somebody had to hand.
REQUIRED = ("schema", "project", "totals")


@dataclass
class Verdict:
    """What ingesting one part of a payload would do, or did."""

    subject: str
    state: str            # new | same | differs | refused
    differences: list[str] = field(default_factory=list)
    reason: str | None = None


def load(path: Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("a harness payload is one object, not a list")
    return payload


def check_schema(payload: dict) -> str | None:
    """Why this payload cannot be read, or None."""
    missing = [key for key in REQUIRED if key not in payload]
    if missing:
        return f"missing {', '.join(missing)}"
    version = payload.get("schema")
    if version != SCHEMA:
        return f"schema {version}, this reads {SCHEMA}"
    return None


def invocations_of(payload: dict) -> list[dict]:
    """The addressed rows, ignoring any without an address.

    A row with no address cannot be stored without inventing an identity for
    it, and an invented identity is one that will not match the same row next
    time.
    """
    return [row for row in payload.get("recent", []) if row.get("address")]


def unknown_totals(payload: dict) -> list[str]:
    """Every total the harness said it could not take, with its reason.

    `{"unknown": "<reason>"}` is a value and not a missing key: it means the
    fact could not be established and says why. It is not zero, not empty and
    not compliant.
    """
    totals = payload.get("totals") or {}
    found = []
    for name in COUNTS:
        value = totals.get(name)
        if isinstance(value, dict) and "unknown" in value:
            found.append(f"{name}: {value['unknown']}")
    return found


def asks_of(payload: dict) -> list[dict]:
    """The queue rows, ignoring any without an address.

    Same rule as `invocations_of`: a row that cannot be named cannot be matched
    to itself next time, and an invented identity is worse than a dropped row.
    """
    return [row for row in payload.get("waiting") or [] if row.get("address")]


def outstanding_of(payload: dict) -> list[dict]:
    """The questions still waiting on a person.

    Read from whether an answer is present, not from the harness's `status`
    string. The status is the harness's own word for it and can lag a response
    that has already arrived; the answer either is there or is not.

    **THIS IS THE ROWS THAT ARRIVED, WHICH IS NOT ALWAYS THE QUEUE.** Ask
    `dropped_from_queue` before presenting it as a work list.
    """
    return [row for row in asks_of(payload) if not row.get("answered_with")]


def dropped_from_queue(payload: dict) -> int | None:
    """How many queue rows the harness held back, or `None` if it did not say.

    **`None` AND `0` ARE DIFFERENT ANSWERS AND A WINDOW MUST NOT MERGE THEM.**
    Zero is a harness that sent its whole queue. `None` is a harness that did
    not report the size of the queue it capped -- older emitters carry neither
    `queue_shown` nor `queue_total` -- and a reader showing "0 held back" for
    that is claiming completeness nobody stated.

    This exists because the harness sent ten rows of a queue of fifteen and
    said nothing, so the Outstanding list read as the whole of the work waiting
    on a person when it was the oldest two thirds of it. The emitter now states
    both numbers; this is the half that reads them.
    """
    shown, total = payload.get("queue_shown"), payload.get("queue_total")
    if not isinstance(shown, int) or not isinstance(total, int):
        return None
    return max(0, total - shown)


def totals_of(payload: dict) -> dict[str, int]:
    """The counts, verbatim.

    THIS NEVER COERCES. It used to read `int(totals.get(name, 0) or 0)`, which
    turned an absent total, a null and an unknown alike into a zero the
    database then held as a fact about the harness. Anything that is not an
    integer here is a caller's mistake, because `plan` refuses such a payload
    before reaching this.
    """
    totals = payload.get("totals") or {}
    return {name: int(totals[name]) for name in COUNTS if name in totals}


def plan(payload: dict, lookup_invocation, lookup_ask=None) -> list[Verdict]:
    """What ingesting this payload would do. No writes."""
    problem = check_schema(payload)
    if problem:
        return [Verdict(str(payload.get("project", "<payload>")), "refused",
                        reason=problem)]

    unknowns = unknown_totals(payload)
    if unknowns:
        return [Verdict(
            str(payload.get("project", "<payload>")), "refused",
            differences=unknowns,
            reason="the harness could not take these counts; storing them as "
                   "zero would record a harness with nothing wrong",
        )]

    missing = [name for name in COUNTS if name not in (payload.get("totals") or {})]
    if missing:
        return [Verdict(
            str(payload.get("project", "<payload>")), "refused",
            reason=f"totals missing {', '.join(missing)}",
        )]

    verdicts = [Verdict(f"{payload['project']} totals", "new")]
    for row in invocations_of(payload):
        existing = lookup_invocation(row["address"])
        if existing is None:
            verdicts.append(Verdict(row["address"], "new"))
            continue
        differences = []
        for column, key in (("status", "status"), ("tool_name", "tool_name"),
                            ("error", "error")):
            incoming = row.get(key)
            current = getattr(existing, column)
            if incoming is not None and incoming != current:
                differences.append(f"{column}: here {current!r}, payload {incoming!r}")
        verdicts.append(Verdict(row["address"],
                                "differs" if differences else "same",
                                differences))

    # The queue. `lookup_ask` is optional so that a caller with no queue table
    # -- an older database, or a test of the invocation half alone -- keeps
    # working and simply reports nothing about it, rather than the rows being
    # silently swallowed by a caller that could have stored them.
    if lookup_ask is not None:
        for row in asks_of(payload):
            existing = lookup_ask(row["address"])
            if existing is None:
                verdicts.append(Verdict(row["address"], "new"))
                continue
            differences = []
            for column, key in (("answered_with", "answered_with"),
                                ("status", "status")):
                incoming = row.get(key)
                current = getattr(existing, column, None)
                if incoming is not None and incoming != current:
                    differences.append(
                        f"{column}: here {current!r}, payload {incoming!r}")
            verdicts.append(Verdict(row["address"],
                                    "differs" if differences else "same",
                                    differences))
    return verdicts


def render(verdicts: list[Verdict], written: bool,
           dropped: int | None = None) -> str:
    """What the ingest did, and what the payload could not tell it.

    `dropped` is `dropped_from_queue`'s answer. Optional because a caller with
    an older payload has nothing to pass, and that case prints differently from
    a queue that arrived whole -- the two are different claims and merging them
    is what let a truncated queue read as a complete one.
    """
    marks = {"new": "[+]", "same": "[=]", "differs": "[!]", "refused": "[x]"}
    lines = []
    for verdict in verdicts:
        lines.append(f"  {marks.get(verdict.state, '[?]')} {verdict.subject}")
        for difference in verdict.differences:
            lines.append(f"        {difference}")
        if verdict.reason:
            lines.append(f"        {verdict.reason}")
    lines.append("")
    lines.append("[+] new   [!] differs from what is here   [=] matching   [x] refused")
    lines.append("")
    if written:
        lines.append("Written.")
    else:
        lines.append("Nothing was written. Pass --write to apply this.")
    lines.append(
        "A field that differs is a disagreement, not a correction: see "
        "governance/qm/records/DRAFT-a-disagreement-is-a-delta.md.")
    lines.append(
        "Nothing here deletes. The payload carries an excerpt of the rows, so "
        "an invocation it does not mention is not one that was removed.")
    if dropped is None:
        lines.append(
            "This payload does not say how large the harness's queue is, so "
            "whether any questions were held back cannot be established here.")
    elif dropped:
        lines.append(
            f"{dropped} question(s) waiting on a person did not fit in this "
            f"payload and are not below. Raise the harness's queue cap "
            f"(`qmcp.dashboard.QUEUE`) or answer some.")
    return "\n".join(lines)
