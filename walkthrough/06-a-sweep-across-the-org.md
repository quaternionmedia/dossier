# 06 — A sweep across the org

Everything on this page runs. It is executed by the ordinary test command, so
an example that stops being true fails the build rather than sitting here
misleading somebody.

**The problem.** Twenty-four repositories declare `fastapi`. A new version
lands. Somebody has to decide whether the organisation takes it, and then that
decision has to reach twenty-four places without becoming twenty-four separate
decisions nobody is tracking.

**What this is not.** A bot that opens twenty-four pull requests. That exists
and it produces twenty-four notifications, twenty-four reviews, and no answer to
"is the organisation on the new version". A sweep is one piece of work with a
blast radius.

## One delta, many parts

    >>> from dossier.sweep import Sweep, Share, MECHANICAL
    >>> sweep = Sweep(package="fastapi", to_version="0.116.0", shares=[
    ...     Share(project="quaternionmedia/qmcp", declared=">=0.115.0",
    ...           manifest="pyproject.toml", shape=MECHANICAL, why="a manifest"),
    ...     Share(project="quaternionmedia/leo", declared=">=0.103.1",
    ...           manifest="pyproject.toml", shape=MECHANICAL, why="a manifest"),
    ... ])
    >>> sweep.blast_radius
    2

The sweep has an address, and each repository's share is `part-of` it:

    >>> sweep.address
    'quaternionmedia/sweep/delta/fastapi-0.116.0'
    >>> {r["relation"] for r in sweep.relations()}
    {'part-of'}

`part-of` and not `crosses`, deliberately. The repositories do not interact —
they each take the same change, and the sweep closes when all of them have.
`crosses` would claim they meet at a point, which is the relation for a seam and
not for a shared dependency.

The address is named for the change, not for the day it ran. A sweep named by
date is a different delta on every run, and the second one carries none of the
first one's approvals:

    >>> Sweep(package="fastapi", to_version="0.116.0").address == sweep.address
    True

## The shape of the work decides the tool

Not every share is the same job. Rewriting `>=0.115.0` to `>=0.116.0` is
something a parser does correctly every time. Deciding what to do about a
repository with no declared version is not.

    >>> from dossier.sweep import bump, already_ahead
    >>> bump(">=0.115.0", "0.116.0")
    '>=0.116.0'
    >>> bump("~=0.95", "0.116.0")
    '~=0.116.0'

A constraint with a ceiling somebody put there on purpose is refused rather than
flattened to one number:

    >>> bump("<1.0.0,>=0.92.0", "0.116.0") is None
    True

**And the one the real archive found.** A version bump is not monotonic across
an organisation just because it is a bump in the repository somebody was looking
at. Six of the twenty-four already ask for more than 0.116.0 — including this
one:

    >>> already_ahead(">=0.128.0", "0.116.0")
    True

Sweeping those mechanically would rewrite them backwards. So they are not
mechanical:

    >>> from dossier.sweep import plan, JUDGEMENT
    >>> ahead = Sweep(package="fastapi", shares=[
    ...     Share(project="quaternionmedia/dossier", declared=">=0.128.0",
    ...           manifest="pyproject.toml", shape=MECHANICAL, why="a manifest")])
    >>> plan(ahead, "0.116.0").shares[0].shape == JUDGEMENT
    True
    >>> "back" in plan(ahead, "0.116.0").shares[0].why
    True

Every share says why it is the shape it is. A shape without a reason is a
verdict.

## Dispatching, without choosing a topology first

That half is the harness's, and so is its page:
`../qmcp/walkthrough/05-dispatching-a-sweep.md`.

**The split is the seam, not an accident of filing.** This repository cannot
import `qmcp` and does not try: what crosses between them is a payload and a
schema, the same trade the delta and harness payloads make. A walkthrough that
imported across it would be demonstrating a coupling that is not there, and it
would pass here and fail for anybody who installed one without the other.

What crosses is the shape vocabulary and the shares:

    >>> planned = plan(Sweep(package="fastapi", shares=[
    ...     Share(project="quaternionmedia/qmcp", declared=">=0.115.0",
    ...           manifest="pyproject.toml", shape=MECHANICAL, why="a manifest")]),
    ...     "0.116.0")
    >>> [{"project": s.project, "shape": s.shape, "declared": s.declared}
    ...  for s in planned.shares]
    [{'project': 'quaternionmedia/qmcp', 'shape': 'mechanical', 'declared': '>=0.115.0'}]

Four words are the whole contract -- `mechanical`, `judgement`, `human`,
`unknown` -- and `qmcp/tests/test_sweep.py` checks that both sides still spell
them the same way.

## What this page cannot show you

Whether the organisation should take 0.116.0. Nothing here knows that, and
nothing here is arranged to find out -- the version is an argument, and choosing
it is the decision the whole apparatus exists to carry out rather than to make.

Nor can it show a repository being changed. A sweep prepares; approving it and
cutting the tag afterwards are a person's by constitution --
`governance/qm/ci/attested-registry.yaml`.
