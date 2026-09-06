"""dossier's content for the durable palette.

THE SHAPE IS NOT DEFINED HERE. `Go`, `Do`, `Show`, `Reach` come from
`dossier.rad.session.DURABLE_VERBS` and are identical in every host. This file
is only what dossier hangs under them -- which is exactly rad's division:
content belongs to the host.

WHY THE CHILD LISTS ARE SHORT. rad's keyboard budget is `1 + ceil(N/2) + 1`, and
a verb over budget is a resolver design error rather than a number to relax. Four
children cost at most 4 inputs to reach; ten would cost 7. Adding a child here
is a cost somebody pays on every use.

WHERE `Go` GETS ITS CHILDREN. `dossier.views.grouped`, so a view added to that
registry gets a keystroke without an edit here. Nothing else in this file is
derived, because nothing else is a list somebody else also keeps.

WHAT THIS CANNOT DO. Know whether a view exists. It names actions; applying them
is the host's, and an action named here that nothing handles is a dead wedge --
which `tests/test_rad_palette.py` checks for rather than trusting.
"""

from __future__ import annotations

from typing import Any

from dossier.rad.session import DO, GO, REACH, SHOW, Wedge
from dossier.views import grouped


def resolve(context: Any = None) -> tuple[Wedge, ...]:
    """The ring's top level, and everything under it.

    `context` is accepted and currently unused: the durable verbs are the same
    everywhere by design, and it is the *children* that will vary by selection.
    Taking it now means the signature does not change when they do.
    """
    return (
        # **THE VIEWS COME FROM `dossier.views`, GROUPED, AND THAT IS A
        # LEVEL.** `Go` held six of the eighteen views this application has;
        # the other twelve were reachable by mouse only. Eighteen children do
        # not fit -- rad places at most eight cells per level -- so the group
        # is a real level a person presses through rather than a heading
        # invented for a document.
        #
        # The cost is one keystroke: a view was `m` and two digits and is now
        # `m` and three. Paid deliberately, because two thirds of the views
        # cost infinity before.
        Wedge(GO, "Go", children=tuple(
            Wedge(f"go.{group.lower()}", group, children=tuple(
                Wedge(f"go.{view.name}", view.title, action=view.action)
                for view in found))
            for group, found in grouped())),
        Wedge(DO, "Do", children=(
            Wedge("do.advance", "Advance phase", action="delta.advance"),
            Wedge("do.note", "Add note", action="delta.note"),
            Wedge("do.sync", "Sync project", action="project.sync"),
            # Fourth, so it lands on a cardinal rather than a corner. `Do` was
            # three children and is now four, which costs nothing: rad's budget
            # is 1 + ceil(N/2) + 1, and that is 4 for both three children and
            # four. A fifth would be the one that costs.
            Wedge("do.sweep", "Sweep a dependency", action="sweep.review"),
            # **FIFTH AND SIXTH, AND THEY COST A STEP.** rad's budget is
            # 1 + ceil(N/2) + 1: four children cost 4 and six cost 5. Paid
            # because the alternative was worse -- `Add` and `Delete` sat in a
            # command bar being consolidated away, and an act with no wedge and
            # no button is an act only the keyboard can reach.
            Wedge("do.add", "Add a project", action="project.add"),
            Wedge("do.remove", "Remove a project", action="project.remove"),
            # **SEVENTH, AND IT COSTS A KEYSTROKE.** rad's budget is
            # 1 + ceil(N/2) + 1: six children cost 5 and seven cost 6. Paid
            # because the only route back to an empty dossier was
            # `dossier dev reset`, which drops every table with no backup and
            # whose entire safety net is the words "Use with caution in
            # production!" in a help text. An act that destructive reachable
            # only by somebody who already knows the command is not a
            # first-run story; it is a trap for the person most likely to
            # need it.
            Wedge("do.restart", "Archive and start over",
                  action="project.restart"),
        )),
        Wedge(SHOW, "Show", children=(
            Wedge("show.all", "All", action="filter.all"),
            Wedge("show.synced", "Synced only", action="filter.synced"),
            Wedge("show.drifting", "Drifting", action="filter.drifting"),
        )),
        Wedge(REACH, "Reach", children=(
            Wedge("reach.qmcp", "Open in qmcp", action="reach.qmcp"),
            Wedge("reach.ingest", "Ingest conversations",
                  action="reach.ingest"),
            Wedge("reach.reconcile", "Reconcile", action="reach.reconcile"),
            # Fourth in this group, so `PLACEMENT` gives it 4 -- route 4.4.
            # The number is not chosen here; it is what the ring assigns, and
            # `actions.py` declares the same one so the two can be compared.
            Wedge("reach.read", "Read conversation", action="reach.read"),
            # Fifth, and it costs a keystroke: rad's budget is
            # 1 + ceil(N/2) + 1, which is 4 for four children and 5 for five.
            # Paid because the alternative is a machine-wide act with no
            # keyboard route at all -- eighty-two indexed repositories had no
            # clone here and closing that gap meant typing `git clone`
            # eighty-two times.
            Wedge("reach.clone", "Clone what is absent", action="reach.clone"),
            # **SIXTH, AND IT COSTS NOTHING.** rad's budget is
            # 1 + ceil(N/2) + 1, which is 5 for five children and 5 for six --
            # so this one is free where the fifth was not. Placed beside the
            # clone deliberately: the two are the same act on different halves
            # of a repository. The clone brings the *code* for what this
            # database already indexes; this brings the *index* for what GitHub
            # has and nobody here has asked about yet.
            #
            # Before it, downloading an owner was `dossier github sync-user`
            # or `sync-org` -- and which of the two was the right one was
            # something you had to already know. The panel could add one
            # repository at a time and no more.
            Wedge("reach.download", "Download an owner",
                  action="reach.download"),
        )),
    )
