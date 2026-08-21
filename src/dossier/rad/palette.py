"""dossier's content for the durable palette.

THE SHAPE IS NOT DEFINED HERE. `Go`, `Do`, `Show`, `Reach` come from
`dossier.rad.session.DURABLE_VERBS` and are identical in every host. This file
is only what dossier hangs under them -- which is exactly rad's division:
content belongs to the host.

WHY THE CHILD LISTS ARE SHORT. rad's keyboard budget is `1 + ceil(N/2) + 1`, and
a verb over budget is a resolver design error rather than a number to relax. Four
children cost at most 4 inputs to reach; ten would cost 7. Adding a child here
is a cost somebody pays on every use.

WHAT THIS CANNOT DO. Know whether a view exists. It names actions; applying them
is the host's, and an action named here that nothing handles is a dead wedge --
which `tests/test_rad_palette.py` checks for rather than trusting.
"""

from __future__ import annotations

from typing import Any

from dossier.rad.session import DO, GO, REACH, SHOW, Wedge


def resolve(context: Any = None) -> tuple[Wedge, ...]:
    """The ring's top level, and everything under it.

    `context` is accepted and currently unused: the durable verbs are the same
    everywhere by design, and it is the *children* that will vary by selection.
    Taking it now means the signature does not change when they do.
    """
    return (
        Wedge(GO, "Go", children=(
            # First, so it is the cheapest wedge in the ring to reach: the
            # highlight lands here on entering Go, making the org overview
            # open, enter, enter. Ordering inside a verb is the host's only
            # lever on cost once the child count is fixed.
            Wedge("go.overview", "Overview", action="view.overview"),
            Wedge("go.deltas", "Deltas", action="view.deltas"),
            Wedge("go.governance", "Governance", action="view.governance"),
            Wedge("go.disk", "Disk", action="view.disk"),
            Wedge("go.details", "Details", action="view.details"),
        )),
        Wedge(DO, "Do", children=(
            Wedge("do.advance", "Advance phase", action="delta.advance"),
            Wedge("do.note", "Add note", action="delta.note"),
            Wedge("do.sync", "Sync project", action="project.sync"),
            # Fourth, so it lands on a cardinal rather than a corner. `Do` was
            # three children and is now four, which costs nothing: rad's budget
            # is 1 + ceil(N/2) + 1, and that is 4 for both three children and
            # four. A fifth would be the one that costs.
            Wedge("do.sweep", "Sweep a dependency", action="sweep.review"),
        )),
        Wedge(SHOW, "Show", children=(
            Wedge("show.all", "All", action="filter.all"),
            Wedge("show.synced", "Synced only", action="filter.synced"),
            Wedge("show.drifting", "Drifting", action="filter.drifting"),
        )),
        Wedge(REACH, "Reach", children=(
            Wedge("reach.qmcp", "Open in qmcp", action="reach.qmcp"),
            Wedge("reach.ingest", "Ingest deltas", action="reach.ingest"),
            Wedge("reach.reconcile", "Reconcile", action="reach.reconcile"),
        )),
    )
