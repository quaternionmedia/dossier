"""Take delta payloads another system emitted, and put them in this database.

    dossier deltas ingest <payload.json>
    dossier deltas ingest <payload.json> --write

WHAT CROSSES IS A SCHEMA, NOT AN IMPORT. qmcp emits delta payloads whose `delta`
key holds this project's own `ProjectDelta` column names, so ingesting is a
constructor call and not a translation. Neither repository imports the other:
they would then have to ship together, which is the opposite of what a seam is
for. `qmcp/cookbook/delta.py` states the same contract from the emitting side.

IDENTITY IS THE ADDRESS, NOT THE ROW ID. A payload carries
`links[].target_name` holding an address like
`quaternionmedia/qmcp/delta/summarizer`. Ingesting the same payload twice must
update one row rather than making a second, and matching on the delta's `name`
alone would collide across projects -- two repositories may both have a delta
called `cleanup`.

NOTHING IS WRITTEN WITHOUT `--write`. The default reports what ingesting would
do. A sync that wrote on sight is one nobody dares run against real data, and
this database holds 141 projects somebody synced by hand.

WHAT THIS CANNOT DO.

  * Resolve a project it has never heard of. A payload naming
    `owner/repo` with no matching `Project` row is refused rather than
    creating one: inventing a project from a delta would let a typo in another
    system silently populate this one.
  * Decide who is right. Where a field differs between the payload and the row
    already here, that is a disagreement, and by
    `governance/qm/records/DRAFT-a-disagreement-is-a-delta.md` the answer is a
    delta to resolve rather than a winner to pick. This reports the difference
    and, with `--write`, takes the incoming value only for fields the payload
    actually carries.
  * Delete anything. A delta absent from a payload is not a delta that was
    removed; it is a delta this payload did not mention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = 1
ADDRESS_LINK = "address"

# Columns a payload may set on a ProjectDelta. Anything else it carries is
# ignored rather than passed through: an unknown key reaching the constructor
# is a TypeError deep in SQLModel, at ingest time, against real data.
WRITABLE = ("name", "title", "description", "phase", "delta_type", "priority")


@dataclass
class Verdict:
    """What ingesting one payload entry would do, or did."""

    address: str
    name: str
    action: str                      # "create", "update", "unchanged", "refused"
    reason: str = ""
    differences: list[str] = field(default_factory=list)


def load(path: Path) -> list[dict]:
    """Payloads from a file holding either one or a list of them."""
    if not path.is_file():
        raise SystemExit(f"{path}: no payload there.")
    data = json.loads(path.read_text(encoding="utf-8"))
    payloads = data if isinstance(data, list) else [data]
    if not payloads:
        raise SystemExit(f"{path}: no payloads. Nothing would be ingested.")
    return payloads


def address_of(payload: dict) -> str | None:
    """The address a payload names itself by, if it names one."""
    for link in payload.get("links") or []:
        if link.get("link_type") == ADDRESS_LINK and link.get("target_name"):
            return str(link["target_name"])
    project = payload.get("project")
    name = (payload.get("delta") or {}).get("name")
    if project and name:
        return f"{project}/delta/{name}"
    return None


def check_schema(payload: dict) -> str | None:
    """A payload from another schema version is refused, never guessed at."""
    version = payload.get("schema")
    if version != SCHEMA:
        return (f"payload schema {version!r}, this build ingests {SCHEMA}. "
                f"Refusing rather than guessing which keys moved")
    return None


def differences(row: Any, incoming: dict) -> list[str]:
    """Fields the payload carries that disagree with the row already here."""
    found: list[str] = []
    for key in WRITABLE:
        if key not in incoming:
            continue
        current = getattr(row, key, None)
        # `phase` is an enum on the row and a string in the payload.
        current_text = getattr(current, "value", current)
        if str(current_text) != str(incoming[key]):
            found.append(f"{key}: here {current_text!r}, payload {incoming[key]!r}")
    return found


def plan(payloads: list[dict], lookup_project, lookup_delta) -> list[Verdict]:
    """What ingesting these payloads would do. Reads, never writes.

    `lookup_project(full_name) -> project | None` and
    `lookup_delta(project_id, name) -> row | None` are passed in so this is
    testable without a database and so the caller owns the session.
    """
    verdicts: list[Verdict] = []
    for payload in payloads:
        address = address_of(payload) or "(no address)"
        row = payload.get("delta") or {}
        name = str(row.get("name") or "")

        problem = check_schema(payload)
        if problem:
            verdicts.append(Verdict(address, name, "refused", problem))
            continue
        if not name:
            verdicts.append(Verdict(address, name, "refused",
                                    "the payload names no delta"))
            continue

        project_name = payload.get("project")
        if not project_name:
            verdicts.append(Verdict(address, name, "refused",
                                    "the payload names no project"))
            continue
        project = lookup_project(project_name)
        if project is None:
            verdicts.append(Verdict(
                address, name, "refused",
                f"no project {project_name!r} here. Inventing one from a delta "
                f"would let a typo elsewhere populate this database"))
            continue

        existing = lookup_delta(project.id, name)
        if existing is None:
            verdicts.append(Verdict(address, name, "create"))
            continue
        found = differences(existing, row)
        verdicts.append(Verdict(address, name,
                                "update" if found else "unchanged",
                                differences=found))
    return verdicts


def render(verdicts: list[Verdict], written: bool) -> str:
    counts = {action: sum(1 for v in verdicts if v.action == action)
              for action in ("create", "update", "unchanged", "refused")}
    out = [
        f"{len(verdicts)} payload(s): {counts['create']} new, "
        f"{counts['update']} differing, {counts['unchanged']} already matching, "
        f"{counts['refused']} refused.",
        "",
    ]
    mark = {"create": "[+]", "update": "[!]", "unchanged": "[=]", "refused": "[x]"}
    for verdict in verdicts:
        out.append(f"  {mark[verdict.action]} {verdict.address}")
        if verdict.reason:
            out.append(f"        {verdict.reason}")
        for difference in verdict.differences:
            out.append(f"        {difference}")
    out += [
        "",
        "[+] new   [!] differs from what is here   [=] matching   [x] refused",
        "",
    ]
    out.append("Written." if written else
               "Nothing was written. Pass --write to apply this.")
    out.append("A field that differs is a disagreement, not a correction: see "
               "governance/qm/records/DRAFT-a-disagreement-is-a-delta.md.")
    out.append("Nothing here deletes. A delta this payload did not mention is "
               "not one that was removed.")
    return "\n".join(out)
