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
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = 1

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


def totals_of(payload: dict) -> dict[str, int]:
    totals = payload.get("totals") or {}
    return {name: int(totals.get(name, 0) or 0)
            for name in ("invocations", "failures", "human_requests",
                         "human_responses")}


def plan(payload: dict, lookup_invocation) -> list[Verdict]:
    """What ingesting this payload would do. No writes."""
    problem = check_schema(payload)
    if problem:
        return [Verdict(str(payload.get("project", "<payload>")), "refused",
                        reason=problem)]

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
    return verdicts


def render(verdicts: list[Verdict], written: bool) -> str:
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
    return "\n".join(lines)
