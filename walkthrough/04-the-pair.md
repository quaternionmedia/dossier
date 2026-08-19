# 04 — The pair: qmcp runs it, dossier shows it

Two applications, one dataset. qmcp is the harness: it invokes tools, runs
pipelines and holds the human-in-the-loop queue. dossier is the control panel:
it shows what exists, what is in flight, and what the harness has done.

**Neither imports the other.** What crosses is a schema, and the join is an
address that names the same row on both sides.

## The address is the join

    >>> address = "quaternionmedia/qmcp/invocation/4ea1e830"
    >>> owner, repo, kind, identifier = address.split("/", 3)
    >>> owner, repo, kind
    ('quaternionmedia', 'qmcp', 'invocation')

Everything after the kind is the identifier, verbatim — it may contain slashes,
so it is split off last and never re-parsed.

## Two payloads cross

| direction | command | carries |
|---|---|---|
| qmcp → dossier | `qmcp deltas` | units of work, as dossier's own column names |
| qmcp → dossier | `qmcp dashboard --json` | what the harness has run |

The delta payload uses dossier's column names deliberately, so the consumer
writes `ProjectDelta(**payload["delta"])` and nothing translates in between.

## Reading what the harness has run

    >>> from dossier.harness import check_schema, totals_of, invocations_of
    >>> report = {
    ...     "schema": 1,
    ...     "project": "quaternionmedia/qmcp",
    ...     "totals": {"invocations": 55, "failures": 0,
    ...                "human_requests": 19, "human_responses": 6},
    ...     "recent": [{"address": "quaternionmedia/qmcp/invocation/aaa",
    ...                 "tool_name": "echo", "status": "SUCCESS",
    ...                 "created_at": "2026-02-15 17:57:10"}],
    ... }
    >>> check_schema(report) is None
    True

The totals and the rows are stored as two different things, because they are
two different claims:

    >>> totals_of(report)["invocations"]
    55
    >>> len(invocations_of(report))
    1

Fifty-five invocations, one row. The payload carries an *excerpt* of the rows
and the harness's totals over its whole history — so recomputing the totals
from the rows would report the size of the excerpt and call it the history.
The control panel shows both, with the age of the reading beside them.

## A row without an address is not stored

    >>> invocations_of({"recent": [{"tool_name": "echo"}]})
    []

An invented identity is one that will not match the same row next time.

## Disagreement, not correction

Ingesting reports a field that differs rather than overwriting it:

    >>> from dossier.harness import plan
    >>> class Stored:
    ...     tool_name, status, error = "echo", "FAILURE", None
    >>> verdicts = plan(report, lookup_invocation=lambda address: Stored())
    >>> [v.state for v in verdicts]
    ['new', 'differs']
    >>> verdicts[1].differences
    ["status: here 'FAILURE', payload 'SUCCESS'"]

Neither side is authoritative. `governance/qm/records/DRAFT-a-disagreement-is-a-delta.md`
is why: two independent observers of a moving system will differ, and picking a
winner by fiat discards the more interesting fact.

## Running the pair

    # in qmcp
    uv run qmcp dashboard --json > harness.json
    uv run qmcp deltas > deltas.json

    # in dossier
    uv run dossier harness ingest harness.json --write
    uv run dossier deltas ingest deltas.json --write

Then open the control panel:

    uv run dossier dashboard

`Harness` is a tab, and the same facet fills the overview's harness sections —
one definition read at two scopes, so the two axes of the screen cannot
disagree about what a column means.

## What this is not yet

The payloads are files passed by hand. A live channel — the control panel
asking the harness directly, or the harness pushing on completion — is not
built, and nothing here pretends the figures are live: every harness reading
carries how long ago it was taken.
